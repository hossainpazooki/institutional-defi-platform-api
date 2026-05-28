"""Deterministic fixture ingestor — publishes a scripted sequence of frames
into a MarketBus for tests and offline development.

This is the "live" side of the pipeline for the vertical slice. It removes
the Binance WS dependency from the integration test so we can assert exact
envelope sequences and latency without going to the network.

Frame shape is the normalized format consumed by `pipeline.LiveSessionPipeline`:

    {"type": "kline_close", "close": float}
    {"type": "snapshot_inputs", "mark": str, "bid": str, "ask": str,
     "depth_bid": [[price, size], ...], "depth_ask": [[price, size], ...],
     "funding_rate": float | None}
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .market_bus import MarketBus


@dataclass
class FixtureIngestor:
    """Replays a fixed list of frames into the bus at a configurable delay.

    The default delay of 0 makes tests deterministic (publish-immediately).
    Production fixture replays at ~10 Hz to simulate real market cadence.

    `wait_for_subscriber=True` blocks the first publish until at least one
    subscriber has registered on the bus for `symbol`. This eliminates the
    classic publish/subscribe race when the consumer (e.g. `Session`) and
    the producer (this ingestor) are both started by an outer harness with
    interleaved `asyncio.create_task` calls.
    """

    bus: MarketBus
    symbol: str
    frames: Sequence[dict[str, Any]]
    delay_s: float = 0.0
    wait_for_subscriber: bool = False
    wait_timeout_s: float = 2.0
    _task: asyncio.Task[None] | None = field(default=None, init=False)

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name=f"fixture-{self.symbol}")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        import contextlib

        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _run(self) -> None:
        if self.wait_for_subscriber:
            await self._await_subscriber()
        for frame in self.frames:
            await self.bus.publish(self.symbol, frame)
            if self.delay_s > 0:
                await asyncio.sleep(self.delay_s)

    async def _await_subscriber(self) -> None:
        """Spin until the bus has at least one subscriber for `symbol`, or timeout."""
        deadline = asyncio.get_event_loop().time() + self.wait_timeout_s
        while self.bus.subscriber_count(self.symbol) == 0:
            if asyncio.get_event_loop().time() > deadline:
                return
            await asyncio.sleep(0.01)

    async def drain(self) -> None:
        """Wait until all frames have been published. Caller drives the bus consumer."""
        if self._task is not None:
            await self._task


__all__ = ["FixtureIngestor"]
