"""Round-trip the mock-ws fixtures through the Pydantic envelope adapter."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from src.market_risk.ws_schemas import (
    CrossingDirection,
    MessageType,
    SubscribePayload,
    ThresholdCrossing,
    TickEnvelope,
    TradeSnapshot,
    Verdict,
    WSEnvelopeAdapter,
)

FIXTURE_PATHS = [
    Path(__file__).parents[2] / ".." / "digital-assets-cross-border" / "tools" / "mock-ws" / "fixtures" / name
    for name in ("mica-threshold-crossing.json", "multi-crossing.json", "retraction.json")
]


def _load_fixture(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        pytest.skip(f"Fixture not present in this checkout: {path}")
    with path.open("r", encoding="utf-8") as f:
        return list(json.load(f))


@pytest.mark.parametrize("path", FIXTURE_PATHS, ids=lambda p: p.name)
def test_fixture_envelopes_roundtrip(path: Path) -> None:
    steps = _load_fixture(path)
    for step in steps:
        env = step.get("envelope")
        if env is None or env.get("type") not in {t.value for t in MessageType}:
            continue
        parsed = WSEnvelopeAdapter.model_validate(env)
        round_tripped = json.loads(parsed.model_dump_json())
        assert round_tripped["type"] == env["type"]
        assert round_tripped["seq"] == env["seq"]


def test_tick_envelope_construction() -> None:
    snap = TradeSnapshot(
        intent_id="i-1",
        ts=datetime(2026, 5, 26, 12, 0, tzinfo=UTC),
        mark_price=Decimal("3510.00"),
        bid=Decimal("3509.50"),
        ask=Decimal("3510.50"),
        size=Decimal("1.0"),
        spread_bps=2.85,
        slippage_bps=4.5,
        vol_30d=0.65,
        var_95_usd=1000.0,
        funding_rate=0.0001,
    )
    env = TickEnvelope(seq=1, ts=snap.ts, payload=snap)
    assert env.type == MessageType.TICK
    data = json.loads(env.model_dump_json())
    assert data["payload"]["mark_price"] == "3510.00"


def test_discriminator_rejects_mismatched_payload() -> None:
    from pydantic import ValidationError

    bad = {
        "seq": 1,
        "ts": "2026-05-26T12:00:00Z",
        "type": "subscribe",
        "payload": {"crossing_id": "x"},  # wrong shape for subscribe
    }
    with pytest.raises(ValidationError):
        WSEnvelopeAdapter.model_validate(bad)


def test_subscribe_envelope_minimal() -> None:
    obj = {
        "seq": 0,
        "ts": "2026-05-26T12:00:00Z",
        "type": "subscribe",
        "payload": {"intent_id": "abc"},
    }
    env = WSEnvelopeAdapter.model_validate(obj)
    inner = env.root
    assert inner.type == MessageType.SUBSCRIBE
    assert isinstance(inner.payload, SubscribePayload)
    assert inner.payload.intent_id == "abc"


def test_threshold_crossing_construction() -> None:
    snap = TradeSnapshot(
        intent_id="i-1",
        ts=datetime(2026, 5, 26, tzinfo=UTC),
        mark_price=Decimal("3510"),
        bid=Decimal("3509"),
        ask=Decimal("3511"),
        size=Decimal("1"),
        spread_bps=5.7,
        slippage_bps=4.5,
        vol_30d=0.6,
        var_95_usd=2500.0,
    )
    crossing = ThresholdCrossing(
        crossing_id="c-1",
        intent_id="i-1",
        ts=snap.ts,
        rule_id="mica-art-5",
        citation="MiCA Art. 5(1)",
        boundary=Decimal("5.0"),
        direction=CrossingDirection.UP,
        snapshot=snap,
        prior_verdict=Verdict.COMPLIANT,
        new_verdict=Verdict.CONDITIONAL,
    )
    assert crossing.direction == CrossingDirection.UP
