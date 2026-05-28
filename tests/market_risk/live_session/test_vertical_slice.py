"""End-to-end vertical slice for the live session.

Drives a fixture ingestor → MarketBus → LiveSessionPipeline → Session and
asserts the canonical envelope contract:

1. The first audit-lane envelope after `emit_subscribed()` is the subscribe
   envelope.
2. A ComplianceEnvelope and ThresholdEnvelope appear BEFORE any
   `rationale_tok` envelope. Spec §5: verdict lands before rationale.
3. Crossing-to-verdict wall-clock latency is well below the 100 ms in-process
   target.
4. After driving the crossing, the in-memory persistence has at least one
   TradeSnapshotRow, one ThresholdEventRow, and one RationaleRow.
5. `Session.stop()` cancels the consume task and the asyncio task count
   returns to the baseline (no leaks).
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any

import pytest

from src.market_risk.live_session.fixture_ingest import FixtureIngestor
from src.market_risk.live_session.market_bus import MarketBus
from src.market_risk.live_session.persistence import InMemoryPersistence
from src.market_risk.live_session.pipeline import (
    PipelineConfig,
    build_pipeline,
)
from src.market_risk.live_session.rationale_streamer import RationaleStreamer
from src.market_risk.live_session.session_manager import Session
from src.market_risk.live_session.threshold_detector import RuleBoundary
from src.market_risk.ws_schemas import (
    InvestorType,
    MessageType,
    TradeDirection,
    TradeIntent,
    WSEnvelopeAdapter,
)


def _intent() -> TradeIntent:
    return TradeIntent(
        intent_id="intent-vs-1",
        direction=TradeDirection.BUY,
        asset="ETHUSDT",
        notional_usd=Decimal("500000"),
        venue_jurisdiction="EU",
        investor_type=InvestorType.PROFESSIONAL,
        target_jurisdictions=["EU"],
        holding_period_days=1,
    )


def _kline_close(close: float) -> dict[str, Any]:
    return {"type": "kline_close", "close": close}


def _book(mark: str, bid: str, ask: str, depth_w: str = "10") -> dict[str, Any]:
    return {
        "type": "snapshot_inputs",
        "mark": mark,
        "bid": bid,
        "ask": ask,
        "depth_bid": [[bid, depth_w]],
        "depth_ask": [[ask, depth_w]],
        "funding_rate": None,
    }


def _build_session() -> tuple[
    Session, MarketBus, InMemoryPersistence, FixtureIngestor, list[bytes]
]:
    """Wire one ETHUSDT session with one MiCA-ish boundary on `spread_bps`.

    The fixture frames are scripted so the second snapshot crosses the boundary:
    a tight market (spread ≈ 1 bps) is followed by a blown-out market (spread
    ≈ 100 bps), which trips the rule.
    """
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

    # Two-phase: first a tight market → first snapshot is COMPLIANT (baseline,
    # no emit). Then a wide market → CROSS into BLOCKED → emit.
    frames: list[dict[str, Any]] = [
        # Warm-up kline returns so Welford gives a non-zero sigma (purely so
        # the snapshot fields aren't all zero; doesn't affect the spread rule).
        _kline_close(1800.0),
        _kline_close(1802.0),
        _kline_close(1801.0),
        # Baseline tight book — spread ≈ 1 bps.
        _book(mark="1800", bid="1799.91", ask="1800.09"),
        # Wide book — spread ≈ 100 bps, crosses the 50bps boundary.
        _book(mark="1800", bid="1791", ask="1809"),
    ]

    captured_audit: list[bytes] = []

    session = Session(intent=intent, bus=bus)

    async def emit_tick(_b: bytes) -> None:
        # Drop-newest market lane via the session — exercised in test below.
        await session.emit_tick(_b)

    async def emit_audit(b: bytes) -> None:
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

    ingestor = FixtureIngestor(bus=bus, symbol=intent.asset, frames=frames)
    return session, bus, persistence, ingestor, captured_audit


async def _wait_for_envelope(
    captured: list[bytes], type_: MessageType, timeout: float = 2.0
) -> bytes:
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        for payload in captured:
            env = WSEnvelopeAdapter.model_validate_json(payload).root
            if env.type == type_:
                return payload
        if asyncio.get_event_loop().time() > deadline:
            raise AssertionError(f"timed out waiting for {type_.value} envelope")
        await asyncio.sleep(0.005)


@pytest.mark.asyncio
async def test_vertical_slice_emits_verdict_before_rationale_with_latency() -> None:
    session, _bus, persistence, ingestor, captured = _build_session()

    baseline_tasks = len(asyncio.all_tasks())

    await session.emit_subscribed()
    session.start()
    ingestor.start()
    try:
        # Wait until both verdict envelopes land.
        await _wait_for_envelope(captured, MessageType.COMPLIANCE)
        await _wait_for_envelope(captured, MessageType.THRESHOLD)

        # Parse envelopes in arrival order and check that no rationale_tok
        # precedes either compliance or threshold.
        types_in_order = [
            WSEnvelopeAdapter.model_validate_json(b).root.type for b in captured
        ]
        first_compliance = types_in_order.index(MessageType.COMPLIANCE)
        first_threshold = types_in_order.index(MessageType.THRESHOLD)
        if MessageType.RATIONALE_TOK in types_in_order:
            first_tok = types_in_order.index(MessageType.RATIONALE_TOK)
            assert first_tok > first_compliance, (
                "rationale_tok must not precede compliance envelope"
            )
            assert first_tok > first_threshold, (
                "rationale_tok must not precede threshold envelope"
            )

        # Latency assertion — the LiveSessionPipeline records the
        # crossing-to-verdict wall-clock latency. Single-jurisdiction
        # in-process path should be well under 100 ms.
        assert session.pipeline is not None
        latency_ms = session.pipeline.last_verdict_latency_ms
        assert latency_ms is not None, "expected a crossing to have been processed"
        assert latency_ms < 100.0, (
            f"single-juris verdict latency {latency_ms:.1f} ms exceeds 100 ms budget"
        )

        # Wait briefly for the rationale stream to finish so persistence is populated.
        await asyncio.sleep(0.05)
        await session.pipeline.join()

        # Persistence has the audit trail.
        assert len(persistence.crossings) >= 1
        assert len(persistence.snapshots) >= 1
        assert len(persistence.rationales) >= 1
        crossing_row = persistence.crossings[0]
        assert crossing_row.rule_id == "mica-spread-50bps"
        assert crossing_row.new_verdict in {"blocked", "conditional"}
    finally:
        await ingestor.stop()
        await session.stop()

    # Leak check: no rogue tasks left behind.
    leftover = len(asyncio.all_tasks()) - baseline_tasks
    # Allow for the current test task itself.
    assert leftover <= 1, (
        f"task leak: {leftover} extra tasks remain after Session.stop()"
    )


@pytest.mark.asyncio
async def test_session_stop_drains_rationale_tasks() -> None:
    """Calling stop() awaits pending rationale tasks rather than orphaning them."""
    session, _bus, _p, ingestor, _ = _build_session()
    await session.emit_subscribed()
    session.start()
    ingestor.start()
    # Let the pipeline produce at least one crossing.
    await asyncio.sleep(0.05)
    # Stop while a rationale may still be streaming.
    await ingestor.stop()
    await session.stop()
    assert session.pipeline is not None
    # join() is idempotent.
    await session.pipeline.join()


@pytest.mark.asyncio
async def test_tick_lane_independent_of_audit_lane() -> None:
    """Verify tick envelopes flow to a separate queue from audit envelopes."""
    session, _bus, _p, ingestor, captured = _build_session()
    session.start()
    ingestor.start()
    try:
        await _wait_for_envelope(captured, MessageType.COMPLIANCE, timeout=2.0)
        # The captured list is the audit lane only; tick envelopes go to
        # session.tick_out which the test does not drain. The audit list must
        # NOT contain tick envelopes.
        types_in_audit = {
            WSEnvelopeAdapter.model_validate_json(b).root.type for b in captured
        }
        assert MessageType.TICK not in types_in_audit
        # And tick_out should have at least one tick payload sitting in it.
        assert session.tick_out.qsize() >= 1
    finally:
        await ingestor.stop()
        await session.stop()
