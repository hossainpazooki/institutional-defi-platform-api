"""Pydantic models for RAG domain API requests and responses."""

from __future__ import annotations

from pydantic import Field

from src.models import CustomBaseModel


class AskRequest(CustomBaseModel):
    """Request for factual Q&A."""

    question: str = Field(..., description="The question to answer")
    top_k: int = Field(5, description="Number of context chunks to retrieve")


class SourceCitation(CustomBaseModel):
    """A source citation in a Q&A response."""

    document_id: str
    chunk_id: str
    section: str | None = None
    score: float


class AskResponse(CustomBaseModel):
    """Response for factual Q&A."""

    answer: str
    sources: list[SourceCitation]
    method: str = Field(..., description="How the answer was generated: 'llm' or 'excerpt'")
