"""Session manager — one Session per intent_id, lifecycle owner for the live pipeline.

Holds: SnapshotBuilder, ThresholdDetector, VerdictService, RationaleStreamer,
the per-session asyncio Queue used to push envelopes to the WS writer, the
monotonic sequence counter, and the consume task that pulls from MarketBus.

See spec §1, §7.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from src.market_risk.ws_schemas import (
    MessageType,
    SubscribePayload,
    WSEnvelopeAdapter,
)

if TYPE_CHECKING:
    from src.market_risk.ws_schemas import TradeIntent

    from .market_bus import MarketBus
    from .rationale_streamer import RationaleStreamer
    from .snapshot_builder import SnapshotBuilder
    from .threshold_detector import ThresholdDetector
    from .verdict_service import VerdictService

ENVELOPE_QUEUE_SIZE = 64


@dataclass
class Session:
    """One live-session container, bound to a single TradeIntent."""

    intent: TradeIntent
    bus: MarketBus
    snapshot_builder: SnapshotBuilder
    detector: ThresholdDetector
    verdicts: VerdictService
    streamer: RationaleStreamer
    out: asyncio.Queue[bytes] = field(
        default_factory=lambda: asyncio.Queue(maxsize=ENVELOPE_QUEUE_SIZE)
    )
    _seq: int = 0
    _consume_task: asyncio.Task[None] | None = None

    def next_seq(self) -> int:
        self._seq += 1
        return self._seq

    async def emit_subscribed(self) -> None:
        env = WSEnvelopeAdapter.model_validate(
            {
                "seq": self.next_seq(),
                "ts": datetime.now(UTC).isoformat(),
                "type": MessageType.SUBSCRIBE.value,
                "payload": SubscribePayload(intent_id=self.intent.intent_id).model_dump(),
            }
        )
        await self._enqueue(env.model_dump_json().encode())

    async def _enqueue(self, payload: bytes) -> None:
        # Drop newest if full — trailing state stays stable.
        with contextlib.suppress(asyncio.QueueFull):
            self.out.put_nowait(payload)

    def start(self) -> None:
        if self._consume_task is None:
            self._consume_task = asyncio.create_task(
                self._consume_forever(), name=f"session-consume-{self.intent.intent_id}"
            )

    async def stop(self) -> None:
        if self._consume_task is not None:
            self._consume_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._consume_task
            self._consume_task = None

    async def _consume_forever(self) -> None:
        """Read raw bus messages for the intent's symbol and produce envelopes.

        Stub for the verdict + rationale pipeline. The real implementation pulls
        raw Binance frames off the bus, calls SnapshotBuilder.build(...),
        feeds detector.detect(...), and emits envelopes for every output. This
        skeleton is wired so the WS endpoint can pump envelopes; production
        density of work happens in the integration session that follows.
        """
        async for _ in self.bus.stream(self.intent.asset):
            await asyncio.sleep(0)  # cooperate; no-op for now


__all__ = ["ENVELOPE_QUEUE_SIZE", "Session"]
