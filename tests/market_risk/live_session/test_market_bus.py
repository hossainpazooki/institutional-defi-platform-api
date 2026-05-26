"""MarketBus fan-out + backpressure tests."""

from __future__ import annotations

import asyncio

import pytest

from src.market_risk.live_session.market_bus import MarketBus


@pytest.mark.asyncio
async def test_publish_fans_out_to_subscribers() -> None:
    bus = MarketBus(queue_size=8)
    s1 = await bus.subscribe("BTCUSDT")
    s2 = await bus.subscribe("BTCUSDT")
    await bus.publish("BTCUSDT", {"k": 1})
    assert s1.queue.get_nowait() == {"k": 1}
    assert s2.queue.get_nowait() == {"k": 1}


@pytest.mark.asyncio
async def test_publish_to_unsubscribed_symbol_is_noop() -> None:
    bus = MarketBus(queue_size=8)
    await bus.publish("BTCUSDT", {"k": 1})  # should not raise


@pytest.mark.asyncio
async def test_backpressure_drops_newest() -> None:
    bus = MarketBus(queue_size=2)
    s = await bus.subscribe("ETHUSDT")
    for i in range(10):
        await bus.publish("ETHUSDT", {"i": i})
    assert s.dropped >= 8


@pytest.mark.asyncio
async def test_unsubscribe_cleans_symbol_entry() -> None:
    bus = MarketBus()
    s = await bus.subscribe("SOLUSDT")
    assert bus.subscriber_count("SOLUSDT") == 1
    await bus.unsubscribe("SOLUSDT", s)
    assert bus.subscriber_count("SOLUSDT") == 0


@pytest.mark.asyncio
async def test_stream_iterates_messages() -> None:
    bus = MarketBus(queue_size=8)
    received: list[dict[str, int]] = []

    async def consume() -> None:
        async for msg in bus.stream("XRPUSDT"):
            received.append(msg)
            if len(received) == 3:
                break

    consumer = asyncio.create_task(consume())
    # Wait until the subscription is registered before publishing.
    while bus.subscriber_count("XRPUSDT") == 0:
        await asyncio.sleep(0.01)
    for i in range(3):
        await bus.publish("XRPUSDT", {"i": i})
    await consumer
    assert received == [{"i": 0}, {"i": 1}, {"i": 2}]
