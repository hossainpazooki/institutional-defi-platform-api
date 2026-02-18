"""Analytics domain — rule comparison, clustering, and conflict detection.

From Workbench analytics/ + core/api/routes_analytics + core/visualization/.
"""

from .drift import DriftDetector, DriftMetrics, DriftReport
from .error_patterns import (
    CategoryStats,
    ErrorPattern,
    ErrorPatternAnalyzer,
    ReviewQueueItem,
)
from .router import router
from .schemas import (
    ClusterAlgorithm,
    ClusterAnalysis,
    ClusterInfo,
    ClusterRequest,
    CompareRulesRequest,
    ComparisonResult,
    ConflictInfo,
    ConflictReport,
    ConflictSearchRequest,
    ConflictSeverity,
    ConflictType,
    CoverageGap,
    CoverageImportance,
    CoverageReport,
    EmbeddingTypeEnum,
    FrameworkCoverage,
    GraphData,
    GraphLink,
    GraphNode,
    SimilarityExplanation,
    SimilarRule,
    SimilarRulesRequest,
    SimilarRulesResponse,
    UMAPPoint,
    UMAPProjectionRequest,
    UMAPProjectionResponse,
)
from .service import RuleAnalyticsService

__all__ = [
    # Router
    "router",
    # Service
    "RuleAnalyticsService",
    # Drift
    "DriftDetector",
    "DriftMetrics",
    "DriftReport",
    # Error Patterns
    "ErrorPatternAnalyzer",
    "ErrorPattern",
    "CategoryStats",
    "ReviewQueueItem",
    # Enums
    "EmbeddingTypeEnum",
    "ClusterAlgorithm",
    "ConflictType",
    "ConflictSeverity",
    "CoverageImportance",
    # Comparison
    "CompareRulesRequest",
    "ComparisonResult",
    # Clustering
    "ClusterRequest",
    "ClusterAnalysis",
    "ClusterInfo",
    # Conflicts
    "ConflictSearchRequest",
    "ConflictReport",
    "ConflictInfo",
    # Similarity
    "SimilarRulesRequest",
    "SimilarRulesResponse",
    "SimilarRule",
    "SimilarityExplanation",
    # Coverage
    "CoverageReport",
    "FrameworkCoverage",
    "CoverageGap",
    # UMAP
    "UMAPProjectionRequest",
    "UMAPProjectionResponse",
    "UMAPPoint",
    # Graph
    "GraphData",
    "GraphNode",
    "GraphLink",
]
