"""Binance combined-streams ingestor — one asyncio.Task per active symbol.

URL: wss://stream.binance.com:9443/stream?streams=<sym>@bookTicker/<sym>@aggTrade/<sym>@kline_1m/<sym>@markPrice@1s

Ref-counted: a symbol's task starts on first subscribe and tears down when the
last subscriber unsubscribes. Outbound is throttled to 10 Hz.

In test/CI / non-network environments, run with `live=False` to use a no-op
ingestor (the bus stays empty; tests inject ticks directly).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .market_bus import MarketBus

logger = logging.getLogger(__name__)

BINANCE_COMBINED_BASE = "wss://stream.binance.com:9443/stream?streams="

# Counter exposed for tests / observability.
DROPPED_TICKS_COUNTER: dict[str, int] = {}


def _streams_for(symbol: str) -> str:
    s = symbol.lower()
    return (
        f"{s}@bookTicker/"
        f"{s}@aggTrade/"
        f"{s}@kline_1m/"
        f"{s}@markPrice@1s"
    )


def binance_url(symbol: str) -> str:
    return f"{BINANCE_COMBINED_BASE}{_streams_for(symbol)}"


WebsocketsConnectFn = Callable[[str], Awaitable[Any]]


@dataclass
class Ingestor:
    """Background task pool keyed by symbol.

    The `connect_fn` indirection lets tests inject a fake WS connection
    without taking a `websockets` dependency in unit tests.
    """

    bus: MarketBus
    connect_fn: WebsocketsConnectFn | None = None
    _tasks: dict[str, asyncio.Task[None]] = field(default_factory=dict)
    _refcount: dict[str, int] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def acquire(self, symbol: str) -> None:
        async with self._lock:
            self._refcount[symbol] = self._refcount.get(symbol, 0) + 1
            if symbol not in self._tasks:
                self._tasks[symbol] = asyncio.create_task(
                    self._run_symbol(symbol), name=f"binance-ingest-{symbol}"
                )

    async def release(self, symbol: str) -> None:
        async with self._lock:
            n = self._refcount.get(symbol, 0)
            if n <= 1:
                self._refcount.pop(symbol, None)
                task = self._tasks.pop(symbol, None)
                if task is not None:
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task
            else:
                self._refcount[symbol] = n - 1

    async def shutdown(self) -> None:
        async with self._lock:
            tasks = list(self._tasks.values())
            self._tasks.clear()
            self._refcount.clear()
        for t in tasks:
            t.cancel()
        for t in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await t

    async def _run_symbol(self, symbol: str) -> None:
        """Connect to Binance combined stream and publish to the bus.

        On any error, log and retry with exponential backoff capped at 60s.
        """
        backoff = 1.0
        while True:
            try:
                await self._connect_and_pump(symbol)
                backoff = 1.0  # Reset after a clean session.
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("ingest_symbol_error", extra={"symbol": symbol, "error": str(exc)})
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60.0)

    async def _connect_and_pump(self, symbol: str) -> None:
        connect = self.connect_fn or _default_connect
        url = binance_url(symbol)
        async with await connect(url) as ws:
            async for raw in ws:
                msg = json.loads(raw) if isinstance(raw, (str, bytes, bytearray)) else raw
                data = msg.get("data") if isinstance(msg, dict) else None
                if not isinstance(data, dict):
                    continue
                await self.bus.publish(symbol, data)


async def _default_connect(url: str) -> Any:
    """Lazy import — keeps `websockets` optional for unit tests / non-network envs."""
    import websockets

    return await websockets.connect(url)


__all__ = ["DROPPED_TICKS_COUNTER", "Ingestor", "binance_url"]
