"""Schemas for the credit decisioning pipeline."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from src.models import CustomBaseModel


class CreditApplication(CustomBaseModel):
    """A credit application submitted for decisioning."""

    borrower_name: str
    deal_amount_usd: float
    document_ids: list[str]
    industry: str
    borrower_type: Literal["corporate", "fund", "sov", "sme"]
    app_id: str = ""
    status: str = "pending"
    created_at: datetime = datetime.now(UTC)

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        if not self.app_id:
            self.app_id = str(uuid.uuid4())
        if self.created_at == datetime.min:
            self.created_at = datetime.now(UTC)


class DocumentUpload(CustomBaseModel):
    """An uploaded document for credit analysis."""

    filename: str
    content_type: str
    raw_text: str
    document_id: str = ""

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        if not self.document_id:
            self.document_id = str(uuid.uuid4())


class ClassificationResult(CustomBaseModel):
    """Result of document classification."""

    document_id: str
    predicted_type: Literal[
        "cim",
        "financial_statement",
        "legal_opinion",
        "covenant_package",
        "tax_certificate",
        "other",
    ]
    confidence: float
    extracted_fields: dict[str, Any]


class AgentSignal(CustomBaseModel):
    """Base output from a credit analysis agent."""

    signals: list[str]
    confidence: float
    uncertainty_flags: list[str]
    model_version: str = "claude-sonnet-4-20250514"


class FinancialAgentOutput(AgentSignal):
    """Output from the financial analysis agent."""

    revenue_trend: str
    debt_service_coverage: float
    working_capital_ratio: float
    credit_score_estimate: int


class LegalAgentOutput(AgentSignal):
    """Output from the legal analysis agent."""

    regulatory_flags: list[str]
    covenant_issues: list[str]
    jurisdiction_risks: list[str]


class MarketAgentOutput(AgentSignal):
    """Output from the market analysis agent."""

    industry_outlook: str
    peer_comparison: dict[str, Any]
    market_risk_score: float


class SynthesisOutput(CustomBaseModel):
    """Synthesized credit decision output."""

    recommendation: Literal["approve", "decline", "refer"]
    confidence: float
    escalate: bool
    escalation_reason: str | None
    citations: list[dict[str, str]]
    agent_outputs: dict[str, Any]


class HITLDecision(CustomBaseModel):
    """Human-in-the-loop review decision."""

    reviewer_id: str
    decision: Literal["approve", "decline", "override"]
    notes: str
    overrides: dict[str, Any] | None = None


class PipelineStatus(CustomBaseModel):
    """Status of a credit decisioning pipeline run."""

    app_id: str
    phase: str
    phases_completed: list[str]
    phases_remaining: list[str]
    started_at: datetime
    completed_at: datetime | None = None
