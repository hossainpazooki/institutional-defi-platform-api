"""WebSocket heartbeat + terminal-intent rejection tests (Phase A).

These tests run with `--noconftest` to avoid the documented Python 3.14 /
FastAPI `inspect.signature(eval_str=True)` regression at the repo conftest
layer (same approach as `test_ws_handler.py`).

Heartbeat cadences are intentionally millisecond-scale, set via env vars that
`Settings` consumes. We clear the `get_settings` lru_cache after setting the
env vars so the WS handler reads our overrides at runtime.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import time
from decimal import Decimal
from typing import Any

import pytest

# Settings overrides BEFORE any consumer imports. Keep heartbeat cadences
# small enough to provoke a real timeout in well under a second.
os.environ["LIVE_THRESHOLD_RATIONALE_ENABLED"] = "true"
os.environ["LIVE_SESSION_PERSISTENCE"] = "memory"
os.environ["LIVE_SESSION_INGEST"] = "fixture"
os.environ["WS_PING_INTERVAL_SECONDS"] = "0.05"
os.environ["WS_PONG_TIMEOUT_SECONDS"] = "0.05"

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from src.config import get_settings  # noqa: E402

get_settings.cache_clear()

from src.market_risk.live_session.bootstrap import (  # noqa: E402
    shutdown_live_session_registry,
    start_live_session_registry,
)
from src.market_risk.live_session.intent_repository import (  # noqa: E402
    CreateIntentParams,
    InMemoryIntentRepository,
)
from src.market_risk.live_session.intents_router import (  # noqa: E402
    router as intents_router,
)
from src.market_risk.live_session.market_bus import MarketBus  # noqa: E402
from src.market_risk.live_session.persistence import InMemoryPersistence  # noqa: E402
from src.market_risk.live_session.pipeline import PipelineConfig  # noqa: E402
from src.market_risk.live_session.rationale_streamer import (  # noqa: E402
    RationaleStreamer,
)
from src.market_risk.live_session.session_manager import (  # noqa: E402
    reset_session_provider,
)
from src.market_risk.live_session.session_registry import (  # noqa: E402
    IngestorLike,
    IntentTerminalError,
    SessionRegistry,
)
from src.market_risk.live_session.threshold_detector import RuleBoundary  # noqa: E402
from src.market_risk.live_session.ws_handler import (  # noqa: E402
    router as ws_router,
)
from src.market_risk.ws_schemas import (  # noqa: E402
    ErrorEnvelope,
    InvestorType,
    MessageType,
    TradeDirection,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _intent_params(asset: str = "ETHUSDT") -> CreateIntentParams:
    return CreateIntentParams(
        asset=asset,
        direction=TradeDirection.BUY,
        notional_usd=Decimal("100000"),
        venue_jurisdiction="EU",
        investor_type=InvestorType.PROFESSIONAL,
        target_jurisdictions=["EU"],
        holding_period_days=1,
    )


def _make_app() -> FastAPI:
    """Mini FastAPI app: intents REST + WS router + bootstrap-wired registry."""
    app = FastAPI()
    app.include_router(intents_router)
    app.include_router(ws_router)
    start_live_session_registry(app)
    return app


def _create_intent(client: TestClient, asset: str = "ETHUSDT") -> str:
    """POST a fresh intent and return its server-generated `intent_id`."""
    resp = client.post(
        "/v2/intents",
        json={
            "asset": asset,
            "direction": "buy",
            "notional_usd": "100000",
            "venue_jurisdiction": "EU",
            "investor_type": "professional",
            "target_jurisdictions": ["EU"],
            "holding_period_days": 1,
        },
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["intent_id"])


def _try_parse_error_envelope(payload: bytes) -> ErrorEnvelope | None:
    """Return the envelope if `payload` decodes as an ErrorEnvelope, else None."""
    try:
        env = ErrorEnvelope.model_validate_json(payload)
    except (ValueError, TypeError):
        return None
    return env if env.type == MessageType.ERROR else None


# ---------------------------------------------------------------------------
# 1. Heartbeat fires `ping` at the configured short interval
# ---------------------------------------------------------------------------


def test_heartbeat_sends_ping_at_configured_interval() -> None:
    """Server must emit a `ping` text frame within a few ws_ping_interval cycles."""
    app = _make_app()
    try:
        with TestClient(app) as client:
            intent_id = _create_intent(client)
            with client.websocket_connect(f"/v2/ws/trade/{intent_id}") as ws:
                deadline = time.monotonic() + 2.0
                saw_ping = False
                # Drain whatever comes — bytes envelopes from fixture frames
                # mixed with text pings. Stop the moment we see the first ping.
                while time.monotonic() < deadline:
                    try:
                        msg = ws.receive()
                    except Exception:  # noqa: BLE001
                        break
                    if msg.get("type") == "websocket.close":
                        break
                    if msg.get("text") == "ping":
                        saw_ping = True
                        break
            assert saw_ping, "expected at least one heartbeat `ping` text frame"
    finally:
        asyncio.run(shutdown_live_session_registry(app.state.live_session_registry))


# ---------------------------------------------------------------------------
# 2. Sending pong keeps the connection alive — no ws_idle_timeout envelope
# ---------------------------------------------------------------------------


def test_pong_prevents_idle_timeout() -> None:
    """While the client answers each `ping` with `pong`, no idle-timeout fires."""
    app = _make_app()
    try:
        with TestClient(app) as client:
            intent_id = _create_intent(client)
            with client.websocket_connect(f"/v2/ws/trade/{intent_id}") as ws:
                deadline = time.monotonic() + 0.6  # ~12 ping intervals
                saw_ping_count = 0
                while time.monotonic() < deadline:
                    try:
                        msg = ws.receive()
                    except Exception:  # noqa: BLE001
                        break
                    if msg.get("type") == "websocket.close":
                        pytest.fail(
                            "server closed while pongs were being delivered — "
                            f"close payload: {msg!r}"
                        )
                    text = msg.get("text")
                    if text == "ping":
                        saw_ping_count += 1
                        ws.send_text("pong")
                        continue
                    raw = msg.get("bytes")
                    if raw is None:
                        continue
                    err = _try_parse_error_envelope(raw)
                    if err is not None and err.payload.code == "ws_idle_timeout":
                        pytest.fail(
                            "idle timeout fired despite pongs being sent — "
                            f"err: {err.payload.message}"
                        )
            assert saw_ping_count >= 1, "expected at least one ping during the window"
    finally:
        asyncio.run(shutdown_live_session_registry(app.state.live_session_registry))


# ---------------------------------------------------------------------------
# 3. Missing pong → ws_idle_timeout envelope, teardown, intent status closed
# ---------------------------------------------------------------------------


def test_missing_pong_times_out_and_marks_intent_closed() -> None:
    """No pong → server emits `ws_idle_timeout`, closes, intent flips to `closed`.

    Also verifies lease release runs exactly once: the registry's `_release`
    only flips status to `closed` on the final refcount drop, so observing
    `status == "closed"` after a single connection proves the lease tore
    down cleanly without double-release (which would log a warning but not
    re-flip status because the repo treats `closed` as terminal).
    """
    app = _make_app()
    repo: InMemoryIntentRepository = app.state.intent_repository
    try:
        with TestClient(app) as client:
            intent_id = _create_intent(client)
            saw_idle_timeout = False
            with client.websocket_connect(f"/v2/ws/trade/{intent_id}") as ws:
                deadline = time.monotonic() + 2.0
                while time.monotonic() < deadline:
                    try:
                        msg = ws.receive()
                    except Exception:  # noqa: BLE001
                        break
                    if msg.get("type") == "websocket.close":
                        break
                    if msg.get("text") == "ping":
                        # Deliberately do not send pong.
                        continue
                    raw = msg.get("bytes")
                    if raw is None:
                        continue
                    err = _try_parse_error_envelope(raw)
                    if err is not None and err.payload.code == "ws_idle_timeout":
                        saw_idle_timeout = True
                        # Continue draining until the server closes so the
                        # `with` block exits cleanly.
                        with contextlib.suppress(Exception):
                            while True:
                                tail = ws.receive()
                                if tail.get("type") == "websocket.close":
                                    break
                        break
            assert saw_idle_timeout, (
                "expected a `ws_idle_timeout` error envelope before close"
            )

            # Intent must end up `closed` once the lease release path runs.
            # Poll briefly to absorb teardown latency.
            for _ in range(80):
                record = repo.get_record(intent_id)
                assert record is not None
                if record.status == "closed":
                    break
                time.sleep(0.025)
            final = repo.get_record(intent_id)
            assert final is not None
            assert final.status == "closed", (
                f"expected intent status `closed` after teardown, got {final.status}"
            )
            assert final.closed_at is not None
    finally:
        asyncio.run(shutdown_live_session_registry(app.state.live_session_registry))


# ---------------------------------------------------------------------------
# 4. Registry rejects acquire() for a closed intent before any Session work
# ---------------------------------------------------------------------------


async def test_registry_acquire_rejects_closed_intent() -> None:
    """`IntentTerminalError` must fire before refcount bump or Session build."""
    repo = InMemoryIntentRepository()
    record = repo.create(_intent_params())
    assert repo.mark_active(record.intent_id) is True
    assert repo.mark_closed(record.intent_id) is True

    build_called = False

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

    class _NeverStartedIngestor:
        def __init__(self, symbol: str) -> None:
            self.symbol = symbol

        def start(self) -> None:  # pragma: no cover - must not be reached
            raise AssertionError(
                "ingestor.start() must not run when acquire rejects a terminal intent"
            )

        async def stop(self) -> None:  # pragma: no cover - must not be reached
            raise AssertionError(
                "ingestor.stop() must not run when acquire rejects a terminal intent"
            )

    def _factory(symbol: str) -> IngestorLike:
        return _NeverStartedIngestor(symbol)

    async def _resolver(intent_id: str) -> Any:
        # The resolver returns a valid TradeIntent — terminal-status guard
        # must fire before this is consulted to short-circuit the path.
        return repo.get(intent_id)

    registry = SessionRegistry(
        bus=bus,
        config=config,
        persistence=persistence,
        streamer_factory=RationaleStreamer,
        ingestor_factory=_factory,
        intent_resolver=_resolver,
        intent_repository=repo,
    )

    # Patch _build_session so a regression that bypasses the guard would
    # surface as a clear AssertionError rather than a silent success.
    original_build = registry._build_session

    def _spy_build(intent: Any) -> Any:
        nonlocal build_called
        build_called = True
        return original_build(intent)

    registry._build_session = _spy_build  # type: ignore[method-assign]

    try:
        with pytest.raises(IntentTerminalError) as excinfo:
            await registry.acquire(record.intent_id)
        assert excinfo.value.status == "closed"
        assert excinfo.value.intent_id == record.intent_id
        assert build_called is False
        assert registry.session_refcount(record.intent_id) == 0
        assert registry.ingestor_refcount("ETHUSDT") == 0

        # `failed` is also terminal.
        record2 = repo.create(_intent_params())
        assert repo.mark_failed(record2.intent_id, "synthetic") is True
        with pytest.raises(IntentTerminalError) as excinfo2:
            await registry.acquire(record2.intent_id)
        assert excinfo2.value.status == "failed"
    finally:
        await registry.shutdown()


# ---------------------------------------------------------------------------
# 5. WS handler maps IntentTerminalError to `intent_terminal` error envelope
# ---------------------------------------------------------------------------


def test_ws_emits_intent_terminal_for_closed_intent() -> None:
    """Connecting to a closed intent_id → error envelope code='intent_terminal'."""
    app = _make_app()
    repo: InMemoryIntentRepository = app.state.intent_repository
    try:
        with TestClient(app) as client:
            intent_id = _create_intent(client)
            # Force terminal state without running a session.
            assert repo.mark_active(intent_id) is True
            assert repo.mark_closed(intent_id) is True
            assert repo.get_record(intent_id) is not None
            assert repo.get_record(intent_id).status == "closed"  # type: ignore[union-attr]

            saw_intent_terminal = False
            with client.websocket_connect(f"/v2/ws/trade/{intent_id}") as ws:
                deadline = time.monotonic() + 1.0
                while time.monotonic() < deadline:
                    try:
                        msg = ws.receive()
                    except Exception:  # noqa: BLE001
                        break
                    if msg.get("type") == "websocket.close":
                        break
                    raw = msg.get("bytes")
                    if raw is None:
                        continue
                    err = _try_parse_error_envelope(raw)
                    if err is not None and err.payload.code == "intent_terminal":
                        saw_intent_terminal = True
                        break
            assert saw_intent_terminal, (
                "expected `intent_terminal` error envelope on closed-intent connect"
            )
    finally:
        asyncio.run(shutdown_live_session_registry(app.state.live_session_registry))


# ---------------------------------------------------------------------------
# Module-level cleanup so module provider state doesn't bleed.
# ---------------------------------------------------------------------------


def teardown_module(_module: Any) -> None:
    reset_session_provider()
