"""REST endpoint for creating + reading trade intents.

`POST /v2/intents` is the precondition for opening `/v2/ws/trade/{intent_id}`.
The response surfaces the *persisted* lifecycle state (`created_at`, `status`,
`activated_at`, `closed_at`, `last_error`) — values are read from the
repository row, never stamped at response time.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from src.market_risk.ws_schemas import InvestorType, TradeDirection

from .intent_repository import (
    CreateIntentParams,
    IntentRecord,
    IntentRepository,
    IntentStatus,
)

router = APIRouter(prefix="/v2/intents", tags=["Live Session Intents"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CreateIntentRequest(BaseModel):
    """Client-submitted intent details.

    `extra="forbid"` rejects unknown fields — most importantly `intent_id`,
    which must be server-generated.
    """

    model_config = ConfigDict(extra="forbid")

    asset: Annotated[str, Field(min_length=1, max_length=32)]
    direction: TradeDirection
    notional_usd: Annotated[Decimal, Field(gt=0)]
    venue_jurisdiction: Annotated[str, Field(min_length=1, max_length=8)]
    investor_type: InvestorType
    target_jurisdictions: Annotated[list[str], Field(min_length=1)]
    holding_period_days: Annotated[int, Field(ge=1, le=3650)]


class IntentResponse(BaseModel):
    """Full intent state including server-generated id and lifecycle metadata."""

    intent_id: str
    asset: str
    direction: TradeDirection
    notional_usd: Decimal
    venue_jurisdiction: str
    investor_type: InvestorType
    target_jurisdictions: list[str]
    holding_period_days: int
    status: IntentStatus
    created_at: datetime
    activated_at: datetime | None = None
    closed_at: datetime | None = None
    last_error: str | None = None


def _record_to_response(record: IntentRecord) -> IntentResponse:
    return IntentResponse(
        intent_id=record.intent_id,
        asset=record.asset,
        direction=record.direction,
        notional_usd=record.notional_usd,
        venue_jurisdiction=record.venue_jurisdiction,
        investor_type=record.investor_type,
        target_jurisdictions=list(record.target_jurisdictions),
        holding_period_days=record.holding_period_days,
        status=record.status,
        created_at=record.created_at,
        activated_at=record.activated_at,
        closed_at=record.closed_at,
        last_error=record.last_error,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_repo(request: Request) -> IntentRepository:
    repo = getattr(request.app.state, "intent_repository", None)
    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="live-session subsystem disabled",
        )
    return repo  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=IntentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_intent(req: CreateIntentRequest, request: Request) -> IntentResponse:
    """Persist a new trade intent and return it with a server-generated id."""
    repo = _get_repo(request)
    params = CreateIntentParams(
        asset=req.asset,
        direction=req.direction,
        notional_usd=req.notional_usd,
        venue_jurisdiction=req.venue_jurisdiction,
        investor_type=req.investor_type,
        target_jurisdictions=list(req.target_jurisdictions),
        holding_period_days=req.holding_period_days,
    )
    record = repo.create(params)
    return _record_to_response(record)


@router.get("/{intent_id}", response_model=IntentResponse)
def get_intent(intent_id: str, request: Request) -> IntentResponse:
    """Fetch a persisted intent by id. 404 if missing.

    Returns the **persisted** lifecycle metadata — `status`, `created_at`,
    `activated_at`, `closed_at`, `last_error` reflect the current row state.
    """
    repo = _get_repo(request)
    record = repo.get_record(intent_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown intent_id {intent_id!r}",
        )
    return _record_to_response(record)


__all__ = ["CreateIntentRequest", "IntentResponse", "router"]
