"""Registry lifecycle + provider wiring tests.

Run with `--noconftest` to avoid the Python 3.14 / FastAPI inspect bug at the
repo conftest layer.
"""

from __future__ import annotations

import os
from decimal import Decimal
from typing import Any

import pytest
from fastapi import FastAPI

# Enable the feature flag before any settings-consumer import.
os.environ["LIVE_THRESHOLD_RATIONALE_ENABLED"] = "true"
# Use in-memory persistence so bootstrap doesn't touch RDS during tests.
os.environ["LIVE_SESSION_PERSISTENCE"] = "memory"
# Use the fixture ingestor so bootstrap doesn't reach Binance.
os.environ["LIVE_SESSION_INGEST"] = "fixture"

from src.config import get_settings  # noqa: E402

get_settings.cache_clear()

from src.market_risk.live_session.bootstrap import (  # noqa: E402
    shutdown_live_session_registry,
    start_live_session_registry,
)
from src.market_risk.live_session.market_bus import MarketBus  # noqa: E402
from src.market_risk.live_session.persistence import InMemoryPersistence  # noqa: E402
from src.market_risk.live_session.pipeline import PipelineConfig  # noqa: E402
from src.market_risk.live_session.rationale_streamer import RationaleStreamer  # noqa: E402
from src.market_risk.live_session.session_manager import (  # noqa: E402
    get_session_provider,
    reset_session_provider,
)
from src.market_risk.live_session.session_registry import (  # noqa: E402
    IngestorLike,
    SessionRegistry,
)
from src.market_risk.live_session.threshold_detector import RuleBoundary  # noqa: E402
from src.market_risk.ws_schemas import (  # noqa: E402
    InvestorType,
    TradeDirection,
    TradeIntent,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_intent(intent_id: str = "intent-reg-1") -> TradeIntent:
    return TradeIntent(
        intent_id=intent_id,
        direction=TradeDirection.BUY,
        asset="ETHUSDT",
        notional_usd=Decimal("500000"),
        venue_jurisdiction="EU",
        investor_type=InvestorType.PROFESSIONAL,
        target_jurisdictions=["EU"],
        holding_period_days=1,
    )


class _CountingIngestor:
    """IngestorLike that records start/stop counts (no actual bus publishing)."""

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.starts = 0
        self.stops = 0

    def start(self) -> None:
        self.starts += 1

    async def stop(self) -> None:
        self.stops += 1


def _build_registry(
    intent: TradeIntent,
    ingestors: dict[str, _CountingIngestor] | None = None,
) -> tuple[SessionRegistry, dict[str, _CountingIngestor]]:
    bus = MarketBus()
    persistence = InMemoryPersistence()
    config = PipelineConfig(
        boundaries=[
            RuleBoundary(
                rule_id="r1",
                citation="MiCA",
                boundary=Decimal("50"),
                scalar="spread_bps",
            )
        ],
        rule_texts={"r1": "spread under 50 bps"},
    )

    created: dict[str, _CountingIngestor] = ingestors if ingestors is not None else {}

    def _factory(symbol: str) -> IngestorLike:
        if symbol not in created:
            created[symbol] = _CountingIngestor(symbol)
        return created[symbol]

    async def _resolver(_id: str) -> TradeIntent | None:
        return intent if _id == intent.intent_id else None

    registry = SessionRegistry(
        bus=bus,
        config=config,
        persistence=persistence,
        streamer_factory=RationaleStreamer,
        ingestor_factory=_factory,
        intent_resolver=_resolver,
    )
    return registry, created


# ---------------------------------------------------------------------------
# 1. Reuse same session for repeated acquires on same intent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_registry_reuses_session_for_same_intent() -> None:
    intent = _make_intent()
    registry, _ingestors = _build_registry(intent)
    try:
        lease_a = await registry.acquire(intent.intent_id)
        lease_b = await registry.acquire(intent.intent_id)
        # Same Session object.
        assert lease_a.session is lease_b.session
        # Refcount is 2.
        assert registry.session_refcount(intent.intent_id) == 2
        await lease_a.release()
        assert registry.session_refcount(intent.intent_id) == 1
        await lease_b.release()
        assert registry.session_refcount(intent.intent_id) == 0
    finally:
        await registry.shutdown()


# ---------------------------------------------------------------------------
# 2. Last release stops the session and removes it from the registry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_registry_stops_session_after_last_release() -> None:
    intent = _make_intent()
    registry, _ingestors = _build_registry(intent)
    try:
        lease = await registry.acquire(intent.intent_id)
        session = lease.session
        # Session is started and consume task is active.
        assert session._consume_task is not None
        assert intent.intent_id in registry.active_intent_ids()

        await lease.release()

        # After the last release, the registry has no entry and the session is stopped.
        assert intent.intent_id not in registry.active_intent_ids()
        # Session.stop() clears the consume task.
        assert session._consume_task is None
    finally:
        await registry.shutdown()


# ---------------------------------------------------------------------------
# 3. App startup wires a non-null provider
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_provider_registered_on_startup() -> None:
    reset_session_provider()
    assert get_session_provider() is None
    app = FastAPI()
    registry = start_live_session_registry(app)
    try:
        assert get_session_provider() is not None
        assert hasattr(app.state, "live_session_registry")
        assert app.state.live_session_registry is registry
        assert hasattr(app.state, "intent_repository")

        # Persist an intent so the real resolver can find it; the provider
        # then returns a lease for it.
        from decimal import Decimal as _D

        from src.market_risk.live_session.intent_repository import (
            CreateIntentParams,
        )
        from src.market_risk.ws_schemas import InvestorType, TradeDirection

        created = app.state.intent_repository.create(
            CreateIntentParams(
                asset="ETHUSDT",
                direction=TradeDirection.BUY,
                notional_usd=_D("100000"),
                venue_jurisdiction="EU",
                investor_type=InvestorType.PROFESSIONAL,
                target_jurisdictions=["EU"],
                holding_period_days=1,
            )
        )

        provider = get_session_provider()
        assert provider is not None
        lease = await provider(created.intent_id)
        assert lease.session.intent.intent_id == created.intent_id
        await lease.release()
    finally:
        await shutdown_live_session_registry(registry)
        # Provider has been cleared.
        assert get_session_provider() is None


# ---------------------------------------------------------------------------
# 4. Shutdown stops active sessions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shutdown_stops_active_sessions() -> None:
    intent_a = _make_intent("intent-shutdown-a")
    intent_b = _make_intent("intent-shutdown-b")
    # Two intents, sharing the same symbol (ETHUSDT) so we also exercise the
    # symbol-ingestor refcount path on shutdown.
    bus = MarketBus()
    persistence = InMemoryPersistence()
    config = PipelineConfig(
        boundaries=[
            RuleBoundary(
                rule_id="r1",
                citation="MiCA",
                boundary=Decimal("50"),
                scalar="spread_bps",
            )
        ],
        rule_texts={"r1": "spread under 50 bps"},
    )
    ingestors: dict[str, _CountingIngestor] = {}

    def _factory(symbol: str) -> IngestorLike:
        if symbol not in ingestors:
            ingestors[symbol] = _CountingIngestor(symbol)
        return ingestors[symbol]

    async def _resolver(_id: str) -> TradeIntent | None:
        return {intent_a.intent_id: intent_a, intent_b.intent_id: intent_b}.get(_id)

    registry = SessionRegistry(
        bus=bus,
        config=config,
        persistence=persistence,
        streamer_factory=RationaleStreamer,
        ingestor_factory=_factory,
        intent_resolver=_resolver,
    )

    lease_a = await registry.acquire(intent_a.intent_id)
    lease_b = await registry.acquire(intent_b.intent_id)
    session_a = lease_a.session
    session_b = lease_b.session
    assert session_a._consume_task is not None
    assert session_b._consume_task is not None

    await registry.shutdown()

    # Both sessions stopped.
    assert session_a._consume_task is None
    assert session_b._consume_task is None
    # Registry rejects further acquires.
    with pytest.raises(RuntimeError):
        await registry.acquire(intent_a.intent_id)
    # Shared symbol ingestor was stopped at least once.
    assert ingestors["ETHUSDT"].stops >= 1


# ---------------------------------------------------------------------------
# 5. Repeated connects do NOT double-start the symbol ingestor
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_repeated_ws_connect_does_not_double_start_ingestor() -> None:
    intent = _make_intent("intent-shared-symbol")
    registry, ingestors = _build_registry(intent)
    try:
        lease_a = await registry.acquire(intent.intent_id)
        lease_b = await registry.acquire(intent.intent_id)
        # Only one ingestor created and only started once.
        assert "ETHUSDT" in ingestors
        assert ingestors["ETHUSDT"].starts == 1
        # And its refcount reflects two acquires.
        assert registry.ingestor_refcount("ETHUSDT") == 2

        # Release one — ingestor still running, refcount drops to 1.
        await lease_a.release()
        assert ingestors["ETHUSDT"].stops == 0
        assert registry.ingestor_refcount("ETHUSDT") == 1

        # Release the last — ingestor stopped exactly once.
        await lease_b.release()
        assert ingestors["ETHUSDT"].stops == 1
        assert registry.ingestor_refcount("ETHUSDT") == 0
    finally:
        await registry.shutdown()


# ---------------------------------------------------------------------------
# 6. Unknown intent raises LookupError (resolver returns None)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_acquire_unknown_intent_raises_lookup() -> None:
    intent = _make_intent("intent-known")
    registry, _ingestors = _build_registry(intent)
    try:
        with pytest.raises(LookupError):
            await registry.acquire("intent-unknown")
    finally:
        await registry.shutdown()


# ---------------------------------------------------------------------------
# 7. Lease.release() is idempotent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lease_release_is_idempotent() -> None:
    intent = _make_intent()
    registry, _ingestors = _build_registry(intent)
    try:
        lease = await registry.acquire(intent.intent_id)
        await lease.release()
        await lease.release()  # second call is a no-op
        assert registry.session_refcount(intent.intent_id) == 0
    finally:
        await registry.shutdown()


# ---------------------------------------------------------------------------
# Final cleanup so module-level provider state doesn't bleed across modules.
# ---------------------------------------------------------------------------


def teardown_module(_module: Any) -> None:
    reset_session_provider()
