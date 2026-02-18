"""JPM Scenarios domain — institutional tokenization scenario analysis."""

from .constants import CHAIN_PROFILES, SCENARIOS, ScenarioConfig
from .router import router
from .schemas import (
    ComplianceResult,
    ExplanationResult,
    MarketRiskResult,
    MemoRequest,
    MemoResponse,
    ProtocolRiskResult,
    ScenarioRunResult,
    ScenariosResponse,
    ScenarioSummary,
)
from .service import JPMScenarioService

__all__ = [
    # Router
    "router",
    # Service
    "JPMScenarioService",
    # Constants
    "CHAIN_PROFILES",
    "SCENARIOS",
    "ScenarioConfig",
    # Schemas
    "ComplianceResult",
    "ExplanationResult",
    "MarketRiskResult",
    "MemoRequest",
    "MemoResponse",
    "ProtocolRiskResult",
    "ScenarioRunResult",
    "ScenarioSummary",
    "ScenariosResponse",
]
