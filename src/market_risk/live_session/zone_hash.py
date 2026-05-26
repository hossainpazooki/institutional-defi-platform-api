"""Zone hash — bucketize boundary-relevant scalars to a tuple-of-buckets hash.

Two snapshots that hash to the same zone are guaranteed to flip the same set of
rule boundaries (provided the buckets are wider than the boundary resolution).
The threshold detector uses this as a cheap "same as last tick" fast-path.

Initial bucket widths (per unified plan §B4):
- notional_usd: €100k
- position_pct: 1%
- vol_30d: 5%
- spread_bps: 5 bps
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeAlias

if TYPE_CHECKING:
    from src.market_risk.ws_schemas import TradeSnapshot

ZoneHash: TypeAlias = tuple[int, int, int, int]


@dataclass(frozen=True)
class BucketWidths:
    notional_usd: float = 100_000.0
    position_pct: float = 0.01
    vol_30d: float = 0.05
    spread_bps: float = 5.0


def _floor_bucket(value: float, width: float) -> int:
    if width <= 0 or not math.isfinite(value):
        return 0
    return int(math.floor(value / width))


def bucket_for(
    snapshot: TradeSnapshot,
    *,
    notional_usd: float,
    position_pct: float,
    widths: BucketWidths | None = None,
) -> ZoneHash:
    w = widths or BucketWidths()
    return (
        _floor_bucket(notional_usd, w.notional_usd),
        _floor_bucket(position_pct, w.position_pct),
        _floor_bucket(snapshot.vol_30d, w.vol_30d),
        _floor_bucket(snapshot.spread_bps, w.spread_bps),
    )


__all__ = ["BucketWidths", "ZoneHash", "bucket_for"]
