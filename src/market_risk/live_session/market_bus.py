"""In-process market data bus — fans raw Binance ticks to N session subscribers.

One bounded asyncio.Queue per subscriber, drop-newest backpressure. The bus
carries raw market state only; trade-derived state lives in Session.

See spec §3.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

DEFAULT_QUEUE_SIZE = 32


@dataclass
class _SubscriberQueue:
    queue: asyncio.Queue[dict[str, Any]]
    dropped: int = 0


@dataclass
class MarketBus:
    """Fan-out queue registry keyed by symbol.

    `publish(symbol, payload)` enqueues to every subscriber for `symbol`.
    When a subscriber's queue is full, the **newest** message is dropped
    (i.e. publish-side discard) and its drop counter is incremented. The
    drop-newest variant preserves the most recent backlog rather than the
    most recent edge — chosen to keep verdict-relevant trailing state stable
    in the face of an over-busy renderer.
    """

    queue_size: int = DEFAULT_QUEUE_SIZE
    _subscribers: dict[str, list[_SubscriberQueue]] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def subscribe(self, symbol: str) -> _SubscriberQueue:
        async with self._lock:
            sub = _SubscriberQueue(queue=asyncio.Queue(maxsize=self.queue_size))
            self._subscribers.setdefault(symbol, []).append(sub)
            return sub

    async def unsubscribe(self, symbol: str, sub: _SubscriberQueue) -> None:
        async with self._lock:
            subs = self._subscribers.get(symbol)
            if subs is None:
                return
            try:
                subs.remove(sub)
            except ValueError:
                return
            if not subs:
                self._subscribers.pop(symbol, None)

    def subscriber_count(self, symbol: str) -> int:
        return len(self._subscribers.get(symbol, ()))

    def total_dropped(self) -> int:
        return sum(s.dropped for subs in self._subscribers.values() for s in subs)

    async def publish(self, symbol: str, payload: dict[str, Any]) -> None:
        subs = list(self._subscribers.get(symbol, ()))
        for s in subs:
            try:
                s.queue.put_nowait(payload)
            except asyncio.QueueFull:
                s.dropped += 1  # noqa: PERF203 - per-subscriber drop tracking is the point

    async def stream(self, symbol: str) -> AsyncIterator[dict[str, Any]]:
        sub = await self.subscribe(symbol)
        try:
            while True:
                payload = await sub.queue.get()
                yield payload
        finally:
            await self.unsubscribe(symbol, sub)


__all__ = ["MarketBus"]
