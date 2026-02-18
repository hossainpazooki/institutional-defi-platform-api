"""Feature Store API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query

from src.features.schemas import (
    EntitiesResponse,
    FeatureSnapshot,
    LatestFeaturesResponse,
)
from src.features.service import FeatureStoreService

router = APIRouter()

_service = FeatureStoreService()


@router.get("/", response_model=EntitiesResponse)
async def list_entities(
    source: str | None = Query(None, description="Filter by source"),
    limit: int = Query(100, le=1000),
):
    """List all entities in the Feature Store."""
    return await _service.list_entities(source=source, limit=limit)


@router.get("/{entity_id}", response_model=FeatureSnapshot)
async def get_features(
    entity_id: str,
    window: str = Query("30d", description="Time window, e.g., '30d', '7d', '1h'"),
    feature_names: str | None = Query(None, description="Comma-separated feature names"),
    source: str | None = Query(None, description="Filter by source"),
    limit: int = Query(1000, le=10000),
):
    """Get historical features for an entity within a time window."""
    return await _service.get_features(
        entity_id=entity_id,
        window=window,
        feature_names=feature_names,
        source=source,
        limit=limit,
    )


@router.get("/{entity_id}/latest", response_model=LatestFeaturesResponse)
async def get_latest_features(
    entity_id: str,
    feature_names: str | None = Query(None, description="Comma-separated feature names"),
):
    """Get the most recent value for each feature of an entity."""
    return await _service.get_latest_features(
        entity_id=entity_id,
        feature_names=feature_names,
    )
