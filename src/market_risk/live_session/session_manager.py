"""Session manager — one Session per intent_id, lifecycle owner for the live pipeline.

Owns: MarketBus subscription, LiveSessionPipeline, the two outbound envelope
queues (tick lane + audit lane), monotonic sequence counter, consume task.

See spec §1, §7.

Backpressure semantics — IMPORTANT:

- The **tick lane** (market data) is bounded with drop-newest. Tick envelopes
  describe rapidly-changing market state; a dropped tick is acceptable because
  the next one arrives milliseconds later.
- The **audit lane** (compliance / threshold / rationale envelopes) is
  unbounded. These describe state transitions and rationale content that the
  audit trail depends on; silent drop would compromise the audit-grade claim.
  Slow consumers are absorbed in memory and surface as backpressure on the
  WS write loop, not as lost events.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, TypeAlias

from src.market_risk.ws_schemas import (
    SubscribeEnvelope,
    SubscribePayload,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from src.market_risk.ws_schemas import TradeIntent

    from .market_bus import MarketBus
    from .pipeline import LiveSessionPipeline
    from .session_registry import SessionLease

TICK_QUEUE_SIZE = 64

# A SessionProvider takes an intent_id and returns a SessionLease — the
# lease bundles the Session with a one-shot release callable owned by the
# registry. The WS handler calls `lease.release()` on teardown rather than
# `session.stop()` directly, so the registry can manage refcounts.
SessionProvider: TypeAlias = "Callable[[str], Awaitable[SessionLease]]"

_session_provider: Callable[[str], Awaitable[SessionLease]] | None = None


def set_session_provider(
    provider: Callable[[str], Awaitable[SessionLease]] | None,
) -> None:
    """Install a session provider used by the WS handler.

    Production wires this at app startup with a real registry. Tests inject a
    fixture-driven provider. Setting `None` clears it; `reset_session_provider()`
    is the named alias for clarity in test teardown.
    """
    global _session_provider  # noqa: PLW0603 - module-level provider is intentional
    _session_provider = provider


def reset_session_provider() -> None:
    """Clear the installed session provider. Use in test `finally:` blocks."""
    set_session_provider(None)


def get_session_provider() -> Callable[[str], Awaitable[SessionLease]] | None:
    """Return the currently-installed session provider, or None if unconfigured."""
    return _session_provider


@dataclass
class Session:
    """One live-session container, bound to a single TradeIntent.

    The Session does not know how to build snapshots, detect crossings, or run
    rationale — those live in `LiveSessionPipeline`. The Session is just the
    transport-level glue: bus subscription, envelope queues, lifecycle.
    """

    intent: TradeIntent
    bus: MarketBus
    pipeline: LiveSessionPipeline | None = None
    tick_out: asyncio.Queue[bytes] = field(
        default_factory=lambda: asyncio.Queue(maxsize=TICK_QUEUE_SIZE)
    )
    audit_out: asyncio.Queue[bytes] = field(default_factory=lambda: asyncio.Queue())
    _seq: int = 0
    _consume_task: asyncio.Task[None] | None = None

    def next_seq(self) -> int:
        self._seq += 1
        return self._seq

    async def emit_subscribed(self) -> None:
        env = SubscribeEnvelope(
            seq=self.next_seq(),
            ts=datetime.now(UTC),
            payload=SubscribePayload(intent_id=self.intent.intent_id),
        )
        await self._enqueue_audit(env.model_dump_json().encode())

    async def emit_tick(self, payload: bytes) -> None:
        """Drop-newest semantics — caller never blocks; lost ticks counted upstream."""
        with contextlib.suppress(asyncio.QueueFull):
            self.tick_out.put_nowait(payload)

    async def emit_audit(self, payload: bytes) -> None:
        """No-drop semantics — must await if the queue is being processed slowly."""
        await self.audit_out.put(payload)

    async def _enqueue_audit(self, payload: bytes) -> None:
        await self.audit_out.put(payload)

    def start(self) -> None:
        if self._consume_task is None:
            self._consume_task = asyncio.create_task(
                self._consume_forever(),
                name=f"session-consume-{self.intent.intent_id}",
            )

    async def stop(self) -> None:
        if self._consume_task is not None:
            self._consume_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._consume_task
            self._consume_task = None
        if self.pipeline is not None:
            await self.pipeline.join()

    async def _consume_forever(self) -> None:
        """Pull raw frames off the bus and drive the pipeline.

        With no pipeline attached this becomes a no-op consumer — preserves
        the old skeleton behavior for callers that haven't migrated yet.
        """
        async for frame in self.bus.stream(self.intent.asset):
            if self.pipeline is None:
                await asyncio.sleep(0)
                continue
            try:
                await self.pipeline.handle_frame(frame)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                import logging

                logging.getLogger(__name__).warning(
                    "pipeline_frame_failed",
                    extra={"intent_id": self.intent.intent_id, "error": str(exc)},
                )


__all__ = [
    "TICK_QUEUE_SIZE",
    "Session",
    "SessionProvider",
    "get_session_provider",
    "reset_session_provider",
    "set_session_provider",
]
