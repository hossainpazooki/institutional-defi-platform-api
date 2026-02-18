"""Verification request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class VerifyRuleRequest(BaseModel):
    """Request to verify a rule."""

    rule_id: str
    source_text: str | None = None
    tiers: list[int] = Field(default=[0, 1])


class VerifyRuleResponse(BaseModel):
    """Response from rule verification."""

    rule_id: str
    status: str
    confidence: float
    evidence_count: int
    evidence: list[dict]
