"""WebSocket handler tests — priority merge, end-to-end visibility, disconnect cleanup.

Notes on test app construction:

The repo-level `tests/conftest.py` imports `src.main` which triggers the
documented Python 3.14 / FastAPI `inspect.signature(eval_str=True)`
regression. We deliberately do not import `src.main` here; instead we build
a minimal FastAPI app with only the live-session WS router registered. Tests
run with `--noconftest`.
"""

from __future__ import annotations

import asyncio
import os
from decimal import Decimal
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Enable the feature flag BEFORE importing get_settings consumers.
os.environ["LIVE_THRESHOLD_RATIONALE_ENABLED"] = "true"

from src.config import get_settings  # noqa: E402

get_settings.cache_clear()

from src.market_risk.live_session.fixture_ingest import FixtureIngestor  # noqa: E402
from src.market_risk.live_session.market_bus import MarketBus  # noqa: E402
from src.market_risk.live_session.persistence import InMemoryPersistence  # noqa: E402
from src.market_risk.live_session.pipeline import (  # noqa: E402
    PipelineConfig,
    build_pipeline,
)
from src.market_risk.live_session.rationale_streamer import RationaleStreamer  # noqa: E402
from src.market_risk.live_session.session_manager import (  # noqa: E402
    Session,
    set_session_provider,
)
from src.market_risk.live_session.threshold_detector import RuleBoundary  # noqa: E402
from src.market_risk.live_session.ws_handler import _run_sender, router  # noqa: E402
from src.market_risk.ws_schemas import (  # noqa: E402
    InvestorType,
    MessageType,
    TradeDirection,
    TradeIntent,
    WSEnvelopeAdapter,
)

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _intent() -> TradeIntent:
    return TradeIntent(
        intent_id="intent-ws-1",
        direction=TradeDirection.BUY,
        asset="ETHUSDT",
        notional_usd=Decimal("500000"),
        venue_jurisdiction="EU",
        investor_type=InvestorType.PROFESSIONAL,
        target_jurisdictions=["EU"],
        holding_period_days=1,
    )


def _kline(close: float) -> dict[str, Any]:
    return {"type": "kline_close", "close": close}


def _book(mark: str, bid: str, ask: str) -> dict[str, Any]:
    return {
        "type": "snapshot_inputs",
        "mark": mark,
        "bid": bid,
        "ask": ask,
        "depth_bid": [[bid, "10"]],
        "depth_ask": [[ask, "10"]],
        "funding_rate": None,
    }


def _fixture_frames() -> list[dict[str, Any]]:
    return [
        _kline(1800.0),
        _kline(1802.0),
        _kline(1801.0),
        _book(mark="1800", bid="1799.91", ask="1800.09"),  # tight, baseline
        _book(mark="1800", bid="1791", ask="1809"),  # wide, crosses
    ]


class _FakeWebSocket:
    """In-memory stand-in for FastAPI's WebSocket with the methods _run_sender uses."""

    def __init__(self) -> None:
        self.sent: list[bytes] = []
        self.closed = False

    async def send_bytes(self, b: bytes) -> None:
        if self.closed:
            raise RuntimeError("closed")
        self.sent.append(b)

    async def send_text(self, s: str) -> None:
        if self.closed:
            raise RuntimeError("closed")
        self.sent.append(s.encode())

    async def close(self) -> None:
        self.closed = True


def _build_session(
    captured_audit: list[bytes] | None = None,
) -> tuple[Session, MarketBus, InMemoryPersistence, FixtureIngestor]:
    bus = MarketBus(queue_size=32)
    intent = _intent()
    persistence = InMemoryPersistence()

    rule = RuleBoundary(
        rule_id="mica-spread-50bps",
        citation="MiCA Art. 5(1)",
        boundary=Decimal("50"),
        scalar="spread_bps",
    )
    config = PipelineConfig(
        boundaries=[rule],
        rule_texts={
            "mica-spread-50bps": (
                "Spread must not exceed 50 basis points for venue execution."
            )
        },
    )
    streamer = RationaleStreamer(rule_text_lookup=lambda rid: config.rule_texts.get(rid, ""))

    session = Session(intent=intent, bus=bus)

    async def emit_tick(b: bytes) -> None:
        await session.emit_tick(b)

    async def emit_audit(b: bytes) -> None:
        if captured_audit is not None:
            captured_audit.append(b)
        await session.emit_audit(b)

    pipeline = build_pipeline(
        intent=intent,
        config=config,
        persistence=persistence,
        streamer=streamer,
        next_seq=session.next_seq,
        emit_tick=emit_tick,
        emit_audit=emit_audit,
    )
    session.pipeline = pipeline
    ingestor = FixtureIngestor(
        bus=bus,
        symbol=intent.asset,
        frames=_fixture_frames(),
        wait_for_subscriber=True,
    )
    return session, bus, persistence, ingestor


# ---------------------------------------------------------------------------
# 1. Unit test on the priority-merge sender.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ws_drains_audit_before_tick() -> None:
    """Both queues seeded; sender must emit all audit bytes before any tick."""
    session, _bus, _p, _ing = _build_session()
    # Pre-fill both lanes.
    for i in range(3):
        await session.audit_out.put(f"audit-{i}".encode())
    for i in range(3):
        # tick lane uses drop-newest via emit_tick; direct put_nowait keeps it
        # explicit and bounded.
        session.tick_out.put_nowait(f"tick-{i}".encode())

    import contextlib

    fake = _FakeWebSocket()
    sender = asyncio.create_task(_run_sender(cast("Any", fake), session))
    try:
        # Wait until at least 4 sends have happened (3 audits + 1 tick).
        for _ in range(200):
            if len(fake.sent) >= 4:
                break
            await asyncio.sleep(0.005)
    finally:
        sender.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await sender

    # First three must be the audit envelopes in FIFO order.
    assert fake.sent[:3] == [b"audit-0", b"audit-1", b"audit-2"]
    # Then a tick.
    assert fake.sent[3].startswith(b"tick-")


# ---------------------------------------------------------------------------
# 2. End-to-end through the FastAPI WS endpoint via TestClient.
# ---------------------------------------------------------------------------


def _make_test_app(session: Session, ingestor: FixtureIngestor) -> FastAPI:
    """Mini FastAPI app with only the live-session WS router.

    We don't import src.main (which trips the Py 3.14 / FastAPI bug). The
    session provider returns a SessionLease wrapping the pre-built session;
    the lease's release call falls through to `session.stop()` so existing
    teardown semantics are preserved.
    """
    from src.market_risk.live_session.session_registry import SessionLease

    app = FastAPI()
    app.include_router(router)

    started = False

    async def provider(_intent_id: str) -> SessionLease:
        nonlocal started
        if not started:
            ingestor.start()
            started = True

        async def _release() -> None:
            await session.stop()

        return SessionLease(session=session, _release=_release)

    set_session_provider(provider)
    return app


@pytest.mark.asyncio
async def test_ws_vertical_slice_visible_from_endpoint() -> None:
    """Open the WS, expect subscribe + tick + compliance + threshold envelopes."""
    captured_audit: list[bytes] = []
    session, _bus, persistence, ingestor = _build_session(captured_audit)
    app = _make_test_app(session, ingestor)

    received: list[bytes] = []
    try:
        with TestClient(app) as client, client.websocket_connect(
            "/v2/ws/trade/intent-ws-1"
        ) as ws:
            # Read up to ~15 envelopes or until both compliance + threshold seen.
            deadline = asyncio.get_event_loop().time() + 5.0
            saw_compliance = False
            saw_threshold = False
            saw_tick = False
            while asyncio.get_event_loop().time() < deadline:
                try:
                    msg = ws.receive_bytes()
                except Exception:  # noqa: BLE001
                    break
                received.append(msg)
                env = WSEnvelopeAdapter.model_validate_json(msg).root
                if env.type == MessageType.TICK:
                    saw_tick = True
                if env.type == MessageType.COMPLIANCE:
                    saw_compliance = True
                if env.type == MessageType.THRESHOLD:
                    saw_threshold = True
                if saw_compliance and saw_threshold and saw_tick:
                    break
            assert saw_compliance, "expected at least one compliance envelope"
            assert saw_threshold, "expected at least one threshold envelope"
            assert saw_tick, "expected at least one tick envelope"

        # Persistence has the audit trail.
        await asyncio.sleep(0.05)  # let rationale finish + persist
        assert len(persistence.crossings) >= 1
        assert len(persistence.snapshots) >= 1
    finally:
        await ingestor.stop()
        # Provider cleanup so the next test gets its own session.
        set_session_provider(None)


# ---------------------------------------------------------------------------
# 3. Disconnect cleans up the session.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ws_disconnect_stops_session() -> None:
    """Client disconnect should cancel the consume task and await rationale tasks."""
    captured_audit: list[bytes] = []
    session, _bus, _persistence, ingestor = _build_session(captured_audit)
    app = _make_test_app(session, ingestor)

    try:
        with TestClient(app) as client, client.websocket_connect(
            "/v2/ws/trade/intent-ws-1"
        ) as ws:
            # Read enough to ensure session is running and at least one envelope flowed.
            _ = ws.receive_bytes()
            # Disconnect.
        # Give the server-side teardown a moment to run.
        await asyncio.sleep(0.2)
        # Consume task should have been cancelled by Session.stop().
        assert session._consume_task is None, (
            "session consume task not cleared after disconnect"
        )
        assert session.pipeline is not None
        # No in-flight rationale tasks should be hanging on the pipeline.
        assert len(session.pipeline._rationale_tasks) == 0, (
            "rationale tasks not drained on shutdown"
        )
    finally:
        await ingestor.stop()
        set_session_provider(None)


# ---------------------------------------------------------------------------
# 4. Verdict-before-rationale ordering visible to the client.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ws_verdict_before_rationale_tok() -> None:
    """Client must observe COMPLIANCE/THRESHOLD before any RATIONALE_TOK envelope."""
    captured_audit: list[bytes] = []
    session, _bus, _persistence, ingestor = _build_session(captured_audit)
    app = _make_test_app(session, ingestor)

    received_types: list[MessageType] = []
    try:
        with TestClient(app) as client, client.websocket_connect(
            "/v2/ws/trade/intent-ws-1"
        ) as ws:
            deadline = asyncio.get_event_loop().time() + 5.0
            while asyncio.get_event_loop().time() < deadline:
                try:
                    msg = ws.receive_bytes()
                except Exception:  # noqa: BLE001
                    break
                env = WSEnvelopeAdapter.model_validate_json(msg).root
                received_types.append(env.type)
                # Stop once we've seen at least one rationale envelope (tok or terminal).
                if env.type in {
                    MessageType.RATIONALE_TOK,
                    MessageType.RATIONALE_VERIFIED,
                    MessageType.RATIONALE_RETRACTED,
                }:
                    break
    finally:
        await ingestor.stop()
        set_session_provider(None)

    if MessageType.RATIONALE_TOK in received_types:
        first_tok = received_types.index(MessageType.RATIONALE_TOK)
        assert MessageType.COMPLIANCE in received_types[:first_tok], (
            "compliance envelope did not precede rationale_tok"
        )
        assert MessageType.THRESHOLD in received_types[:first_tok], (
            "threshold envelope did not precede rationale_tok"
        )
    else:
        # If no rationale_tok arrived within window we still want the verdict
        # ordering to have been established before any terminal rationale.
        terminal_set = {
            MessageType.RATIONALE_VERIFIED,
            MessageType.RATIONALE_RETRACTED,
        }
        terminal_idx = next(
            (i for i, t in enumerate(received_types) if t in terminal_set), None
        )
        if terminal_idx is not None:
            assert MessageType.COMPLIANCE in received_types[:terminal_idx]
            assert MessageType.THRESHOLD in received_types[:terminal_idx]


# ---------------------------------------------------------------------------
# 5. Sanity: provider unconfigured → endpoint closes politely.
# ---------------------------------------------------------------------------


def test_ws_no_provider_closes_cleanly() -> None:
    """Without a session provider configured, the endpoint must not 500."""
    app = FastAPI()
    app.include_router(router)
    set_session_provider(None)
    try:
        with (
            TestClient(app) as client,
            pytest.raises(Exception),  # noqa: B017, PT011
            client.websocket_connect("/v2/ws/trade/x"),
        ):
            # WebSocketDisconnect or similar — TestClient raises on close.
            pass
    finally:
        set_session_provider(None)
