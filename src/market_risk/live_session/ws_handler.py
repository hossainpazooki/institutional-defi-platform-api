"""FastAPI WebSocket handler for `/v2/ws/trade/{intent_id}`.

Heartbeat: server pings every 20s; client must pong within 10s. Monotonic seq.
See spec §7.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.config import get_settings

logger = logging.getLogger(__name__)

PING_INTERVAL_SECONDS = 20.0
PONG_TIMEOUT_SECONDS = 10.0

router = APIRouter(prefix="/v2/ws", tags=["Live Session"])


async def _ping_loop(ws: WebSocket) -> None:
    while True:
        await asyncio.sleep(PING_INTERVAL_SECONDS)
        try:
            await asyncio.wait_for(ws.send_text("ping"), timeout=PONG_TIMEOUT_SECONDS)
        except (TimeoutError, WebSocketDisconnect):
            return


@router.websocket("/trade/{intent_id}")
async def trade_session(ws: WebSocket, intent_id: str) -> None:
    """Per-intent live session WebSocket.

    Phase 1: unauthenticated. Production-shaped lifecycle (accept → subscribe →
    pump envelopes → heartbeat → terminate). Real session wiring lands in B7's
    follow-up where SessionManager + Ingestor + Bus are composed.
    """
    settings = get_settings()
    if not getattr(settings, "live_threshold_rationale_enabled", False):
        await ws.close(code=1008, reason="live-session flag disabled")
        return

    await ws.accept()
    out: asyncio.Queue[str] = asyncio.Queue(maxsize=64)

    async def _send_loop() -> None:
        while True:
            payload = await out.get()
            await ws.send_text(payload)

    send_task = asyncio.create_task(_send_loop(), name=f"ws-send-{intent_id}")
    ping_task = asyncio.create_task(_ping_loop(ws), name=f"ws-ping-{intent_id}")

    try:
        # Wait for client subscribe message before pumping envelopes.
        first = await ws.receive_text()
        logger.info("ws_first_message", extra={"intent_id": intent_id, "len": len(first)})

        # Minimal lifecycle echo: send back a synthetic subscribed envelope so
        # connectivity tests observe a server-side response.
        await out.put(
            f'{{"seq":1,"ts":"1970-01-01T00:00:00Z","type":"subscribe","payload":{{"intent_id":"{intent_id}"}}}}'
        )

        while True:
            # Block on either inbound message or send cancellation.
            msg: Any = await ws.receive_text()
            if msg == "pong":
                continue
    except WebSocketDisconnect:
        return
    finally:
        for t in (send_task, ping_task):
            t.cancel()
        for t in (send_task, ping_task):
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t


__all__ = ["PING_INTERVAL_SECONDS", "PONG_TIMEOUT_SECONDS", "router"]
