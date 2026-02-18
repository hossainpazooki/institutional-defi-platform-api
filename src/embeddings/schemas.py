"""Pydantic schemas for embedding rule API and store operations."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

# =============================================================================
# API Schemas
# =============================================================================


class EmbeddingTypeEnum(StrEnum):
    """Types of embeddings generated per rule."""

    SEMANTIC = "semantic"
    STRUCTURAL = "structural"
    ENTITY = "entity"
    LEGAL = "legal"


class EmbeddingRead(BaseModel):
    """Read schema for a rule embedding."""

    id: int
    embedding_type: str
    vector_dim: int
    model_name: str
    source_text: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class EmbeddingWithVector(EmbeddingRead):
    """Embedding with the actual vector (for search results)."""

    vector: list[float] = Field(description="The embedding vector")


class SimilarityResult(BaseModel):
    """Result of a similarity search."""

    rule_id: str
    rule_name: str
    score: float = Field(description="Similarity score (0-1, higher is more similar)")
    embedding_type: str
    matched_text: str | None = None


class SearchRequest(BaseModel):
    """Request for embedding-based search."""

    query: str = Field(description="Text query to search for")
    embedding_types: list[EmbeddingTypeEnum] = Field(
        default_factory=lambda: list(EmbeddingTypeEnum),
        description="Types of embeddings to search (defaults to all)",
    )
    limit: int = Field(default=10, ge=1, le=100, description="Maximum number of results")
    min_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Minimum similarity score")


class ConditionCreate(BaseModel):
    field: str
    operator: str
    value: str
    description: str | None = None


class ConditionRead(BaseModel):
    id: int
    field: str
    operator: str
    value: str
    description: str | None

    model_config = {"from_attributes": True}


class DecisionCreate(BaseModel):
    outcome: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    explanation: str | None = None


class DecisionRead(BaseModel):
    id: int
    outcome: str
    confidence: float
    explanation: str | None

    model_config = {"from_attributes": True}


class LegalSourceCreate(BaseModel):
    citation: str
    document_id: str | None = None
    url: str | None = None


class LegalSourceRead(BaseModel):
    id: int
    citation: str
    document_id: str | None
    url: str | None

    model_config = {"from_attributes": True}


class RuleCreate(BaseModel):
    rule_id: str
    name: str
    description: str | None = None
    conditions: list[ConditionCreate] = Field(default_factory=list)
    decision: DecisionCreate | None = None
    legal_sources: list[LegalSourceCreate] = Field(default_factory=list)
    generate_embeddings: bool = Field(default=True, description="Whether to generate embeddings for this rule")


class RuleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    conditions: list[ConditionCreate] | None = None
    decision: DecisionCreate | None = None
    legal_sources: list[LegalSourceCreate] | None = None
    is_active: bool | None = None
    regenerate_embeddings: bool = Field(default=False, description="Whether to regenerate embeddings")


class RuleRead(BaseModel):
    id: int
    rule_id: str
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    is_active: bool
    conditions: list[ConditionRead]
    decision: DecisionRead | None
    legal_sources: list[LegalSourceRead]
    embeddings: list[EmbeddingRead] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class RuleList(BaseModel):
    id: int
    rule_id: str
    name: str
    description: str | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# =============================================================================
# Multi-Mode Similarity Search Schemas
# =============================================================================


class TextSearchRequest(BaseModel):
    """Search rules by natural language query."""

    query: str = Field(description="Natural language search query")
    top_k: int = Field(default=10, ge=1, le=100, description="Number of results to return")
    min_similarity: float = Field(default=0.5, ge=0.0, le=1.0, description="Minimum similarity threshold")


class EntitySearchRequest(BaseModel):
    """Search rules by entity list (field names, operators)."""

    entities: list[str] = Field(description="List of entities to search for (e.g., ['income', 'age'])")
    top_k: int = Field(default=10, ge=1, le=100, description="Number of results to return")


class OutcomeSearchRequest(BaseModel):
    """Search rules by decision outcome."""

    outcome: str = Field(description="Decision outcome to search for (e.g., 'approved', 'eligible')")
    top_k: int = Field(default=10, ge=1, le=100, description="Number of results to return")


class LegalSourceSearchRequest(BaseModel):
    """Search rules by legal citation or source."""

    citation: str = Field(description="Legal citation to search for")
    document_id: str | None = Field(default=None, description="Optional document ID filter")
    top_k: int = Field(default=10, ge=1, le=100, description="Number of results to return")


class HybridSearchRequest(BaseModel):
    """Search with custom embedding type weights."""

    query: str = Field(description="Search query")
    weights: dict[str, float] = Field(
        description="Weights for each embedding type (e.g., {'semantic': 0.3, 'structural': 0.4})"
    )
    top_k: int = Field(default=10, ge=1, le=100, description="Number of results to return")


class SearchResult(BaseModel):
    """Result from similarity search."""

    rule_id: str
    rule_name: str
    score: float = Field(description="Similarity score (0-1, higher is more similar)")
    embedding_type: str
    matched_text: str | None = None


# =============================================================================
# Graph Embedding Schemas
# =============================================================================


class GraphSearchRequest(BaseModel):
    """Search for rules with similar graph structures."""

    rule_id: str = Field(description="Reference rule ID to find similar rules")
    top_k: int = Field(default=10, ge=1, le=100, description="Number of results to return")


class GraphComparisonRequest(BaseModel):
    """Compare graph structures of two rules."""

    rule_id_a: str = Field(description="First rule ID")
    rule_id_b: str = Field(description="Second rule ID")


class GraphNode(BaseModel):
    """Node in a rule graph."""

    id: str
    type: str = Field(description="Node type (rule, condition, entity, decision, legal_source)")
    label: str


class GraphEdge(BaseModel):
    """Edge in a rule graph."""

    source: str
    target: str
    type: str = Field(description="Edge type (HAS_CONDITION, REFERENCES_ENTITY, etc.)")


class RuleGraph(BaseModel):
    """Graph representation of a rule."""

    rule_id: str
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    num_nodes: int
    num_edges: int


class GraphComparisonResult(BaseModel):
    """Result of comparing two rule graphs."""

    rule_id_a: str
    rule_id_b: str
    similarity_score: float = Field(description="Graph similarity (0-1)")
    common_nodes: int
    common_edges: int
    structural_distance: float = Field(description="Graph edit distance normalized")


# =============================================================================
# Store Schemas (merged from storage/stores/schemas.py)
# =============================================================================


class StoreEmbeddingType(StrEnum):
    """Type of embedding vector for in-memory store."""

    SEMANTIC = "semantic"
    STRUCTURAL = "structural"
    ENTITY = "entity"
    LEGAL = "legal"
    GRAPH = "graph"


class EmbeddingRecord(BaseModel):
    """A stored embedding vector with metadata."""

    id: str = Field(default_factory=lambda: f"emb_{uuid.uuid4().hex[:12]}")
    rule_id: str
    embedding_type: StoreEmbeddingType
    vector: list[float]
    dimension: int
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_name: str | None = None
    version: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"use_enum_values": True}


class StoreGraphNode(BaseModel):
    """A node in the rule graph (in-memory store)."""

    id: str = Field(default_factory=lambda: f"node_{uuid.uuid4().hex[:8]}")
    node_type: Literal["rule", "condition", "obligation", "outcome", "entity", "concept"]
    label: str
    rule_id: str | None = None

    properties: dict[str, Any] = Field(default_factory=dict)
    embedding: list[float] | None = None
    embedding_model: str | None = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class StoreGraphEdge(BaseModel):
    """An edge connecting two nodes in the rule graph (in-memory store)."""

    id: str = Field(default_factory=lambda: f"edge_{uuid.uuid4().hex[:8]}")
    source_id: str
    target_id: str
    edge_type: Literal[
        "has_condition",
        "leads_to",
        "requires",
        "references",
        "conflicts_with",
        "supersedes",
        "related_to",
    ]
    weight: float = 1.0

    properties: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class GraphQuery(BaseModel):
    """Query for graph traversal."""

    start_node_ids: list[str] | None = None
    start_node_type: str | None = None
    start_rule_id: str | None = None

    edge_types: list[str] | None = None
    max_depth: int = 2
    direction: Literal["outgoing", "incoming", "both"] = "both"

    node_types: list[str] | None = None
    min_weight: float | None = None

    limit: int = 100


class GraphQueryResult(BaseModel):
    """Result of a graph query."""

    nodes: list[StoreGraphNode] = Field(default_factory=list)
    edges: list[StoreGraphEdge] = Field(default_factory=list)
    paths: list[list[str]] | None = None

    total_nodes: int = 0
    total_edges: int = 0
    query_time_ms: int = 0


class SimilaritySearchRequest(BaseModel):
    """Request for similarity search (in-memory store)."""

    query_vector: list[float] | None = None
    query_text: str | None = None
    rule_id: str | None = None
    embedding_type: StoreEmbeddingType = StoreEmbeddingType.SEMANTIC
    top_k: int = 10
    threshold: float = 0.0


class SimilaritySearchResult(BaseModel):
    """Result of similarity search (in-memory store)."""

    rule_id: str
    similarity: float
    embedding_type: StoreEmbeddingType
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphStats(BaseModel):
    """Statistics about the graph store."""

    total_nodes: int = 0
    total_edges: int = 0
    nodes_by_type: dict[str, int] = Field(default_factory=dict)
    edges_by_type: dict[str, int] = Field(default_factory=dict)
    rules_with_embeddings: int = 0
    avg_edges_per_node: float = 0.0
