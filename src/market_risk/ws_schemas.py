"""WebSocket envelope + payload schemas for the live trading session.

Mirrors `@platform/contracts` in digital-assets-cross-border. See spec §7.

Pydantic v2 serializes `Decimal` as a JSON string by default — matches the TS
contract which carries price/size as string-encoded Decimals.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, RootModel

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Verdict(StrEnum):
    COMPLIANT = "compliant"
    CONDITIONAL = "conditional"
    BLOCKED = "blocked"


class CrossingDirection(StrEnum):
    UP = "crossed_up"
    DOWN = "crossed_down"


class NLIStatus(StrEnum):
    STREAMING = "streaming"
    VERIFIED = "verified"
    RETRACTED = "retracted"


class InvestorType(StrEnum):
    RETAIL = "retail"
    PROFESSIONAL = "professional"
    ELIGIBLE_COUNTERPARTY = "eligible_counterparty"


class TradeDirection(StrEnum):
    BUY = "buy"
    SELL = "sell"


class MessageType(StrEnum):
    SUBSCRIBE = "subscribe"
    TICK = "tick"
    RISK_UPDATE = "risk_update"
    COMPLIANCE = "compliance"
    THRESHOLD = "threshold"
    RATIONALE_TOK = "rationale_tok"
    RATIONALE_VERIFIED = "rationale_verified"
    RATIONALE_RETRACTED = "rationale_retracted"
    ERROR = "error"


# ---------------------------------------------------------------------------
# Core domain models
# ---------------------------------------------------------------------------


class TradeIntent(BaseModel):
    model_config = ConfigDict(frozen=True)

    intent_id: str
    direction: TradeDirection
    asset: str
    notional_usd: Decimal
    venue_jurisdiction: str
    investor_type: InvestorType
    target_jurisdictions: list[str]
    holding_period_days: int


class TradeSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

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
    funding_rate: float | None = None


class ThresholdCrossing(BaseModel):
    model_config = ConfigDict(frozen=True)

    crossing_id: str
    intent_id: str
    ts: datetime
    rule_id: str
    citation: str
    boundary: Decimal
    direction: CrossingDirection
    snapshot: TradeSnapshot
    prior_verdict: Verdict
    new_verdict: Verdict


class Rationale(BaseModel):
    rationale_id: str
    crossing_id: str
    content: str
    status: NLIStatus
    final_score: float | None = None
    retraction_reason: str | None = None
    completed_at: datetime | None = None


# ---------------------------------------------------------------------------
# Payloads (one per message type)
# ---------------------------------------------------------------------------


class SubscribePayload(BaseModel):
    intent_id: str


class CompliancePayload(BaseModel):
    crossing_id: str
    prior_verdict: Verdict
    new_verdict: Verdict
    citation: str


class RationaleTokPayload(BaseModel):
    rationale_id: str
    crossing_id: str
    token: str


class RationaleVerifiedPayload(BaseModel):
    rationale_id: str
    crossing_id: str
    final_score: float


class RationaleRetractedPayload(BaseModel):
    rationale_id: str
    crossing_id: str
    final_score: float
    reason: str


class ErrorPayload(BaseModel):
    code: str
    message: str


class RiskUpdatePayload(RootModel[dict[str, Any]]):
    """Open-shape risk metric update. Concrete keys depend on emitter."""


# ---------------------------------------------------------------------------
# Envelopes — discriminated union on `type`
# ---------------------------------------------------------------------------


class _BaseEnvelope(BaseModel):
    seq: int = Field(..., ge=0)
    ts: datetime


class SubscribeEnvelope(_BaseEnvelope):
    type: Literal[MessageType.SUBSCRIBE] = MessageType.SUBSCRIBE
    payload: SubscribePayload


class TickEnvelope(_BaseEnvelope):
    type: Literal[MessageType.TICK] = MessageType.TICK
    payload: TradeSnapshot


class RiskUpdateEnvelope(_BaseEnvelope):
    type: Literal[MessageType.RISK_UPDATE] = MessageType.RISK_UPDATE
    payload: RiskUpdatePayload


class ComplianceEnvelope(_BaseEnvelope):
    type: Literal[MessageType.COMPLIANCE] = MessageType.COMPLIANCE
    payload: CompliancePayload


class ThresholdEnvelope(_BaseEnvelope):
    type: Literal[MessageType.THRESHOLD] = MessageType.THRESHOLD
    payload: ThresholdCrossing


class RationaleTokEnvelope(_BaseEnvelope):
    type: Literal[MessageType.RATIONALE_TOK] = MessageType.RATIONALE_TOK
    payload: RationaleTokPayload


class RationaleVerifiedEnvelope(_BaseEnvelope):
    type: Literal[MessageType.RATIONALE_VERIFIED] = MessageType.RATIONALE_VERIFIED
    payload: RationaleVerifiedPayload


class RationaleRetractedEnvelope(_BaseEnvelope):
    type: Literal[MessageType.RATIONALE_RETRACTED] = MessageType.RATIONALE_RETRACTED
    payload: RationaleRetractedPayload


class ErrorEnvelope(_BaseEnvelope):
    type: Literal[MessageType.ERROR] = MessageType.ERROR
    payload: ErrorPayload


WSEnvelope: TypeAlias = Annotated[
    SubscribeEnvelope
    | TickEnvelope
    | RiskUpdateEnvelope
    | ComplianceEnvelope
    | ThresholdEnvelope
    | RationaleTokEnvelope
    | RationaleVerifiedEnvelope
    | RationaleRetractedEnvelope
    | ErrorEnvelope,
    Field(discriminator="type"),
]


class WSEnvelopeAdapter(RootModel[WSEnvelope]):
    """Round-trip adapter — use `.model_validate_json(...)` / `.model_dump_json()`."""


__all__ = [
    "ComplianceEnvelope",
    "CompliancePayload",
    "CrossingDirection",
    "ErrorEnvelope",
    "ErrorPayload",
    "InvestorType",
    "MessageType",
    "NLIStatus",
    "Rationale",
    "RationaleRetractedEnvelope",
    "RationaleRetractedPayload",
    "RationaleTokEnvelope",
    "RationaleTokPayload",
    "RationaleVerifiedEnvelope",
    "RationaleVerifiedPayload",
    "RiskUpdateEnvelope",
    "RiskUpdatePayload",
    "SubscribeEnvelope",
    "SubscribePayload",
    "ThresholdCrossing",
    "ThresholdEnvelope",
    "TickEnvelope",
    "TradeDirection",
    "TradeIntent",
    "TradeSnapshot",
    "Verdict",
    "WSEnvelope",
    "WSEnvelopeAdapter",
]
