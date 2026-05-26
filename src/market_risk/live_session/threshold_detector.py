"""Threshold detector — emits ThresholdCrossing whenever a snapshot crosses a
rule-defined regulatory boundary.

Uses a precomputed `boundary_index: dict[Bucket, list[RuleId]]` from the rules
loader to short-list candidate rules per snapshot. The full evaluation against
the compiled IR runs only on the short-list.

See spec §4.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from src.market_risk.ws_schemas import (
    CrossingDirection,
    ThresholdCrossing,
    TradeSnapshot,
    Verdict,
)

from .zone_hash import BucketWidths, bucket_for

if TYPE_CHECKING:
    from collections.abc import Iterable

    from .zone_hash import ZoneHash


@dataclass(frozen=True)
class RuleBoundary:
    """A single regulatory boundary that a snapshot scalar may cross."""

    rule_id: str
    citation: str
    boundary: Decimal
    # Field on the snapshot the boundary applies to. Limited to numeric attrs:
    # "spread_bps" | "slippage_bps" | "vol_30d" | "var_95_usd" | "mark_price".
    scalar: str


VerdictPredicate = Callable[[TradeSnapshot, RuleBoundary], Verdict]


def _get_scalar(snapshot: TradeSnapshot, name: str) -> Decimal:
    """Pull a numeric scalar off the snapshot as Decimal for comparison."""
    if name in {"mark_price", "bid", "ask", "size"}:
        return Decimal(str(getattr(snapshot, name)))
    return Decimal(str(getattr(snapshot, name)))


@dataclass
class ThresholdDetector:
    """Stateful crossing detector for one session.

    Tracks the last known verdict per (rule_id) so we only emit on *transitions*
    rather than every tick. The verdict resolver is injected; this lets B5's
    VerdictService own the decision logic without B4 importing it.
    """

    boundaries: list[RuleBoundary]
    verdict_for: VerdictPredicate
    widths: BucketWidths = field(default_factory=BucketWidths)
    _last_verdict: dict[str, Verdict] = field(default_factory=dict)
    _last_zone: ZoneHash | None = None

    def detect(
        self,
        snapshot: TradeSnapshot,
        *,
        notional_usd: float,
        position_pct: float,
    ) -> list[ThresholdCrossing]:
        zone = bucket_for(
            snapshot, notional_usd=notional_usd, position_pct=position_pct, widths=self.widths
        )
        # Fast-path: same zone as last tick, no boundary could have flipped.
        if zone == self._last_zone and self._last_verdict:
            return []
        self._last_zone = zone

        return list(self._evaluate_all(snapshot))

    def _evaluate_all(self, snapshot: TradeSnapshot) -> Iterable[ThresholdCrossing]:
        for rb in self.boundaries:
            new_verdict = self.verdict_for(snapshot, rb)
            prior = self._last_verdict.get(rb.rule_id)
            if prior is None:
                # First evaluation — record but don't emit (no transition yet).
                self._last_verdict[rb.rule_id] = new_verdict
                continue
            if new_verdict == prior:
                continue
            direction = (
                CrossingDirection.UP
                if _get_scalar(snapshot, rb.scalar) > rb.boundary
                else CrossingDirection.DOWN
            )
            self._last_verdict[rb.rule_id] = new_verdict
            yield ThresholdCrossing(
                crossing_id=str(uuid.uuid4()),
                intent_id=snapshot.intent_id,
                ts=snapshot.ts or datetime.now(UTC),
                rule_id=rb.rule_id,
                citation=rb.citation,
                boundary=rb.boundary,
                direction=direction,
                snapshot=snapshot,
                prior_verdict=prior,
                new_verdict=new_verdict,
            )


__all__ = ["RuleBoundary", "ThresholdDetector", "VerdictPredicate"]
