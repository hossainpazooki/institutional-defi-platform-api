"""Rationale streamer + NLI gate tests."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

import pytest

from src.market_risk.live_session.nli_gate import _stub_score
from src.market_risk.live_session.rationale_streamer import (
    RationaleEvent,
    RationaleStreamer,
)
from src.market_risk.ws_schemas import (
    CrossingDirection,
    NLIStatus,
    ThresholdCrossing,
    TradeSnapshot,
    Verdict,
)


def _crossing() -> ThresholdCrossing:
    snap = TradeSnapshot(
        intent_id="i-1",
        ts=datetime(2026, 5, 26, tzinfo=UTC),
        mark_price=Decimal("100"),
        bid=Decimal("99"),
        ask=Decimal("101"),
        size=Decimal("1"),
        spread_bps=11.0,
        slippage_bps=4.5,
        vol_30d=0.5,
        var_95_usd=1500.0,
        funding_rate=None,
    )
    return ThresholdCrossing(
        crossing_id="c-1",
        intent_id="i-1",
        ts=snap.ts,
        rule_id="mica-art-5",
        citation="MiCA Art. 5(1)",
        boundary=Decimal("10.0"),
        direction=CrossingDirection.UP,
        snapshot=snap,
        prior_verdict=Verdict.COMPLIANT,
        new_verdict=Verdict.BLOCKED,
    )


async def _factory_good(system: str, user: str) -> AsyncIterator[str]:  # noqa: ARG001
    async def _gen() -> AsyncIterator[str]:
        # Tokens that contain words from the premise so the stub scorer verifies.
        for word in user.split()[:25]:
            yield word + " "

    return _gen()


async def _factory_drift(system: str, user: str) -> AsyncIterator[str]:  # noqa: ARG001
    async def _gen() -> AsyncIterator[str]:
        # 80 tokens of unrelated content so the stub scorer retracts at cadence 50.
        for _ in range(80):
            yield "zzzzz "

    return _gen()


@pytest.mark.asyncio
async def test_stream_emits_tokens_and_terminal_event() -> None:
    s = RationaleStreamer(token_stream_factory=_factory_good)
    out: list[RationaleEvent] = []
    async for ev in s.stream(_crossing()):
        out.append(ev)
    assert any(e.token is not None for e in out)
    terminal = [e for e in out if e.status is not None]
    assert len(terminal) == 1


@pytest.mark.asyncio
async def test_stream_retracts_on_drift() -> None:
    s = RationaleStreamer(token_stream_factory=_factory_drift)
    out: list[RationaleEvent] = []
    async for ev in s.stream(_crossing()):
        out.append(ev)
    terminal = next(e for e in out if e.status is not None)
    assert terminal.status == NLIStatus.RETRACTED


def test_stub_scorer_bounded() -> None:
    s = _stub_score("MiCA boundary spread vol", "MiCA boundary spread vol exact match")
    assert 0.1 <= s <= 0.95


def test_stub_scorer_zero_when_no_overlap() -> None:
    s = _stub_score("rule premise", "completely different content")
    assert s < 0.5


def test_stub_scorer_high_when_full_overlap() -> None:
    p = "the boundary crossed regulatory volatility"
    s = _stub_score(p, p)
    assert s > 0.8
