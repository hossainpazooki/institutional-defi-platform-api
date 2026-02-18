"""Rule analytics service for comparison, clustering, and conflict detection.

Provides advanced analytics across rules using embeddings:
- Rule comparison across all embedding types
- Clustering with silhouette scores
- Conflict detection (semantic, structural, temporal)
- Similarity search with explanations
- Legal source coverage analysis
"""

from __future__ import annotations

import contextlib
import math
from collections import defaultdict
from typing import TYPE_CHECKING

import numpy as np

from src.embeddings.graph_store import GraphStore
from src.embeddings.models import EmbeddingType
from src.embeddings.store import EmbeddingStore

from .schemas import (
    ClusterAlgorithm,
    ClusterAnalysis,
    ClusterInfo,
    ComparisonResult,
    ConflictInfo,
    ConflictReport,
    ConflictSeverity,
    ConflictType,
    CoverageGap,
    CoverageImportance,
    CoverageReport,
    EmbeddingTypeEnum,
    FrameworkCoverage,
    SimilarityExplanation,
    SimilarRule,
    SimilarRulesResponse,
    UMAPPoint,
    UMAPProjectionResponse,
)

if TYPE_CHECKING:
    from src.rules.service import RuleLoader


# Try to import scikit-learn (optional)
try:
    from sklearn.cluster import DBSCAN, AgglomerativeClustering, KMeans
    from sklearn.metrics import silhouette_score

    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

# Try to import UMAP (optional)
try:
    import umap

    UMAP_AVAILABLE = True
except ImportError:
    UMAP_AVAILABLE = False


def _cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0

    dot_product = sum(a * b for a, b in zip(vec1, vec2, strict=False))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return dot_product / (norm1 * norm2)


class RuleAnalyticsService:
    """Central service for rule comparison and clustering analytics.

    Provides:
    - Rule comparison across all embedding dimensions
    - Clustering based on embeddings with quality metrics
    - Conflict detection between rules
    - Similarity search with explanations
    - Legal source coverage analysis
    """

    def __init__(
        self,
        embedding_store: EmbeddingStore | None = None,
        graph_store: GraphStore | None = None,
        rule_loader: RuleLoader | None = None,
    ):
        """Initialize the analytics service.

        Args:
            embedding_store: Store for rule embeddings
            graph_store: Store for rule graphs
            rule_loader: Loader for rule data
        """
        self._embedding_store = embedding_store or EmbeddingStore()
        self._graph_store = graph_store or GraphStore()
        self._rule_loader = rule_loader

    def _get_rule_embeddings(
        self, rule_id: str, embedding_type: EmbeddingTypeEnum | str | None = None
    ) -> dict[str, list[float]]:
        """Get embeddings for a rule.

        Returns:
            Dict mapping embedding type to vector
        """
        result = {}

        # Handle string embedding type
        if isinstance(embedding_type, str):
            if embedding_type == "all":
                embedding_type = None
            else:
                try:
                    embedding_type = EmbeddingTypeEnum(embedding_type)
                except ValueError:
                    embedding_type = None

        types_to_fetch = (
            [EmbeddingType(embedding_type.value)]
            if embedding_type and embedding_type != EmbeddingTypeEnum.ALL
            else [
                EmbeddingType.SEMANTIC,
                EmbeddingType.STRUCTURAL,
                EmbeddingType.ENTITY,
                EmbeddingType.LEGAL,
            ]
        )

        for emb_type in types_to_fetch:
            records = self._embedding_store.get_by_rule(rule_id, emb_type)
            if records:
                result[emb_type.value] = records[0].vector

        return result

    def _get_rule_name(self, rule_id: str) -> str | None:
        """Get rule name from loader."""
        if not self._rule_loader:
            return None
        rule = self._rule_loader.get_rule(rule_id)
        # Rule has 'description' not 'name'
        return rule.description if rule else None

    def _get_rule_jurisdiction(self, rule_id: str) -> str | None:
        """Get rule jurisdiction from loader."""
        if not self._rule_loader:
            return None
        rule = self._rule_loader.get_rule(rule_id)
        return rule.jurisdiction.value if rule and rule.jurisdiction else None

    def _extract_entities_from_rule(self, rule_id: str) -> list[str]:
        """Extract entity names from a rule's conditions."""
        if not self._rule_loader:
            return []
        rule = self._rule_loader.get_rule(rule_id)
        if not rule:
            return []

        entities = set()
        self._collect_entities_recursive(rule.decision_tree, entities)
        return sorted(entities)

    def _collect_entities_recursive(self, node: dict, entities: set) -> None:
        """Recursively collect entity names from decision tree."""
        if not isinstance(node, dict):
            return

        # Check for condition fields
        if "condition" in node:
            cond = node["condition"]
            if isinstance(cond, dict) and "field" in cond:
                entities.add(cond["field"])

        # Check branches
        for key in ["if_true", "if_false", "branches"]:
            if key in node:
                child = node[key]
                if isinstance(child, dict):
                    self._collect_entities_recursive(child, entities)
                elif isinstance(child, list):
                    for item in child:
                        self._collect_entities_recursive(item, entities)

    def _extract_legal_sources_from_rule(self, rule_id: str) -> list[str]:
        """Extract legal source references from a rule."""
        if not self._rule_loader:
            return []
        rule = self._rule_loader.get_rule(rule_id)
        if not rule or not rule.source:
            return []

        sources = []
        if rule.source.document_id:
            sources.append(rule.source.document_id)
        if rule.source.article:
            sources.append(f"{rule.source.document_id}:{rule.source.article}")
        return sources

    # =========================================================================
    # Rule Comparison
    # =========================================================================

    def compare_rules(
        self,
        rule1_id: str,
        rule2_id: str,
        weights: dict[str, float] | None = None,
        include_graph: bool = True,
    ) -> ComparisonResult:
        """Compare two rules across all embedding dimensions.

        Args:
            rule1_id: First rule ID
            rule2_id: Second rule ID
            weights: Optional weights per embedding type
            include_graph: Whether to include graph comparison

        Returns:
            ComparisonResult with similarity breakdown
        """
        # Default weights
        if weights is None:
            weights = {
                "semantic": 0.4,
                "structural": 0.3,
                "entity": 0.2,
                "legal": 0.1,
            }

        # Get embeddings for both rules
        emb1 = self._get_rule_embeddings(rule1_id)
        emb2 = self._get_rule_embeddings(rule2_id)

        # Calculate similarity per type
        similarity_by_type = {}
        for emb_type in ["semantic", "structural", "entity", "legal"]:
            if emb_type in emb1 and emb_type in emb2:
                similarity_by_type[emb_type] = _cosine_similarity(emb1[emb_type], emb2[emb_type])
            else:
                similarity_by_type[emb_type] = 0.0

        # Calculate weighted overall similarity
        total_weight = sum(weights.get(t, 0) for t in similarity_by_type)
        if total_weight > 0:
            overall_similarity = (
                sum(similarity_by_type[t] * weights.get(t, 0) for t in similarity_by_type) / total_weight
            )
        else:
            overall_similarity = 0.0

        # Extract shared entities
        entities1 = set(self._extract_entities_from_rule(rule1_id))
        entities2 = set(self._extract_entities_from_rule(rule2_id))
        shared_entities = sorted(entities1 & entities2)

        # Extract shared legal sources
        sources1 = set(self._extract_legal_sources_from_rule(rule1_id))
        sources2 = set(self._extract_legal_sources_from_rule(rule2_id))
        shared_legal_sources = sorted(sources1 & sources2)

        # Graph comparison
        structural_comparison = {}
        if include_graph:
            # Get graph stats from graph store
            nodes1 = self._graph_store.get_nodes_by_rule(rule1_id)
            nodes2 = self._graph_store.get_nodes_by_rule(rule2_id)
            structural_comparison = {
                "rule1_nodes": len(nodes1),
                "rule2_nodes": len(nodes2),
                "node_difference": abs(len(nodes1) - len(nodes2)),
            }

        # Detect potential conflicts
        conflict_indicators = []
        # High semantic similarity but from different jurisdictions
        if similarity_by_type.get("semantic", 0) > 0.8:
            jur1 = self._get_rule_jurisdiction(rule1_id)
            jur2 = self._get_rule_jurisdiction(rule2_id)
            if jur1 and jur2 and jur1 != jur2:
                conflict_indicators.append(
                    f"High semantic similarity ({similarity_by_type['semantic']:.2f}) "
                    f"across different jurisdictions ({jur1} vs {jur2})"
                )

        return ComparisonResult(
            rule1_id=rule1_id,
            rule2_id=rule2_id,
            rule1_name=self._get_rule_name(rule1_id),
            rule2_name=self._get_rule_name(rule2_id),
            overall_similarity=overall_similarity,
            similarity_by_type=similarity_by_type,
            structural_comparison=structural_comparison,
            shared_entities=shared_entities,
            shared_legal_sources=shared_legal_sources,
            conflict_indicators=conflict_indicators,
        )

    # =========================================================================
    # Clustering
    # =========================================================================

    def cluster_rules(
        self,
        embedding_type: str = "semantic",
        n_clusters: int | None = None,
        algorithm: str = "kmeans",
        rule_ids: list[str] | None = None,
    ) -> ClusterAnalysis:
        """Cluster rules based on embeddings.

        Args:
            embedding_type: Which embedding type to cluster on
            n_clusters: Number of clusters (auto-detect if None)
            algorithm: Clustering algorithm
            rule_ids: Specific rules to cluster (all if None)

        Returns:
            ClusterAnalysis with cluster details and quality metrics
        """
        # Convert string to enum
        try:
            emb_type_enum = EmbeddingTypeEnum(embedding_type)
        except ValueError:
            emb_type_enum = EmbeddingTypeEnum.SEMANTIC

        try:
            algo_enum = ClusterAlgorithm(algorithm)
        except ValueError:
            algo_enum = ClusterAlgorithm.KMEANS

        if not SKLEARN_AVAILABLE:
            return ClusterAnalysis(
                num_clusters=0,
                algorithm=algo_enum,
                embedding_type=emb_type_enum,
                silhouette_score=0.0,
                clusters=[],
                total_rules=0,
            )

        # Collect all embeddings of specified type
        emb_type = EmbeddingType(embedding_type)
        all_rule_ids = rule_ids if rule_ids else self._embedding_store.list_rules()
        vectors = []
        valid_rule_ids = []

        for rule_id in all_rule_ids:
            records = self._embedding_store.get_by_rule(rule_id, emb_type)
            if records:
                vectors.append(records[0].vector)
                valid_rule_ids.append(rule_id)

        if len(vectors) < 2:
            return ClusterAnalysis(
                num_clusters=0,
                algorithm=algo_enum,
                embedding_type=emb_type_enum,
                silhouette_score=0.0,
                clusters=[],
                total_rules=len(valid_rule_ids),
            )

        X = np.array(vectors)

        # Determine number of clusters
        if n_clusters is None:
            # Heuristic: sqrt(n/2) clusters
            n_clusters = max(2, min(int(np.sqrt(len(X) / 2)), 10))

        # Apply clustering
        if algo_enum == ClusterAlgorithm.KMEANS:
            model = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
            labels = model.fit_predict(X)
            centroids = model.cluster_centers_
        elif algo_enum == ClusterAlgorithm.DBSCAN:
            model = DBSCAN(eps=0.5, min_samples=2)
            labels = model.fit_predict(X)
            centroids = None
        else:  # HIERARCHICAL
            model = AgglomerativeClustering(n_clusters=n_clusters)
            labels = model.fit_predict(X)
            centroids = None

        # Calculate silhouette score
        unique_labels = set(labels)
        sil_score = silhouette_score(X, labels) if len(unique_labels) > 1 and -1 not in unique_labels else 0.0

        # Build cluster info
        clusters = []
        for cluster_id in sorted(unique_labels):
            if cluster_id == -1:  # Skip noise points in DBSCAN
                continue

            # Get rules in this cluster
            cluster_mask = labels == cluster_id
            cluster_rule_ids = [valid_rule_ids[i] for i, m in enumerate(cluster_mask) if m]

            # Find centroid rule (closest to center)
            centroid_rule_id = None
            if centroids is not None and len(cluster_rule_ids) > 0:
                cluster_vectors = X[cluster_mask]
                centroid = centroids[cluster_id]
                distances = np.linalg.norm(cluster_vectors - centroid, axis=1)
                centroid_idx = np.argmin(distances)
                centroid_rule_id = cluster_rule_ids[centroid_idx]

            # Calculate cohesion (average pairwise similarity)
            cluster_vectors = X[cluster_mask]
            if len(cluster_vectors) > 1:
                similarities = []
                for i in range(len(cluster_vectors)):
                    for j in range(i + 1, len(cluster_vectors)):
                        sim = _cosine_similarity(cluster_vectors[i].tolist(), cluster_vectors[j].tolist())
                        similarities.append(sim)
                cohesion = np.mean(similarities) if similarities else 0.0
            else:
                cohesion = 1.0

            # Extract keywords (common entities in cluster)
            keywords = self._extract_cluster_keywords(cluster_rule_ids)

            clusters.append(
                ClusterInfo(
                    cluster_id=int(cluster_id),
                    size=len(cluster_rule_ids),
                    rule_ids=cluster_rule_ids,
                    centroid_rule_id=centroid_rule_id,
                    cohesion_score=float(cohesion),
                    keywords=keywords[:5],  # Top 5 keywords
                )
            )

        return ClusterAnalysis(
            num_clusters=len(clusters),
            algorithm=algo_enum,
            embedding_type=emb_type_enum,
            silhouette_score=float(sil_score),
            clusters=clusters,
            total_rules=len(valid_rule_ids),
        )

    def _extract_cluster_keywords(self, rule_ids: list[str]) -> list[str]:
        """Extract common keywords/entities from cluster rules."""
        entity_counts: dict[str, int] = defaultdict(int)
        for rule_id in rule_ids:
            entities = self._extract_entities_from_rule(rule_id)
            for entity in entities:
                entity_counts[entity] += 1

        # Sort by frequency
        sorted_entities = sorted(entity_counts.items(), key=lambda x: -x[1])
        return [entity for entity, count in sorted_entities if count > 1]

    # =========================================================================
    # Conflict Detection
    # =========================================================================

    def find_conflicts(
        self,
        rule_ids: list[str] | None = None,
        conflict_types: list[str] | None = None,
        threshold: float = 0.7,
    ) -> ConflictReport:
        """Detect potential rule conflicts.

        Args:
            rule_ids: Specific rules to check (all if None)
            conflict_types: Types of conflicts to detect
            threshold: Similarity threshold for conflict detection

        Returns:
            ConflictReport with detected conflicts
        """
        if conflict_types is None:
            conflict_types = ["semantic", "structural"]

        # Convert strings to enums
        conflict_type_enums = []
        for ct in conflict_types:
            with contextlib.suppress(ValueError):
                conflict_type_enums.append(ConflictType(ct))

        if not conflict_type_enums:
            conflict_type_enums = [ConflictType.SEMANTIC, ConflictType.STRUCTURAL]

        # Get rules to analyze
        if rule_ids is None:
            rule_ids = self._embedding_store.list_rules()

        if len(rule_ids) < 2:
            return ConflictReport(
                total_rules_analyzed=len(rule_ids),
                conflicts_found=0,
                conflicts=[],
            )

        conflicts = []

        # Compare all pairs
        for i, rule1_id in enumerate(rule_ids):
            for rule2_id in rule_ids[i + 1 :]:
                # Get embeddings
                emb1 = self._get_rule_embeddings(rule1_id)
                emb2 = self._get_rule_embeddings(rule2_id)

                # Check each conflict type
                for conflict_type in conflict_type_enums:
                    conflict = self._check_conflict_pair(rule1_id, rule2_id, emb1, emb2, conflict_type, threshold)
                    if conflict:
                        conflicts.append(conflict)

        # Count by severity
        high_count = sum(1 for c in conflicts if c.severity == ConflictSeverity.HIGH)
        medium_count = sum(1 for c in conflicts if c.severity == ConflictSeverity.MEDIUM)
        low_count = sum(1 for c in conflicts if c.severity == ConflictSeverity.LOW)

        return ConflictReport(
            total_rules_analyzed=len(rule_ids),
            conflicts_found=len(conflicts),
            conflicts=conflicts,
            high_severity_count=high_count,
            medium_severity_count=medium_count,
            low_severity_count=low_count,
        )

    def _check_conflict_pair(
        self,
        rule1_id: str,
        rule2_id: str,
        emb1: dict[str, list[float]],
        emb2: dict[str, list[float]],
        conflict_type: ConflictType,
        threshold: float,
    ) -> ConflictInfo | None:
        """Check if two rules conflict for a given conflict type."""
        if conflict_type == ConflictType.SEMANTIC:
            return self._check_semantic_conflict(rule1_id, rule2_id, emb1, emb2, threshold)
        elif conflict_type == ConflictType.STRUCTURAL:
            return self._check_structural_conflict(rule1_id, rule2_id, emb1, emb2, threshold)
        elif conflict_type == ConflictType.JURISDICTION:
            return self._check_jurisdiction_conflict(rule1_id, rule2_id, emb1, emb2)
        return None

    def _check_semantic_conflict(
        self,
        rule1_id: str,
        rule2_id: str,
        emb1: dict[str, list[float]],
        emb2: dict[str, list[float]],
        threshold: float,
    ) -> ConflictInfo | None:
        """Check for semantic conflicts (similar meaning, different outcomes)."""
        if "semantic" not in emb1 or "semantic" not in emb2:
            return None

        similarity = _cosine_similarity(emb1["semantic"], emb2["semantic"])
        if similarity < threshold:
            return None

        # For now, flag high similarity as potential conflict
        # In production, would compare actual decision outcomes
        severity = (
            ConflictSeverity.HIGH
            if similarity > 0.9
            else ConflictSeverity.MEDIUM
            if similarity > 0.8
            else ConflictSeverity.LOW
        )

        return ConflictInfo(
            rule1_id=rule1_id,
            rule2_id=rule2_id,
            rule1_name=self._get_rule_name(rule1_id),
            rule2_name=self._get_rule_name(rule2_id),
            conflict_type=ConflictType.SEMANTIC,
            severity=severity,
            description=f"High semantic similarity ({similarity:.2f}) may indicate redundancy or conflict",
            similarity_score=similarity,
            conflicting_aspects=["High textual/semantic overlap"],
            resolution_hints=[
                "Review both rules to ensure consistent outcomes",
                "Consider consolidating if redundant",
            ],
        )

    def _check_structural_conflict(
        self,
        rule1_id: str,
        rule2_id: str,
        emb1: dict[str, list[float]],
        emb2: dict[str, list[float]],
        threshold: float,
    ) -> ConflictInfo | None:
        """Check for structural conflicts (similar structure, different logic)."""
        if "structural" not in emb1 or "structural" not in emb2:
            return None

        similarity = _cosine_similarity(emb1["structural"], emb2["structural"])
        if similarity < threshold:
            return None

        severity = ConflictSeverity.MEDIUM if similarity > 0.85 else ConflictSeverity.LOW

        return ConflictInfo(
            rule1_id=rule1_id,
            rule2_id=rule2_id,
            rule1_name=self._get_rule_name(rule1_id),
            rule2_name=self._get_rule_name(rule2_id),
            conflict_type=ConflictType.STRUCTURAL,
            severity=severity,
            description=f"Similar decision structure ({similarity:.2f}) with potentially different logic",
            similarity_score=similarity,
            conflicting_aspects=["Similar condition patterns"],
            resolution_hints=[
                "Verify decision paths lead to consistent outcomes",
                "Check for overlapping condition coverage",
            ],
        )

    def _check_jurisdiction_conflict(
        self,
        rule1_id: str,
        rule2_id: str,
        emb1: dict[str, list[float]],
        emb2: dict[str, list[float]],
    ) -> ConflictInfo | None:
        """Check for jurisdiction conflicts (same topic, different jurisdictions)."""
        jur1 = self._get_rule_jurisdiction(rule1_id)
        jur2 = self._get_rule_jurisdiction(rule2_id)

        if not jur1 or not jur2 or jur1 == jur2:
            return None

        # Check if semantically similar
        if "semantic" not in emb1 or "semantic" not in emb2:
            return None

        similarity = _cosine_similarity(emb1["semantic"], emb2["semantic"])
        if similarity < 0.7:
            return None

        return ConflictInfo(
            rule1_id=rule1_id,
            rule2_id=rule2_id,
            rule1_name=self._get_rule_name(rule1_id),
            rule2_name=self._get_rule_name(rule2_id),
            conflict_type=ConflictType.JURISDICTION,
            severity=ConflictSeverity.MEDIUM,
            description=f"Cross-jurisdiction rules ({jur1} vs {jur2}) addressing similar topics",
            similarity_score=similarity,
            conflicting_aspects=[
                f"Different jurisdictions: {jur1}, {jur2}",
                "Similar regulatory scope",
            ],
            resolution_hints=[
                "Ensure compliance pathway handles both jurisdictions",
                "Document jurisdictional differences",
            ],
        )

    # =========================================================================
    # Similarity Search
    # =========================================================================

    def find_similar(
        self,
        rule_id: str,
        embedding_type: str = "all",
        top_k: int = 10,
        min_score: float = 0.5,
        include_explanation: bool = True,
    ) -> SimilarRulesResponse:
        """Find rules similar to a given rule.

        Args:
            rule_id: Query rule ID
            embedding_type: Embedding type to search
            top_k: Maximum results
            min_score: Minimum similarity score
            include_explanation: Whether to include explanations

        Returns:
            SimilarRulesResponse with ranked similar rules
        """
        query_embeddings = self._get_rule_embeddings(rule_id, embedding_type)
        if not query_embeddings:
            return SimilarRulesResponse(
                query_rule_id=rule_id,
                query_rule_name=self._get_rule_name(rule_id),
                similar_rules=[],
                total_candidates=0,
            )

        # Get all other rules
        all_rule_ids = self._embedding_store.list_rules()
        candidates = []

        for candidate_id in all_rule_ids:
            if candidate_id == rule_id:
                continue

            candidate_embeddings = self._get_rule_embeddings(candidate_id, embedding_type)
            if not candidate_embeddings:
                continue

            # Calculate similarity per type
            scores_by_type = {}
            for emb_type, query_vec in query_embeddings.items():
                if emb_type in candidate_embeddings:
                    score = _cosine_similarity(query_vec, candidate_embeddings[emb_type])
                    scores_by_type[emb_type] = score

            if not scores_by_type:
                continue

            # Overall score is average
            overall_score = sum(scores_by_type.values()) / len(scores_by_type)
            if overall_score < min_score:
                continue

            candidates.append((candidate_id, overall_score, scores_by_type))

        # Sort by overall score and take top_k
        candidates.sort(key=lambda x: -x[1])
        top_candidates = candidates[:top_k]

        # Build response
        similar_rules = []
        for candidate_id, overall_score, scores_by_type in top_candidates:
            explanation = None
            if include_explanation:
                explanation = self._build_similarity_explanation(rule_id, candidate_id, scores_by_type)

            similar_rules.append(
                SimilarRule(
                    rule_id=candidate_id,
                    rule_name=self._get_rule_name(candidate_id),
                    jurisdiction=self._get_rule_jurisdiction(candidate_id),
                    overall_score=overall_score,
                    scores_by_type=scores_by_type,
                    explanation=explanation,
                )
            )

        return SimilarRulesResponse(
            query_rule_id=rule_id,
            query_rule_name=self._get_rule_name(rule_id),
            similar_rules=similar_rules,
            total_candidates=len(all_rule_ids) - 1,
        )

    def _build_similarity_explanation(
        self,
        query_id: str,
        candidate_id: str,
        scores_by_type: dict[str, float],
    ) -> SimilarityExplanation:
        """Build explanation for why two rules are similar."""
        # Find primary reason
        if scores_by_type:
            best_type = max(scores_by_type.items(), key=lambda x: x[1])
            primary_reason = f"Highest similarity in {best_type[0]} ({best_type[1]:.2f})"
        else:
            primary_reason = "General similarity across embeddings"

        # Get shared entities
        entities1 = set(self._extract_entities_from_rule(query_id))
        entities2 = set(self._extract_entities_from_rule(candidate_id))
        shared_entities = sorted(entities1 & entities2)

        # Get shared legal sources
        sources1 = set(self._extract_legal_sources_from_rule(query_id))
        sources2 = set(self._extract_legal_sources_from_rule(candidate_id))
        shared_legal_sources = sorted(sources1 & sources2)

        # Structural description
        structural_sim = scores_by_type.get("structural", 0)
        structural_desc = (
            f"Decision structures are {'very' if structural_sim > 0.8 else 'moderately'} similar"
            if structural_sim > 0.5
            else None
        )

        # Semantic description
        semantic_sim = scores_by_type.get("semantic", 0)
        semantic_desc = (
            f"Rules address {'highly' if semantic_sim > 0.8 else ''} related regulatory topics"
            if semantic_sim > 0.5
            else None
        )

        return SimilarityExplanation(
            primary_reason=primary_reason,
            shared_entities=shared_entities,
            shared_legal_sources=shared_legal_sources,
            structural_similarity=structural_desc,
            semantic_alignment=semantic_desc,
        )

    # =========================================================================
    # Coverage Analysis
    # =========================================================================

    def analyze_coverage(self) -> CoverageReport:
        """Analyze legal source coverage across rules.

        Returns:
            CoverageReport with coverage statistics and gaps
        """
        if not self._rule_loader:
            return CoverageReport(
                total_rules=0,
                total_legal_sources=0,
                coverage_by_framework={},
                uncovered_sources=[],
                coverage_gaps=[],
            )

        rules = self._rule_loader.get_all_rules()
        total_rules = len(rules)

        # Count rules per framework and article
        framework_rules: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))

        for rule in rules:
            if rule.source and rule.source.document_id:
                framework = rule.source.document_id.split("_")[0].upper()
                article = rule.source.article or "general"
                framework_rules[framework][article].append(rule.rule_id)

        # Build framework coverage
        coverage_by_framework = {}
        for framework, articles in framework_rules.items():
            total_articles = len(articles)
            covered_articles = sum(1 for a in articles.values() if len(a) > 0)
            rules_per_article = {art: len(rules) for art, rules in articles.items()}
            rule_count = sum(rules_per_article.values())

            coverage_by_framework[framework] = FrameworkCoverage(
                framework=framework,
                total_articles=total_articles,
                covered_articles=covered_articles,
                coverage_percentage=(covered_articles / total_articles * 100) if total_articles > 0 else 0.0,
                rules_per_article=rules_per_article,
                rule_count=rule_count,
            )

        # Identify coverage gaps (articles with low rule count)
        coverage_gaps = []
        for framework, coverage in coverage_by_framework.items():
            for article, count in coverage.rules_per_article.items():
                if count < 1:
                    coverage_gaps.append(
                        CoverageGap(
                            framework=framework,
                            article=article,
                            importance=CoverageImportance.HIGH,
                            recommendation=f"Add rules for {framework} {article}",
                        )
                    )

        # Calculate overall coverage
        total_sources = sum(len(articles) for articles in framework_rules.values())
        overall_coverage = 0.0
        if coverage_by_framework:
            overall_coverage = sum(c.coverage_percentage for c in coverage_by_framework.values()) / len(
                coverage_by_framework
            )

        return CoverageReport(
            total_rules=total_rules,
            total_legal_sources=total_sources,
            coverage_by_framework=coverage_by_framework,
            uncovered_sources=[],
            coverage_gaps=coverage_gaps,
            overall_coverage_percentage=overall_coverage,
        )

    # =========================================================================
    # UMAP Projection
    # =========================================================================

    def get_umap_projection(
        self,
        embedding_type: str = "semantic",
        n_components: int = 2,
        n_neighbors: int = 15,
        min_dist: float = 0.1,
        rule_ids: list[str] | None = None,
    ) -> UMAPProjectionResponse:
        """Get UMAP projection of rule embeddings for visualization.

        Args:
            embedding_type: Embedding type to project
            n_components: 2 or 3 dimensions
            n_neighbors: UMAP n_neighbors parameter
            min_dist: UMAP min_dist parameter
            rule_ids: Specific rules (all if None)

        Returns:
            UMAPProjectionResponse with projected points
        """
        # Convert string to enum
        try:
            emb_type_enum = EmbeddingTypeEnum(embedding_type)
        except ValueError:
            emb_type_enum = EmbeddingTypeEnum.SEMANTIC

        if not UMAP_AVAILABLE:
            return UMAPProjectionResponse(
                points=[],
                embedding_type=emb_type_enum,
                n_components=n_components,
                total_rules=0,
            )

        # Collect embeddings
        emb_type = EmbeddingType(embedding_type)
        all_rule_ids = rule_ids if rule_ids else self._embedding_store.list_rules()
        vectors = []
        valid_rule_ids = []

        for rule_id in all_rule_ids:
            records = self._embedding_store.get_by_rule(rule_id, emb_type)
            if records:
                vectors.append(records[0].vector)
                valid_rule_ids.append(rule_id)

        if len(vectors) < 3:
            return UMAPProjectionResponse(
                points=[],
                embedding_type=emb_type_enum,
                n_components=n_components,
                total_rules=len(valid_rule_ids),
            )

        X = np.array(vectors)

        # Apply UMAP
        reducer = umap.UMAP(
            n_components=n_components,
            n_neighbors=min(n_neighbors, len(X) - 1),
            min_dist=min_dist,
            random_state=42,
        )
        projected = reducer.fit_transform(X)

        # Build points
        points = []
        for i, rule_id in enumerate(valid_rule_ids):
            point = UMAPPoint(
                rule_id=rule_id,
                rule_name=self._get_rule_name(rule_id),
                x=float(projected[i, 0]),
                y=float(projected[i, 1]),
                z=float(projected[i, 2]) if n_components == 3 else None,
                jurisdiction=self._get_rule_jurisdiction(rule_id),
            )
            points.append(point)

        return UMAPProjectionResponse(
            points=points,
            embedding_type=emb_type_enum,
            n_components=n_components,
            total_rules=len(valid_rule_ids),
        )
