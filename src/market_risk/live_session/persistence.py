"""Persistence interface for the live-session pipeline.

A narrow Protocol so the pipeline doesn't import SQLModel. Two implementations:

- `InMemoryPersistence` — collects rows as plain dataclasses; used by unit /
  integration tests. Decoupled from SQLModel so it works on Python 3.14 where
  the SQLModel table=True classes hit an `inspect`/`issubclass` regression.
- `SQLModelPersistence` — writes ORM rows via a SQLModel `Session`. SQLModel
  imports are local-deferred to keep the pipeline import path light.

Both implementations are append-only and synchronous (the rows are small and
writes are off the verdict critical path — the WS envelope for a verdict is
emitted before persistence completes).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractContextManager
    from decimal import Decimal

    from sqlmodel import Session as SQLSession

    from src.market_risk.ws_schemas import (
        Rationale,
        ThresholdCrossing,
        TradeSnapshot,
    )

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Plain row types — independent of SQLModel so the in-memory path doesn't
# trigger the Python 3.14 / SQLModel issue. SQLModelPersistence translates
# these to the ORM rows in `.models`.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SnapshotRow:
    intent_id: str
    ts: datetime
    mark_price: Decimal
    bid: Decimal
    ask: Decimal
    size: Decimal
    spread_bps: float
    slippage_bps: float
    vol_30d: float
    var_95_usd: float
    funding_rate: float | None


@dataclass(frozen=True)
class CrossingRow:
    crossing_id: str
    intent_id: str
    ts: datetime
    rule_id: str
    citation: str
    boundary: Decimal
    direction: str
    prior_verdict: str
    new_verdict: str


@dataclass(frozen=True)
class RationaleRowDC:
    rationale_id: str
    crossing_id: str
    intent_id: str
    ts: datetime
    content: str
    status: str
    final_score: float | None
    retraction_reason: str | None
    completed_at: datetime | None


@dataclass(frozen=True)
class NLICheckRowDC:
    nli_check_id: str
    rationale_id: str
    intent_id: str
    ts: datetime
    token_offset: int
    entailment_score: float


class SessionPersistence(Protocol):
    """Narrow append-only persistence interface for the live session.

    Implementations must not raise on the happy path — failures are logged by
    the pipeline and degrade to "audit-incomplete" without breaking the WS feed.
    """

    def record_snapshot(self, snapshot: TradeSnapshot) -> None: ...

    def record_crossing(self, crossing: ThresholdCrossing) -> None: ...

    def record_rationale(self, rationale: Rationale, intent_id: str) -> None: ...

    def record_nli_check(
        self,
        *,
        nli_check_id: str,
        rationale_id: str,
        intent_id: str,
        ts: datetime,
        token_offset: int,
        entailment_score: float,
    ) -> None: ...


@dataclass
class InMemoryPersistence:
    """Test/dev implementation — keeps rows in lists for assertion."""

    snapshots: list[SnapshotRow] = field(default_factory=list)
    crossings: list[CrossingRow] = field(default_factory=list)
    rationales: list[RationaleRowDC] = field(default_factory=list)
    nli_checks: list[NLICheckRowDC] = field(default_factory=list)

    def record_snapshot(self, snapshot: TradeSnapshot) -> None:
        self.snapshots.append(
            SnapshotRow(
                intent_id=snapshot.intent_id,
                ts=snapshot.ts,
                mark_price=snapshot.mark_price,
                bid=snapshot.bid,
                ask=snapshot.ask,
                size=snapshot.size,
                spread_bps=snapshot.spread_bps,
                slippage_bps=snapshot.slippage_bps,
                vol_30d=snapshot.vol_30d,
                var_95_usd=snapshot.var_95_usd,
                funding_rate=snapshot.funding_rate,
            )
        )

    def record_crossing(self, crossing: ThresholdCrossing) -> None:
        self.crossings.append(
            CrossingRow(
                crossing_id=crossing.crossing_id,
                intent_id=crossing.intent_id,
                ts=crossing.ts,
                rule_id=crossing.rule_id,
                citation=crossing.citation,
                boundary=crossing.boundary,
                direction=crossing.direction.value,
                prior_verdict=crossing.prior_verdict.value,
                new_verdict=crossing.new_verdict.value,
            )
        )

    def record_rationale(self, rationale: Rationale, intent_id: str) -> None:
        ts = rationale.completed_at or datetime.now(tz=UTC)
        self.rationales.append(
            RationaleRowDC(
                rationale_id=rationale.rationale_id,
                crossing_id=rationale.crossing_id,
                intent_id=intent_id,
                ts=ts,
                content=rationale.content,
                status=rationale.status.value,
                final_score=rationale.final_score,
                retraction_reason=rationale.retraction_reason,
                completed_at=rationale.completed_at,
            )
        )

    def record_nli_check(
        self,
        *,
        nli_check_id: str,
        rationale_id: str,
        intent_id: str,
        ts: datetime,
        token_offset: int,
        entailment_score: float,
    ) -> None:
        self.nli_checks.append(
            NLICheckRowDC(
                nli_check_id=nli_check_id,
                rationale_id=rationale_id,
                intent_id=intent_id,
                ts=ts,
                token_offset=token_offset,
                entailment_score=entailment_score,
            )
        )


@dataclass
class SQLModelPersistence:
    """Production implementation — writes via a fresh SQLModel session per call.

    SQLModel row imports are local-deferred so import of this module on
    Python 3.14 doesn't trigger SQLModel's class-construction regression
    until the production code actually instantiates rows.

    Errors are swallowed and logged so the live WS feed survives a DB blip.
    """

    session_factory: Callable[[], AbstractContextManager[SQLSession]]

    def _write(self, row: object) -> None:
        try:
            with self.session_factory() as s:
                s.add(row)
                s.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("persistence_write_failed", extra={"error": str(exc)})

    def record_snapshot(self, snapshot: TradeSnapshot) -> None:
        from .models import TradeSnapshotRow

        self._write(
            TradeSnapshotRow(
                intent_id=snapshot.intent_id,
                ts=snapshot.ts,
                mark_price=snapshot.mark_price,
                bid=snapshot.bid,
                ask=snapshot.ask,
                size=snapshot.size,
                spread_bps=snapshot.spread_bps,
                slippage_bps=snapshot.slippage_bps,
                vol_30d=snapshot.vol_30d,
                var_95_usd=snapshot.var_95_usd,
                funding_rate=snapshot.funding_rate,
            )
        )

    def record_crossing(self, crossing: ThresholdCrossing) -> None:
        from .models import ThresholdEventRow

        self._write(
            ThresholdEventRow(
                crossing_id=crossing.crossing_id,
                intent_id=crossing.intent_id,
                ts=crossing.ts,
                rule_id=crossing.rule_id,
                citation=crossing.citation,
                boundary=crossing.boundary,
                direction=crossing.direction.value,
                prior_verdict=crossing.prior_verdict.value,
                new_verdict=crossing.new_verdict.value,
            )
        )

    def record_rationale(self, rationale: Rationale, intent_id: str) -> None:
        from .models import RationaleRow

        ts = rationale.completed_at or datetime.now(tz=UTC)
        self._write(
            RationaleRow(
                rationale_id=rationale.rationale_id,
                crossing_id=rationale.crossing_id,
                intent_id=intent_id,
                ts=ts,
                content=rationale.content,
                status=rationale.status.value,
                final_score=rationale.final_score,
                retraction_reason=rationale.retraction_reason,
                completed_at=rationale.completed_at,
            )
        )

    def record_nli_check(
        self,
        *,
        nli_check_id: str,
        rationale_id: str,
        intent_id: str,
        ts: datetime,
        token_offset: int,
        entailment_score: float,
    ) -> None:
        from .models import NLICheckRow

        self._write(
            NLICheckRow(
                nli_check_id=nli_check_id,
                rationale_id=rationale_id,
                intent_id=intent_id,
                ts=ts,
                token_offset=token_offset,
                entailment_score=entailment_score,
            )
        )


__all__ = [
    "CrossingRow",
    "InMemoryPersistence",
    "NLICheckRowDC",
    "RationaleRowDC",
    "SQLModelPersistence",
    "SessionPersistence",
    "SnapshotRow",
]
