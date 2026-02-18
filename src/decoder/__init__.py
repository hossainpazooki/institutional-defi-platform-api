"""Decoder domain - tiered explanations and counterfactual analysis."""

from .exceptions import DecoderServiceError
from .llm_service import LLMDecoderService
from .router import counterfactual_router, router
from .schemas import (
    # Router Request Models
    AnalyzeByIdRequest,
    # Explanation
    AuditInfo,
    # Citation
    Citation,
    # Templates
    CitationSlot,
    CompareByIdRequest,
    # Comparison
    ComparisonMatrix,
    ComparisonRequest,
    # Counterfactual
    CounterfactualExplanation,
    CounterfactualRequest,
    CounterfactualResponse,
    # Decoder Request/Response
    DecoderRequest,
    DecoderResponse,
    DeltaAnalysis,
    ExplainByDecisionRequest,
    Explanation,
    ExplanationSummary,
    ExplanationTemplate,
    # Enums
    ExplanationTier,
    InlineAnalyzeRequest,
    InlineCompareRequest,
    InlineDecisionRequest,
    LLMCitation,
    # LLM Decoder
    LLMDecoderResponse,
    LLMExplainRequest,
    LLMTierInfo,
    LLMTiersResponse,
    MatrixInsight,
    OutcomeSummary,
    Scenario,
    ScenarioRequest,
    ScenarioType,
    TemplateInfo,
    TemplateSection,
    TemplateVariable,
)
from .service import (
    CitationInjector,
    CounterfactualEngine,
    DecoderService,
    DeltaAnalyzer,
    TemplateRegistry,
)

__all__ = [
    # Router
    "router",
    "counterfactual_router",
    # Services
    "DecoderService",
    "CounterfactualEngine",
    "CitationInjector",
    "TemplateRegistry",
    "DeltaAnalyzer",
    "LLMDecoderService",
    # Exceptions
    "DecoderServiceError",
    # Enums
    "ExplanationTier",
    "ScenarioType",
    # Citation
    "Citation",
    "LLMCitation",
    # Explanation
    "Explanation",
    "ExplanationSummary",
    "AuditInfo",
    # Decoder Request/Response
    "DecoderRequest",
    "DecoderResponse",
    # LLM Decoder
    "LLMExplainRequest",
    "LLMDecoderResponse",
    "LLMTierInfo",
    "LLMTiersResponse",
    # Counterfactual
    "Scenario",
    "OutcomeSummary",
    "DeltaAnalysis",
    "CounterfactualExplanation",
    "CounterfactualRequest",
    "CounterfactualResponse",
    # Comparison
    "ComparisonRequest",
    "MatrixInsight",
    "ComparisonMatrix",
    # Templates
    "TemplateVariable",
    "CitationSlot",
    "TemplateSection",
    "ExplanationTemplate",
    # Router Request Models
    "TemplateInfo",
    "ExplainByDecisionRequest",
    "InlineDecisionRequest",
    "ScenarioRequest",
    "AnalyzeByIdRequest",
    "InlineAnalyzeRequest",
    "CompareByIdRequest",
    "InlineCompareRequest",
]
