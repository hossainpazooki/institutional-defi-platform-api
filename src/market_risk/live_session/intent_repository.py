"""TradeIntent persistence — create + get + lifecycle status transitions.

Lifecycle semantics (decision locked this slice):

- A row enters with `status='created'` and `created_at=<server now>`.
- On the **first** successful registry acquire, `mark_active()` flips
  `status='active'` and stamps `activated_at`. Subsequent acquires (refcount
  increments) are no-ops on the repo — `activated_at` is the *first* activation.
- On the **final** release (refcount hits zero and Session.stop succeeds),
  `mark_closed()` flips `status='closed'` and stamps `closed_at`. **Closed is
  terminal** — the registry does not re-activate a closed intent. (Enforcement
  belongs to the registry; this layer is happy to record any state.)
- If session construction fails after intent lookup, `mark_failed(reason)`
  flips to `status='failed'` and records `last_error`.

`mark_*` methods are **idempotent** and return `bool` (changed / not changed),
so the caller knows whether a side-effect actually occurred. They never raise
on unknown ids — they return `False`, leaving the lookup-error surface to the
registry/REST boundary where it belongs.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal, Protocol, TypeAlias

from src.market_risk.ws_schemas import InvestorType, TradeDirection, TradeIntent

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractContextManager
    from decimal import Decimal

    from sqlmodel import Session as SQLSession


INTENT_ID_PREFIX = "int_"

IntentStatus: TypeAlias = Literal["created", "active", "closed", "failed"]


def generate_intent_id() -> str:
    """Server-side high-entropy id. ~22-char URL-safe base64 + prefix."""
    return f"{INTENT_ID_PREFIX}{secrets.token_urlsafe(16)}"


@dataclass(frozen=True)
class CreateIntentParams:
    """Inputs to `create()` — already validated by the REST layer."""

    asset: str
    direction: TradeDirection
    notional_usd: Decimal
    venue_jurisdiction: str
    investor_type: InvestorType
    target_jurisdictions: list[str]
    holding_period_days: int


@dataclass(frozen=True)
class IntentRecord:
    """Persisted intent + lifecycle metadata. The REST response shape."""

    intent_id: str
    asset: str
    direction: TradeDirection
    notional_usd: Decimal
    venue_jurisdiction: str
    investor_type: InvestorType
    target_jurisdictions: tuple[str, ...]
    holding_period_days: int
    status: IntentStatus
    created_at: datetime
    activated_at: datetime | None
    closed_at: datetime | None
    last_error: str | None

    def to_intent(self) -> TradeIntent:
        """Project to the pipeline-facing immutable `TradeIntent`."""
        return TradeIntent(
            intent_id=self.intent_id,
            direction=self.direction,
            asset=self.asset,
            notional_usd=self.notional_usd,
            venue_jurisdiction=self.venue_jurisdiction,
            investor_type=self.investor_type,
            target_jurisdictions=list(self.target_jurisdictions),
            holding_period_days=self.holding_period_days,
        )


class IntentRepository(Protocol):
    """CRUD + lifecycle transitions for trade intents.

    `create()` generates the `intent_id` and returns the full record.
    `get_record()` is the canonical read; `get()` is a convenience wrapper for
    callers that only need the pipeline-facing `TradeIntent`.
    `mark_*()` methods are idempotent and return whether state changed.
    """

    def create(self, params: CreateIntentParams) -> IntentRecord: ...

    def get_record(self, intent_id: str) -> IntentRecord | None: ...

    def get(self, intent_id: str) -> TradeIntent | None: ...

    def mark_active(self, intent_id: str) -> bool: ...

    def mark_closed(self, intent_id: str) -> bool: ...

    def mark_failed(self, intent_id: str, reason: str) -> bool: ...


# ---------------------------------------------------------------------------
# In-memory implementation
# ---------------------------------------------------------------------------


@dataclass
class _MutableRow:
    """Internal mutable storage for `InMemoryIntentRepository`."""

    intent: TradeIntent
    status: IntentStatus
    created_at: datetime
    activated_at: datetime | None = None
    closed_at: datetime | None = None
    last_error: str | None = None

    def to_record(self) -> IntentRecord:
        return IntentRecord(
            intent_id=self.intent.intent_id,
            asset=self.intent.asset,
            direction=self.intent.direction,
            notional_usd=self.intent.notional_usd,
            venue_jurisdiction=self.intent.venue_jurisdiction,
            investor_type=self.intent.investor_type,
            target_jurisdictions=tuple(self.intent.target_jurisdictions),
            holding_period_days=self.intent.holding_period_days,
            status=self.status,
            created_at=self.created_at,
            activated_at=self.activated_at,
            closed_at=self.closed_at,
            last_error=self.last_error,
        )


@dataclass
class InMemoryIntentRepository:
    """Test/dev implementation — `rows` keyed by `intent_id`."""

    rows: dict[str, _MutableRow] = field(default_factory=dict)

    def create(self, params: CreateIntentParams) -> IntentRecord:
        intent_id = generate_intent_id()
        intent = TradeIntent(
            intent_id=intent_id,
            direction=params.direction,
            asset=params.asset,
            notional_usd=params.notional_usd,
            venue_jurisdiction=params.venue_jurisdiction,
            investor_type=params.investor_type,
            target_jurisdictions=list(params.target_jurisdictions),
            holding_period_days=params.holding_period_days,
        )
        row = _MutableRow(
            intent=intent,
            status="created",
            created_at=datetime.now(tz=UTC),
        )
        self.rows[intent_id] = row
        return row.to_record()

    def get_record(self, intent_id: str) -> IntentRecord | None:
        row = self.rows.get(intent_id)
        return row.to_record() if row is not None else None

    def get(self, intent_id: str) -> TradeIntent | None:
        row = self.rows.get(intent_id)
        return row.intent if row is not None else None

    def mark_active(self, intent_id: str) -> bool:
        row = self.rows.get(intent_id)
        if row is None or row.status != "created":
            return False
        row.status = "active"
        row.activated_at = datetime.now(tz=UTC)
        return True

    def mark_closed(self, intent_id: str) -> bool:
        row = self.rows.get(intent_id)
        if row is None or row.status not in {"created", "active"}:
            return False
        row.status = "closed"
        row.closed_at = datetime.now(tz=UTC)
        return True

    def mark_failed(self, intent_id: str, reason: str) -> bool:
        row = self.rows.get(intent_id)
        if row is None or row.status not in {"created", "active"}:
            return False
        row.status = "failed"
        row.last_error = reason
        return True


# ---------------------------------------------------------------------------
# SQLModel implementation — lazy import of the row class
# ---------------------------------------------------------------------------


@dataclass
class SQLIntentRepository:
    """SQLModel-backed implementation.

    Row class is imported inside methods so the module import path stays safe
    on Python 3.14. Lifecycle updates are read-modify-write inside one
    session; the registry's per-intent asyncio.Lock serializes acquires.
    """

    session_factory: Callable[[], AbstractContextManager[SQLSession]]

    def create(self, params: CreateIntentParams) -> IntentRecord:
        from .models import TradeIntentRow

        intent_id = generate_intent_id()
        now = datetime.now(tz=UTC)
        row = TradeIntentRow(
            intent_id=intent_id,
            asset=params.asset,
            direction=params.direction.value,
            notional_usd=params.notional_usd,
            venue_jurisdiction=params.venue_jurisdiction,
            investor_type=params.investor_type.value,
            target_jurisdictions=list(params.target_jurisdictions),
            holding_period_days=params.holding_period_days,
            status="created",
            created_at=now,
        )
        with self.session_factory() as s:
            s.add(row)
            s.commit()
            s.refresh(row)
        return _row_to_record(row)

    def get_record(self, intent_id: str) -> IntentRecord | None:
        from .models import TradeIntentRow

        with self.session_factory() as s:
            row = s.get(TradeIntentRow, intent_id)
            if row is None:
                return None
            return _row_to_record(row)

    def get(self, intent_id: str) -> TradeIntent | None:
        record = self.get_record(intent_id)
        return record.to_intent() if record is not None else None

    def mark_active(self, intent_id: str) -> bool:
        return self._transition(
            intent_id,
            allowed_from={"created"},
            new_status="active",
            stamp_field="activated_at",
        )

    def mark_closed(self, intent_id: str) -> bool:
        return self._transition(
            intent_id,
            allowed_from={"created", "active"},
            new_status="closed",
            stamp_field="closed_at",
        )

    def mark_failed(self, intent_id: str, reason: str) -> bool:
        from .models import TradeIntentRow

        with self.session_factory() as s:
            row = s.get(TradeIntentRow, intent_id)
            if row is None or row.status not in {"created", "active"}:
                return False
            row.status = "failed"
            row.last_error = reason
            s.add(row)
            s.commit()
            return True

    def _transition(
        self,
        intent_id: str,
        *,
        allowed_from: set[str],
        new_status: IntentStatus,
        stamp_field: str,
    ) -> bool:
        from .models import TradeIntentRow

        with self.session_factory() as s:
            row = s.get(TradeIntentRow, intent_id)
            if row is None or row.status not in allowed_from:
                return False
            row.status = new_status
            setattr(row, stamp_field, datetime.now(tz=UTC))
            s.add(row)
            s.commit()
            return True


def _row_to_record(row: object) -> IntentRecord:
    """Map a `TradeIntentRow` to `IntentRecord` without importing the row class."""
    status = getattr(row, "status")  # noqa: B009
    # Status comes from the DB string column; validate at the boundary.
    if status not in {"created", "active", "closed", "failed"}:
        msg = f"unexpected status in DB row: {status!r}"
        raise ValueError(msg)
    status_typed: IntentStatus = status
    return IntentRecord(
        intent_id=getattr(row, "intent_id"),  # noqa: B009
        asset=getattr(row, "asset"),  # noqa: B009
        direction=TradeDirection(getattr(row, "direction")),  # noqa: B009
        notional_usd=getattr(row, "notional_usd"),  # noqa: B009
        venue_jurisdiction=getattr(row, "venue_jurisdiction"),  # noqa: B009
        investor_type=InvestorType(getattr(row, "investor_type")),  # noqa: B009
        target_jurisdictions=tuple(getattr(row, "target_jurisdictions") or []),  # noqa: B009
        holding_period_days=getattr(row, "holding_period_days"),  # noqa: B009
        status=status_typed,
        created_at=getattr(row, "created_at"),  # noqa: B009
        activated_at=getattr(row, "activated_at", None),
        closed_at=getattr(row, "closed_at", None),
        last_error=getattr(row, "last_error", None),
    )


__all__ = [
    "INTENT_ID_PREFIX",
    "CreateIntentParams",
    "InMemoryIntentRepository",
    "IntentRecord",
    "IntentRepository",
    "IntentStatus",
    "SQLIntentRepository",
    "generate_intent_id",
]
