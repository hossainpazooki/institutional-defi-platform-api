"""FastAPI WebSocket handler for `/v2/ws/trade/{intent_id}`.

Drains the `Session` envelope lanes with strict audit-over-tick priority:

1. Repeatedly drain every immediately-available envelope from `session.audit_out`.
2. If nothing on audit, send at most one envelope from `session.tick_out`.
3. If both lanes are empty, wait for whichever lane receives the next envelope.
   When the wait wakes up with both ready (rare), audit wins; the tick is
   re-enqueued via the bounded `tick_out` (drop-newest semantics may apply).

This preserves the contract from spec §5: verdict envelopes (which arrive on
the audit lane) reach the client before any rationale token, regardless of
how many tick envelopes are simultaneously queued.

Heartbeat (spec §7):

The server sends a `ping` text frame every `Settings.ws_ping_interval_seconds`
and waits `Settings.ws_pong_timeout_seconds` for a matching `pong` text frame
from the client. A `_Heartbeat` state cell is shared between `_ping_loop`
(reader) and `_receive_loop` (writer) — both run on the same event loop, so a
plain dataclass with a monotonic-time field is safe without locking. If a
pong does not arrive in time, `_ping_loop` emits a typed `ws_idle_timeout`
error envelope and returns; the outer `asyncio.wait(FIRST_COMPLETED)` then
falls through to the existing teardown, which cancels the sender / receiver
and releases the lease exactly once.

The heartbeat interval and timeout are read from `Settings` at handler entry
so tests can drive sub-second cadences via the `WS_PING_INTERVAL_SECONDS` /
`WS_PONG_TIMEOUT_SECONDS` env vars without patching module constants.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.config import get_settings
from src.market_risk.ws_schemas import ErrorEnvelope, ErrorPayload

from .session_manager import Session, get_session_provider
from .session_registry import IntentTerminalError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v2/ws", tags=["Live Session"])


@dataclass
class _Heartbeat:
    """Per-connection liveness cell shared between ping + receive loops.

    `last_pong_monotonic` is updated by `_receive_loop` on every inbound `pong`
    text frame and inspected by `_ping_loop` after each `pong_timeout_s`
    grace window. Both coroutines run on the same event loop — no lock needed.
    """

    last_pong_monotonic: float


async def _ping_loop(
    ws: WebSocket,
    hb: _Heartbeat,
    *,
    interval_s: float,
    pong_timeout_s: float,
) -> None:
    """Server-initiated heartbeat with liveness check.

    Each cycle:
      1. Sleep `interval_s`.
      2. Send `ping`.
      3. Sleep `pong_timeout_s` to give the client a chance to respond.
      4. If `hb.last_pong_monotonic` is still older than the ping we just
         sent, emit a `ws_idle_timeout` error envelope and return. The outer
         `asyncio.wait` in `trade_session` then drives normal teardown.
    """
    while True:
        await asyncio.sleep(interval_s)
        ping_sent_at = time.monotonic()
        try:
            await ws.send_text("ping")
        except WebSocketDisconnect:
            return
        except Exception:  # noqa: BLE001 - any send failure is a terminal signal
            return
        await asyncio.sleep(pong_timeout_s)
        if hb.last_pong_monotonic < ping_sent_at:
            await _emit_error_envelope(
                ws,
                code="ws_idle_timeout",
                message=f"no pong within {pong_timeout_s}s of last ping",
            )
            return


async def _receive_loop(ws: WebSocket, hb: _Heartbeat) -> None:
    """Drain inbound messages. Updates the heartbeat cell on every `pong`."""
    try:
        while True:
            msg = await ws.receive_text()
            if msg == "pong":
                hb.last_pong_monotonic = time.monotonic()
                continue
            # Future: route inbound subscribe / control messages here.
    except WebSocketDisconnect:
        return


async def _run_sender(ws: WebSocket, session: Session) -> None:
    """Priority-merge sender: strict audit-over-tick.

    The loop has three phases per iteration:

    Phase 1 — drain all currently-available audit envelopes via `get_nowait()`.
    Phase 2 — if audit was empty, send at most one tick via `get_nowait()`.
    Phase 3 — both lanes empty: race a `get()` on each lane and pick the winner,
              with audit-priority tie-break when both resolve in the same wakeup.

    Cancellation is the normal shutdown path. WebSocketDisconnect from a send
    bubbles up to `trade_session` which performs the orderly teardown.
    """
    audit = session.audit_out
    ticks = session.tick_out

    while True:
        # Phase 1 — drain audit.
        drained_anything = False
        while True:
            try:
                payload = audit.get_nowait()
            except asyncio.QueueEmpty:
                break
            await ws.send_bytes(payload)
            drained_anything = True

        # Phase 2 — at most one tick if audit was empty this iteration.
        if not drained_anything:
            try:
                tick_payload = ticks.get_nowait()
            except asyncio.QueueEmpty:
                tick_payload = None
            if tick_payload is not None:
                await ws.send_bytes(tick_payload)
                continue

        # If we drained audit at least once, loop back to check audit again
        # before pulling a tick. This is the starvation guard for the tick
        # lane — when audit is continuously busy, ticks pile up in their
        # bounded queue and drop-newest semantics apply, which is intentional.
        if drained_anything:
            continue

        # Phase 3 — wait on either lane.
        audit_get = asyncio.create_task(audit.get(), name="ws-audit-get")
        tick_get = asyncio.create_task(ticks.get(), name="ws-tick-get")
        try:
            done, _pending = await asyncio.wait(
                {audit_get, tick_get},
                return_when=asyncio.FIRST_COMPLETED,
            )
        except asyncio.CancelledError:
            for t in (audit_get, tick_get):
                t.cancel()
            for t in (audit_get, tick_get):
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await t
            raise

        if audit_get in done:
            await ws.send_bytes(audit_get.result())
            if tick_get in done:
                # Both fired in the same wakeup — re-enqueue the tick with
                # drop-newest semantics; audit always wins the tie.
                with contextlib.suppress(asyncio.QueueFull):
                    ticks.put_nowait(tick_get.result())
            else:
                tick_get.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await tick_get
        else:
            # Only tick is ready.
            await ws.send_bytes(tick_get.result())
            audit_get.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await audit_get


async def _emit_error_envelope(ws: WebSocket, code: str, message: str) -> None:
    """Best-effort error envelope on the WS before close. Swallows send failures."""
    env = ErrorEnvelope(
        seq=0,
        ts=datetime.now(UTC),
        payload=ErrorPayload(code=code, message=message),
    )
    with contextlib.suppress(Exception):
        await ws.send_bytes(env.model_dump_json().encode())


@router.websocket("/trade/{intent_id}")
async def trade_session(ws: WebSocket, intent_id: str) -> None:
    """Per-intent live session WebSocket.

    Lifecycle:
      accept → resolve session via provider → start session → race
      (sender ‖ receiver ‖ pinger) until one finishes → teardown.

    Phase 1: unauthenticated. The intent_id ownership check belongs in the
    session provider when auth lands.
    """
    settings = get_settings()
    if not getattr(settings, "live_threshold_rationale_enabled", False):
        await ws.close(code=1008, reason="live-session flag disabled")
        return

    provider = get_session_provider()
    if provider is None:
        await ws.close(code=1011, reason="no session provider configured")
        return

    ping_interval_s = float(settings.ws_ping_interval_seconds)
    pong_timeout_s = float(settings.ws_pong_timeout_seconds)

    await ws.accept()

    try:
        lease = await provider(intent_id)
    except IntentTerminalError as exc:
        logger.info(
            "intent_terminal_acquire_rejected",
            extra={"intent_id": intent_id, "status": exc.status},
        )
        await _emit_error_envelope(
            ws, code="intent_terminal", message=str(exc)
        )
        await ws.close(code=1008, reason="intent is terminal")
        return
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "session_provider_failed",
            extra={"intent_id": intent_id, "error": str(exc)},
        )
        await _emit_error_envelope(ws, code="session_provider_failed", message=str(exc))
        await ws.close(code=1011, reason="session provider error")
        return

    session = lease.session
    # The registry calls `session.start()` on first acquire (idempotent), so we
    # don't need to call it again here. `emit_subscribed` is per-connection.
    session.start()
    await session.emit_subscribed()

    hb = _Heartbeat(last_pong_monotonic=time.monotonic())

    sender_task = asyncio.create_task(_run_sender(ws, session), name=f"ws-send-{intent_id}")
    recv_task = asyncio.create_task(_receive_loop(ws, hb), name=f"ws-recv-{intent_id}")
    ping_task = asyncio.create_task(
        _ping_loop(
            ws,
            hb,
            interval_s=ping_interval_s,
            pong_timeout_s=pong_timeout_s,
        ),
        name=f"ws-ping-{intent_id}",
    )
    tasks = (sender_task, recv_task, ping_task)

    try:
        done, _pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        # If a task raised, surface it for an error envelope on the way out.
        # Clean return from `_ping_loop` (idle timeout) is not an exception —
        # the typed `ws_idle_timeout` envelope was already emitted inside the
        # loop, so we do not double-emit here.
        for t in done:
            task_exc = t.exception()
            if task_exc is not None and not isinstance(task_exc, WebSocketDisconnect):
                logger.warning(
                    "ws_task_error",
                    extra={
                        "intent_id": intent_id,
                        "task": t.get_name(),
                        "error": str(task_exc),
                    },
                )
                await _emit_error_envelope(
                    ws, code="ws_task_error", message=f"{t.get_name()}: {task_exc}"
                )
    except WebSocketDisconnect:
        # Normal client disconnect.
        pass
    finally:
        for t in tasks:
            t.cancel()
        for t in tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t
        # Release through the lease — the registry decides whether this was
        # the final refcount and whether to actually stop the session.
        with contextlib.suppress(Exception):
            await lease.release()
        with contextlib.suppress(Exception):
            await ws.close()


__all__ = ["_run_sender", "router"]
