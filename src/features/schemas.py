"""Pydantic schemas for Feature Store domain."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class FeatureValue(BaseModel):
    """A single feature value with metadata."""

    value: Any
    ts: datetime
    confidence: float | None = None
    source: str


class FeatureSnapshot(BaseModel):
    """Response model for feature queries."""

    entity_id: str
    features: dict[str, list[dict]]  # feature_name -> list of {value, ts, confidence}
    window_start: datetime
    window_end: datetime
    total_points: int


class LatestFeaturesResponse(BaseModel):
    """Response model for latest features query."""

    entity_id: str
    features: dict[str, FeatureValue]
    as_of: datetime


class EntitiesResponse(BaseModel):
    """Response model for listing entities."""

    entities: list[str]
    count: int


class FeatureWriteRequest(BaseModel):
    """Request model for writing a feature."""

    entity_id: str
    feature_name: str
    value: Any
    source: str
    confidence: float | None = None
    metadata: dict | None = None
