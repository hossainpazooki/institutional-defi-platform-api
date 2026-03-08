"""Feature Store domain service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from src.features.schemas import (
    EntitiesResponse,
    FeatureSnapshot,
    FeatureValue,
    LatestFeaturesResponse,
)

# Mock data for stub implementation
MOCK_ENTITIES = [
    "ethereum",
    "base",
    "polygon",
    "solana",
    "aave_v3",
    "uniswap_v3",
    "BTC",
    "ETH",
    "SOL",
]


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _mock_features() -> dict[str, dict[str, FeatureValue]]:
    """Build mock features with current timestamps."""
    now = _now()
    return {
        "ethereum": {
            "overall_score": FeatureValue(value=92, ts=now, confidence=0.95, source="protocol_risk"),
            "decentralization_score": FeatureValue(value=95, ts=now, confidence=0.95, source="protocol_risk"),
            "finality_score": FeatureValue(value=88, ts=now, confidence=0.95, source="protocol_risk"),
            "tps": FeatureValue(value=15.5, ts=now, confidence=0.99, source="chain_health"),
            "gas_gwei": FeatureValue(value=25.0, ts=now, confidence=0.99, source="chain_health"),
        },
        "base": {
            "overall_score": FeatureValue(value=78, ts=now, confidence=0.90, source="protocol_risk"),
            "decentralization_score": FeatureValue(value=55, ts=now, confidence=0.90, source="protocol_risk"),
            "finality_score": FeatureValue(value=85, ts=now, confidence=0.90, source="protocol_risk"),
            "tps": FeatureValue(value=45.0, ts=now, confidence=0.99, source="chain_health"),
        },
        "aave_v3": {
            "overall_score": FeatureValue(value=90, ts=now, confidence=0.92, source="defi_risk"),
            "smart_contract_score": FeatureValue(value=95, ts=now, confidence=0.92, source="defi_risk"),
            "economic_score": FeatureValue(value=88, ts=now, confidence=0.92, source="defi_risk"),
            "tvl_usd": FeatureValue(value=15_000_000_000, ts=now, confidence=0.99, source="defi_risk"),
            "grade": FeatureValue(value="A", ts=now, confidence=0.92, source="defi_risk"),
        },
        "BTC": {
            "var_99_1d": FeatureValue(value=0.045, ts=now, confidence=0.85, source="market_risk"),
            "volatility_30d": FeatureValue(value=0.52, ts=now, confidence=0.90, source="market_risk"),
            "price_usd": FeatureValue(value=95000, ts=now, confidence=0.99, source="market_risk"),
        },
    }


def parse_window(window: str) -> timedelta:
    """Parse window string like '30d', '7d', '1h' into timedelta."""
    unit = window[-1]
    value = int(window[:-1])
    if unit == "d":
        return timedelta(days=value)
    elif unit == "h":
        return timedelta(hours=value)
    elif unit == "m":
        return timedelta(minutes=value)
    else:
        raise ValueError(f"Invalid window unit: {unit}")


class FeatureStoreService:
    """Business logic for the Feature Store."""

    async def list_entities(
        self,
        source: str | None = None,
        limit: int = 100,
    ) -> EntitiesResponse:
        """List all entities in the Feature Store."""
        entities = MOCK_ENTITIES[:limit]
        return EntitiesResponse(entities=entities, count=len(entities))

    async def get_features(
        self,
        entity_id: str,
        window: str = "30d",
        feature_names: str | None = None,
        source: str | None = None,
        limit: int = 1000,
    ) -> FeatureSnapshot:
        """Get historical features for an entity within a time window."""
        window_delta = parse_window(window)
        now = _now()
        window_start = now - window_delta

        entity_features = _mock_features().get(entity_id, {})

        if feature_names:
            names = [n.strip() for n in feature_names.split(",")]
            entity_features = {k: v for k, v in entity_features.items() if k in names}

        if source:
            entity_features = {k: v for k, v in entity_features.items() if v.source == source}

        features_dict: dict[str, list[dict[str, Any]]] = {}
        for name, feature in entity_features.items():
            features_dict[name] = [
                {
                    "value": feature.value,
                    "ts": feature.ts.isoformat(),
                    "confidence": feature.confidence,
                    "source": feature.source,
                }
            ]

        return FeatureSnapshot(
            entity_id=entity_id,
            features=features_dict,
            window_start=window_start,
            window_end=now,
            total_points=len(features_dict),
        )

    async def get_latest_features(
        self,
        entity_id: str,
        feature_names: str | None = None,
    ) -> LatestFeaturesResponse:
        """Get the most recent value for each feature of an entity."""
        entity_features = _mock_features().get(entity_id, {})

        if feature_names:
            names = [n.strip() for n in feature_names.split(",")]
            entity_features = {k: v for k, v in entity_features.items() if k in names}

        return LatestFeaturesResponse(
            entity_id=entity_id,
            features=entity_features,
            as_of=_now(),
        )
