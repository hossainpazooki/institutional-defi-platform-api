"""Production startup wiring for the live-session registry.

Called from `src.main.lifespan` only when the feature flag is on. Construction
is lazy — no module-level network/DB clients — and shutdown is idempotent.

Phase 1 stubs still outstanding (documented for follow-up):

- **Boundary rules.** A single hardcoded MiCA-shaped spread-bps boundary is
  loaded. A future slice plumbs the rule loader (`src/rules/`) and selects
  rules whose `cross_border_relevant` flag drives the verdict dispatch path.

What's now real (this slice):

- **Intent resolution** is backed by `IntentRepository.get(intent_id)`. Unknown
  ids return `None` → the registry raises `LookupError` → the WS handler
  emits an error envelope and closes (no more ETHUSDT fallback).
- **Persistence + intents** default to SQL. `LIVE_SESSION_PERSISTENCE=memory`
  swaps both to in-memory implementations for offline demos and tests.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from src.market_risk.live_session.fixture_ingest import FixtureIngestor
from src.market_risk.live_session.ingestor import Ingestor
from src.market_risk.live_session.intent_repository import (
    InMemoryIntentRepository,
    IntentRepository,
    SQLIntentRepository,
)
from src.market_risk.live_session.market_bus import MarketBus
from src.market_risk.live_session.persistence import (
    InMemoryPersistence,
    SessionPersistence,
    SQLModelPersistence,
)
from src.market_risk.live_session.pipeline import PipelineConfig
from src.market_risk.live_session.rationale_streamer import RationaleStreamer
from src.market_risk.live_session.session_manager import (
    reset_session_provider,
    set_session_provider,
)
from src.market_risk.live_session.session_registry import (
    IngestorLike,
    IntentResolver,
    SessionRegistry,
    make_session_provider,
)
from src.market_risk.live_session.threshold_detector import RuleBoundary

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from contextlib import AbstractContextManager

    from fastapi import FastAPI
    from sqlmodel import Session as SQLSession

    from src.market_risk.ws_schemas import TradeIntent

logger = logging.getLogger(__name__)


def _default_boundaries() -> list[RuleBoundary]:
    return [
        RuleBoundary(
            rule_id="mica-spread-50bps",
            citation="MiCA Art. 5(1)",
            boundary=Decimal("50"),
            scalar="spread_bps",
        ),
    ]


def _default_rule_texts() -> dict[str, str]:
    return {
        "mica-spread-50bps": (
            "Spread must not exceed 50 basis points for venue execution."
        ),
    }


# ---------------------------------------------------------------------------
# DB / session factory helpers
# ---------------------------------------------------------------------------


def _make_sql_session_factory() -> Callable[[], AbstractContextManager[SQLSession]]:
    """Build a SQLModel session context-manager factory bound to the app engine."""
    from sqlmodel import Session as SQLSession

    from src.database import get_engine

    @contextmanager
    def _session_cm() -> Iterator[SQLSession]:
        with SQLSession(get_engine()) as s:
            yield s

    return _session_cm


def _build_persistence_and_intent_repo() -> tuple[SessionPersistence, IntentRepository]:
    """Pick both persistence backends together — they share the same engine."""
    if os.environ.get("LIVE_SESSION_PERSISTENCE", "").lower() == "memory":
        logger.info("live_session_persistence: in-memory (env override)")
        return InMemoryPersistence(), InMemoryIntentRepository()

    session_factory = _make_sql_session_factory()
    return (
        SQLModelPersistence(session_factory=session_factory),
        SQLIntentRepository(session_factory=session_factory),
    )


# ---------------------------------------------------------------------------
# Intent resolver — real repo lookup, no ETHUSDT fallback
# ---------------------------------------------------------------------------


def _make_intent_resolver(repo: IntentRepository) -> IntentResolver:
    """Resolver factory — returns the repo-backed lookup as an async callable."""

    async def _resolve(intent_id: str) -> TradeIntent | None:
        return repo.get(intent_id)

    return _resolve


# ---------------------------------------------------------------------------
# Ingestor factories
# ---------------------------------------------------------------------------


def _ingestor_factory_live(bus: MarketBus) -> Callable[[str], IngestorLike]:
    """Returns a factory that hands out a live Binance ingestor per symbol."""

    def _factory(symbol: str) -> IngestorLike:
        # The Ingestor's `acquire(symbol)` is what actually starts a task in
        # the real Binance implementation. For the registry's `start()` /
        # `stop()` Protocol, wrap it in a per-symbol facade.
        ingestor = Ingestor(bus=bus)

        class _PerSymbolFacade:
            def start(self) -> None:
                import asyncio

                self._task = asyncio.create_task(
                    ingestor.acquire(symbol), name=f"live-ingest-acquire-{symbol}"
                )

            async def stop(self) -> None:
                await ingestor.release(symbol)
                await ingestor.shutdown()

        return _PerSymbolFacade()

    return _factory


def _ingestor_factory_demo(bus: MarketBus) -> Callable[[str], IngestorLike]:
    """Returns a fixture-driven factory for demo / offline modes.

    Triggered by env `LIVE_SESSION_INGEST=fixture`. Publishes a small canned
    sequence on first acquire so the demo flow works without Binance reach.
    The fixture is symbol-agnostic — it publishes synthetic frames keyed to
    whatever symbol the registry asks for.
    """

    def _factory(symbol: str) -> IngestorLike:
        frames: list[dict[str, Any]] = [
            {"type": "kline_close", "close": 1800.0},
            {"type": "kline_close", "close": 1802.0},
            {"type": "kline_close", "close": 1801.0},
            {
                "type": "snapshot_inputs",
                "mark": "1800",
                "bid": "1799.91",
                "ask": "1800.09",
                "depth_bid": [["1799.91", "10"]],
                "depth_ask": [["1800.09", "10"]],
                "funding_rate": None,
            },
            {
                "type": "snapshot_inputs",
                "mark": "1800",
                "bid": "1791",
                "ask": "1809",
                "depth_bid": [["1791", "10"]],
                "depth_ask": [["1809", "10"]],
                "funding_rate": None,
            },
        ]
        return FixtureIngestor(
            bus=bus, symbol=symbol, frames=frames, wait_for_subscriber=True
        )

    return _factory


# ---------------------------------------------------------------------------
# Startup / shutdown
# ---------------------------------------------------------------------------


def start_live_session_registry(app: FastAPI) -> SessionRegistry:
    """Build the registry + intent repo, install provider, stash on `app.state`."""
    bus = MarketBus()
    persistence, intent_repo = _build_persistence_and_intent_repo()
    config = PipelineConfig(
        boundaries=_default_boundaries(),
        rule_texts=_default_rule_texts(),
    )

    mode = os.environ.get("LIVE_SESSION_INGEST", "live").lower()
    ingestor_factory = (
        _ingestor_factory_demo(bus) if mode == "fixture" else _ingestor_factory_live(bus)
    )

    registry = SessionRegistry(
        bus=bus,
        config=config,
        persistence=persistence,
        streamer_factory=RationaleStreamer,
        ingestor_factory=ingestor_factory,
        intent_resolver=_make_intent_resolver(intent_repo),
        intent_repository=intent_repo,
    )

    set_session_provider(make_session_provider(registry))
    app.state.live_session_registry = registry
    app.state.intent_repository = intent_repo
    logger.info(
        "live_session_registry_started",
        extra={
            "ingest_mode": mode,
            "persistence": type(persistence).__name__,
            "intent_repo": type(intent_repo).__name__,
        },
    )
    return registry


async def shutdown_live_session_registry(registry: SessionRegistry) -> None:
    """Stop every active session + ingestor, then clear the provider."""
    try:
        await registry.shutdown()
    finally:
        reset_session_provider()
    logger.info("live_session_registry_shutdown")


__all__ = [
    "shutdown_live_session_registry",
    "start_live_session_registry",
]
