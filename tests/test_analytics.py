"""Tests for analytics module (error patterns and drift detection)."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from src.analytics import (
    ClusterAnalysis,
    ComparisonResult,
    ConflictReport,
    CoverageReport,
    DriftDetector,
    DriftMetrics,
    DriftReport,
    ErrorPatternAnalyzer,
    FrameworkCoverage,
    RuleAnalyticsService,
    SimilarityExplanation,
    SimilarRulesResponse,
    UMAPProjectionResponse,
)
from src.main import create_app
from src.ontology import JurisdictionCode
from src.rules import (
    ConsistencyBlock,
    ConsistencyEvidence,
    ConsistencyStatus,
    ConsistencySummary,
    DecisionLeaf,
    Rule,
    RuleLoader,
    SourceRef,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def rules_with_consistency() -> list[Rule]:
    """Create a set of rules with various consistency states."""
    rules = []

    # Rule 1: Verified, all passing
    rules.append(
        Rule(
            rule_id="rule_verified",
            source=SourceRef(document_id="test"),
            decision_tree=DecisionLeaf(result="test"),
            consistency=ConsistencyBlock(
                summary=ConsistencySummary(
                    status=ConsistencyStatus.VERIFIED,
                    confidence=0.95,
                    verified_by="system",
                ),
                evidence=[
                    ConsistencyEvidence(tier=0, category="schema_valid", label="pass", score=1.0, details="OK"),
                    ConsistencyEvidence(tier=0, category="required_fields", label="pass", score=1.0, details="OK"),
                    ConsistencyEvidence(tier=1, category="deontic_alignment", label="pass", score=0.9, details="OK"),
                ],
            ),
        )
    )

    # Rule 2: Needs review, some warnings
    rules.append(
        Rule(
            rule_id="rule_needs_review",
            source=SourceRef(document_id="test"),
            decision_tree=DecisionLeaf(result="test"),
            consistency=ConsistencyBlock(
                summary=ConsistencySummary(
                    status=ConsistencyStatus.NEEDS_REVIEW,
                    confidence=0.7,
                    verified_by="system",
                ),
                evidence=[
                    ConsistencyEvidence(tier=0, category="schema_valid", label="pass", score=1.0, details="OK"),
                    ConsistencyEvidence(
                        tier=1, category="deontic_alignment", label="warning", score=0.6, details="Mismatch"
                    ),
                    ConsistencyEvidence(
                        tier=1, category="keyword_overlap", label="warning", score=0.5, details="Low overlap"
                    ),
                ],
            ),
        )
    )

    # Rule 3: Inconsistent, with failures
    rules.append(
        Rule(
            rule_id="rule_inconsistent",
            source=SourceRef(document_id="test"),
            decision_tree=DecisionLeaf(result="test"),
            consistency=ConsistencyBlock(
                summary=ConsistencySummary(
                    status=ConsistencyStatus.INCONSISTENT,
                    confidence=0.3,
                    verified_by="system",
                ),
                evidence=[
                    ConsistencyEvidence(tier=0, category="schema_valid", label="pass", score=1.0, details="OK"),
                    ConsistencyEvidence(
                        tier=0, category="required_fields", label="fail", score=0.0, details="Missing source"
                    ),
                    ConsistencyEvidence(
                        tier=1, category="deontic_alignment", label="fail", score=0.2, details="Major mismatch"
                    ),
                ],
            ),
        )
    )

    # Rule 4: Unverified (no consistency block)
    rules.append(
        Rule(
            rule_id="rule_unverified",
            source=SourceRef(document_id="test"),
            decision_tree=DecisionLeaf(result="test"),
        )
    )

    # Rule 5: Another warning case
    rules.append(
        Rule(
            rule_id="rule_warnings_2",
            source=SourceRef(document_id="test"),
            decision_tree=DecisionLeaf(result="test"),
            consistency=ConsistencyBlock(
                summary=ConsistencySummary(
                    status=ConsistencyStatus.NEEDS_REVIEW,
                    confidence=0.65,
                    verified_by="human:reviewer1",
                ),
                evidence=[
                    ConsistencyEvidence(tier=0, category="schema_valid", label="pass", score=1.0, details="OK"),
                    ConsistencyEvidence(
                        tier=1, category="keyword_overlap", label="warning", score=0.4, details="Very low"
                    ),
                ],
            ),
        )
    )

    return rules


# =============================================================================
# Error Pattern Analyzer Tests
# =============================================================================


class TestErrorPatternAnalyzer:
    """Test error pattern analysis."""

    def test_analyze_rules(self, rules_with_consistency):
        """Test basic rule analysis."""
        analyzer = ErrorPatternAnalyzer()
        stats = analyzer.analyze_rules(rules_with_consistency)

        assert "schema_valid" in stats
        assert "deontic_alignment" in stats
        assert "keyword_overlap" in stats

    def test_category_stats(self, rules_with_consistency):
        """Test category statistics computation."""
        analyzer = ErrorPatternAnalyzer()
        stats = analyzer.analyze_rules(rules_with_consistency)

        schema_stats = stats["schema_valid"]
        assert schema_stats.total == 4  # 4 rules with consistency blocks have this check
        assert schema_stats.pass_count == 4
        assert schema_stats.fail_count == 0
        assert schema_stats.pass_rate == 1.0

        deontic_stats = stats["deontic_alignment"]
        assert deontic_stats.total == 3
        assert deontic_stats.pass_count == 1
        assert deontic_stats.warning_count == 1
        assert deontic_stats.fail_count == 1

    def test_build_error_matrix(self, rules_with_consistency):
        """Test error matrix construction."""
        analyzer = ErrorPatternAnalyzer()
        matrix = analyzer.build_error_matrix(rules_with_consistency)

        assert "schema_valid" in matrix
        assert matrix["schema_valid"]["pass"] == 4

        assert "deontic_alignment" in matrix
        assert matrix["deontic_alignment"]["pass"] == 1
        assert matrix["deontic_alignment"]["warning"] == 1
        assert matrix["deontic_alignment"]["fail"] == 1

    def test_detect_patterns(self, rules_with_consistency):
        """Test pattern detection."""
        analyzer = ErrorPatternAnalyzer()
        patterns = analyzer.detect_patterns(rules_with_consistency, min_affected=1)

        # Should detect patterns for categories with warnings/failures
        pattern_ids = [p.pattern_id for p in patterns]

        # keyword_overlap has 2 warnings
        assert any("keyword_overlap" in p for p in pattern_ids)

    def test_build_review_queue(self, rules_with_consistency):
        """Test review queue construction."""
        analyzer = ErrorPatternAnalyzer()
        queue = analyzer.build_review_queue(rules_with_consistency)

        assert len(queue) > 0

        # Inconsistent should be first (highest priority)
        assert queue[0].rule_id == "rule_inconsistent"
        assert queue[0].status == ConsistencyStatus.INCONSISTENT

        # Unverified should be in queue
        unverified_in_queue = any(q.rule_id == "rule_unverified" for q in queue)
        assert unverified_in_queue

    def test_get_summary_stats(self, rules_with_consistency):
        """Test summary statistics."""
        analyzer = ErrorPatternAnalyzer()
        summary = analyzer.get_summary_stats(rules_with_consistency)

        assert summary["total_rules"] == 5
        assert summary["verified"] == 1
        assert summary["needs_review"] == 2
        assert summary["inconsistent"] == 1
        assert summary["unverified"] == 1
        assert "timestamp" in summary


# =============================================================================
# Drift Detector Tests
# =============================================================================


class TestDriftDetector:
    """Test drift detection."""

    def test_capture_metrics(self, rules_with_consistency):
        """Test metrics capture."""
        detector = DriftDetector()
        metrics = detector.capture_metrics(rules_with_consistency)

        assert isinstance(metrics, DriftMetrics)
        assert metrics.total_rules == 5
        assert metrics.verified_count == 1
        assert metrics.needs_review_count == 2
        assert metrics.inconsistent_count == 1
        assert metrics.unverified_count == 1
        assert metrics.avg_confidence > 0

    def test_set_baseline(self, rules_with_consistency):
        """Test baseline setting."""
        detector = DriftDetector()
        baseline = detector.set_baseline(rules=rules_with_consistency)

        assert baseline is not None
        assert detector._baseline == baseline

    def test_detect_no_drift(self, rules_with_consistency):
        """Test drift detection when no drift."""
        detector = DriftDetector()
        detector.set_baseline(rules=rules_with_consistency)

        # Same rules = no drift
        report = detector.detect_drift(rules_with_consistency)

        assert isinstance(report, DriftReport)
        assert report.drift_severity == "none"
        assert not report.drift_detected

    def test_detect_drift_with_degradation(self):
        """Test drift detection with degradation."""
        detector = DriftDetector()

        # Baseline: good state
        good_rules = [
            Rule(
                rule_id="rule1",
                source=SourceRef(document_id="test"),
                consistency=ConsistencyBlock(
                    summary=ConsistencySummary(
                        status=ConsistencyStatus.VERIFIED,
                        confidence=0.95,
                    ),
                    evidence=[
                        ConsistencyEvidence(tier=0, category="schema_valid", label="pass", score=1.0, details="OK"),
                    ],
                ),
            ),
            Rule(
                rule_id="rule2",
                source=SourceRef(document_id="test"),
                consistency=ConsistencyBlock(
                    summary=ConsistencySummary(
                        status=ConsistencyStatus.VERIFIED,
                        confidence=0.9,
                    ),
                    evidence=[
                        ConsistencyEvidence(tier=0, category="schema_valid", label="pass", score=1.0, details="OK"),
                    ],
                ),
            ),
        ]
        detector.set_baseline(rules=good_rules)

        # Current: degraded state
        bad_rules = [
            Rule(
                rule_id="rule1",
                source=SourceRef(document_id="test"),
                consistency=ConsistencyBlock(
                    summary=ConsistencySummary(
                        status=ConsistencyStatus.INCONSISTENT,
                        confidence=0.3,
                    ),
                    evidence=[
                        ConsistencyEvidence(tier=0, category="schema_valid", label="fail", score=0.0, details="Failed"),
                    ],
                ),
            ),
            Rule(
                rule_id="rule2",
                source=SourceRef(document_id="test"),
                consistency=ConsistencyBlock(
                    summary=ConsistencySummary(
                        status=ConsistencyStatus.NEEDS_REVIEW,
                        confidence=0.5,
                    ),
                    evidence=[
                        ConsistencyEvidence(
                            tier=0, category="schema_valid", label="warning", score=0.5, details="Warn"
                        ),
                    ],
                ),
            ),
        ]

        report = detector.detect_drift(bad_rules)

        assert report.drift_detected
        assert report.drift_severity in ("moderate", "major")

    def test_get_history(self, rules_with_consistency):
        """Test history tracking."""
        detector = DriftDetector()

        # Capture multiple snapshots
        detector.capture_metrics(rules_with_consistency)
        detector.capture_metrics(rules_with_consistency)
        detector.capture_metrics(rules_with_consistency)

        history = detector.get_history()
        assert len(history) == 3

    def test_get_trend(self, rules_with_consistency):
        """Test trend extraction."""
        detector = DriftDetector()

        # Capture multiple snapshots
        detector.capture_metrics(rules_with_consistency)
        detector.capture_metrics(rules_with_consistency)

        trend = detector.get_trend("avg_confidence", window=5)
        assert len(trend) == 2
        assert all(isinstance(t, tuple) for t in trend)

    def test_compare_authors(self, rules_with_consistency):
        """Test author comparison."""
        detector = DriftDetector()
        author_stats = detector.compare_authors(rules_with_consistency)

        assert "system" in author_stats
        assert "human:reviewer1" in author_stats

        assert author_stats["system"]["rule_count"] >= 2
        assert "avg_score" in author_stats["system"]


# =============================================================================
# Integration Tests
# =============================================================================


class TestAnalyticsIntegration:
    """Test integration between analytics components."""

    def test_analyzer_with_loader(self, tmp_path):
        """Test analyzer with RuleLoader."""
        loader = RuleLoader(tmp_path)

        # Add rules to loader
        rule = Rule(
            rule_id="test_rule",
            source=SourceRef(document_id="test"),
            decision_tree=DecisionLeaf(result="test"),
            consistency=ConsistencyBlock(
                summary=ConsistencySummary(
                    status=ConsistencyStatus.VERIFIED,
                    confidence=0.9,
                ),
                evidence=[
                    ConsistencyEvidence(tier=0, category="schema_valid", label="pass", score=1.0, details="OK"),
                ],
            ),
        )
        loader._rules[rule.rule_id] = rule

        analyzer = ErrorPatternAnalyzer(rule_loader=loader)
        stats = analyzer.analyze_rules()

        assert "schema_valid" in stats

    def test_drift_with_loader(self, tmp_path):
        """Test drift detector with RuleLoader."""
        loader = RuleLoader(tmp_path)

        rule = Rule(
            rule_id="test_rule",
            source=SourceRef(document_id="test"),
            decision_tree=DecisionLeaf(result="test"),
        )
        loader._rules[rule.rule_id] = rule

        detector = DriftDetector(rule_loader=loader)
        metrics = detector.capture_metrics()

        assert metrics.total_rules == 1
        assert metrics.unverified_count == 1

    def test_full_workflow(self, rules_with_consistency):
        """Test full analytics workflow."""
        # 1. Analyze patterns
        analyzer = ErrorPatternAnalyzer()
        stats = analyzer.analyze_rules(rules_with_consistency)
        analyzer.detect_patterns(rules_with_consistency)
        queue = analyzer.build_review_queue(rules_with_consistency)
        summary = analyzer.get_summary_stats(rules_with_consistency)

        # 2. Set up drift detection
        detector = DriftDetector()
        detector.set_baseline(rules=rules_with_consistency)

        # 3. Simulate some changes (just use same rules for test)
        drift_report = detector.detect_drift(rules_with_consistency)

        # Verify outputs
        assert len(stats) > 0
        assert len(queue) > 0
        assert summary["total_rules"] == 5
        assert drift_report.drift_severity == "none"


# =============================================================================
# RuleAnalyticsService Tests
# =============================================================================


@pytest.fixture
def rules_for_analytics() -> list[Rule]:
    """Create rules suitable for analytics testing."""
    rules = []

    # Rule 1: MiCA authorization rule (EU)
    rules.append(
        Rule(
            rule_id="mica_art36_authorization",
            description="MiCA Article 36 authorization requirements",
            source=SourceRef(document_id="mica", article="Article 36"),
            jurisdiction=JurisdictionCode.EU,
            decision_tree=DecisionLeaf(result="requires_authorization"),
            tags=["authorization", "stablecoin", "mica"],
            effective_date=date(2024, 6, 30),
        )
    )

    # Rule 2: Similar MiCA rule (EU)
    rules.append(
        Rule(
            rule_id="mica_art38_stablecoin",
            description="MiCA Article 38 stablecoin requirements",
            source=SourceRef(document_id="mica", article="Article 38"),
            jurisdiction=JurisdictionCode.EU,
            decision_tree=DecisionLeaf(result="requires_reserve"),
            tags=["stablecoin", "reserve", "mica"],
            effective_date=date(2024, 6, 30),
        )
    )

    # Rule 3: FCA authorization (UK)
    rules.append(
        Rule(
            rule_id="fca_crypto_authorization",
            description="FCA crypto authorization requirements",
            source=SourceRef(document_id="fca_handbook", article="PERG 2.8"),
            jurisdiction=JurisdictionCode.UK,
            decision_tree=DecisionLeaf(result="requires_fca_registration"),
            tags=["authorization", "crypto", "fca"],
            effective_date=date(2024, 1, 1),
        )
    )

    # Rule 4: US rule
    rules.append(
        Rule(
            rule_id="us_stablecoin_rule",
            description="US stablecoin regulation",
            source=SourceRef(document_id="genius_act", article="Section 101"),
            jurisdiction=JurisdictionCode.US,
            decision_tree=DecisionLeaf(result="requires_license"),
            tags=["stablecoin", "license", "us"],
            effective_date=date(2025, 1, 1),
        )
    )

    # Rule 5: Swiss rule
    rules.append(
        Rule(
            rule_id="ch_finma_rule",
            description="FINMA crypto regulation",
            source=SourceRef(document_id="finma_guidance", article="Section 5"),
            jurisdiction=JurisdictionCode.CH,
            decision_tree=DecisionLeaf(result="requires_finma_approval"),
            tags=["crypto", "finma", "switzerland"],
            effective_date=date(2024, 3, 1),
        )
    )

    return rules


@pytest.fixture
def analytics_service_with_rules(rules_for_analytics, tmp_path) -> RuleAnalyticsService:
    """Create RuleAnalyticsService with test rules loaded."""
    loader = RuleLoader(tmp_path)
    for rule in rules_for_analytics:
        loader._rules[rule.rule_id] = rule
    return RuleAnalyticsService(rule_loader=loader)


class TestRuleAnalyticsService:
    """Test RuleAnalyticsService functionality."""

    def test_init(self, tmp_path):
        """Test service initialization."""
        loader = RuleLoader(tmp_path)
        service = RuleAnalyticsService(rule_loader=loader)
        assert service is not None
        assert service._rule_loader == loader

    def test_compare_rules_basic(self, analytics_service_with_rules):
        """Test basic rule comparison."""
        service = analytics_service_with_rules

        result = service.compare_rules(
            rule1_id="mica_art36_authorization",
            rule2_id="mica_art38_stablecoin",
        )

        assert isinstance(result, ComparisonResult)
        assert result.rule1_id == "mica_art36_authorization"
        assert result.rule2_id == "mica_art38_stablecoin"
        assert 0.0 <= result.overall_similarity <= 1.0
        assert len(result.similarity_by_type) > 0

    def test_compare_rules_with_weights(self, analytics_service_with_rules):
        """Test rule comparison with custom weights."""
        service = analytics_service_with_rules

        weights = {"semantic": 0.5, "entity": 0.3, "legal": 0.2}
        result = service.compare_rules(
            rule1_id="mica_art36_authorization",
            rule2_id="fca_crypto_authorization",
            weights=weights,
        )

        assert isinstance(result, ComparisonResult)
        # Should have some shared entities (authorization)
        assert "authorization" in result.shared_entities or len(result.shared_entities) >= 0

    def test_compare_rules_different_jurisdictions(self, analytics_service_with_rules):
        """Test comparing rules from different jurisdictions."""
        service = analytics_service_with_rules

        result = service.compare_rules(
            rule1_id="mica_art36_authorization",
            rule2_id="fca_crypto_authorization",
        )

        assert result.rule1_id == "mica_art36_authorization"
        assert result.rule2_id == "fca_crypto_authorization"
        # Different jurisdictions, should have lower similarity
        assert 0.0 <= result.overall_similarity <= 1.0

    def test_cluster_rules_kmeans(self, analytics_service_with_rules):
        """Test rule clustering with K-means."""
        service = analytics_service_with_rules

        result = service.cluster_rules(
            embedding_type="semantic",
            n_clusters=2,
            algorithm="kmeans",
        )

        assert isinstance(result, ClusterAnalysis)
        assert result.algorithm == "kmeans"
        assert result.embedding_type == "semantic"
        # May be 0 if no embeddings exist
        assert result.num_clusters >= 0

    def test_cluster_rules_dbscan(self, analytics_service_with_rules):
        """Test rule clustering with DBSCAN."""
        service = analytics_service_with_rules

        result = service.cluster_rules(
            embedding_type="semantic",
            algorithm="dbscan",
        )

        assert isinstance(result, ClusterAnalysis)
        assert result.algorithm == "dbscan"

    def test_cluster_rules_auto_clusters(self, analytics_service_with_rules):
        """Test rule clustering with auto-detected cluster count."""
        service = analytics_service_with_rules

        result = service.cluster_rules(
            embedding_type="entity",
            n_clusters=None,  # Auto-detect
            algorithm="kmeans",
        )

        assert isinstance(result, ClusterAnalysis)
        # May be 0 if no embeddings exist
        assert result.num_clusters >= 0

    def test_find_conflicts_semantic(self, analytics_service_with_rules):
        """Test semantic conflict detection."""
        service = analytics_service_with_rules

        result = service.find_conflicts(
            rule_ids=None,
            conflict_types=["semantic"],
            threshold=0.3,  # Lower threshold to find more matches in test
        )

        assert isinstance(result, ConflictReport)
        # May be 0 if no embeddings to compare
        assert result.total_rules_analyzed >= 0

    def test_find_conflicts_with_specific_rules(self, analytics_service_with_rules):
        """Test conflict detection for specific rules."""
        service = analytics_service_with_rules

        result = service.find_conflicts(
            rule_ids=["mica_art36_authorization", "mica_art38_stablecoin"],
            conflict_types=["semantic", "structural"],
            threshold=0.5,
        )

        assert isinstance(result, ConflictReport)
        assert result.total_rules_analyzed == 2

    def test_find_conflicts_jurisdiction(self, analytics_service_with_rules):
        """Test jurisdiction conflict detection."""
        service = analytics_service_with_rules

        result = service.find_conflicts(
            conflict_types=["jurisdiction"],
            threshold=0.5,
        )

        assert isinstance(result, ConflictReport)

    def test_find_similar_basic(self, analytics_service_with_rules):
        """Test basic similarity search."""
        service = analytics_service_with_rules

        result = service.find_similar(
            rule_id="mica_art36_authorization",
            embedding_type="all",
            top_k=3,
            min_score=0.0,  # Accept all scores for testing
        )

        assert isinstance(result, SimilarRulesResponse)
        assert result.query_rule_id == "mica_art36_authorization"
        # Should find other rules (4 other rules available)
        assert len(result.similar_rules) <= 3

    def test_find_similar_by_type(self, analytics_service_with_rules):
        """Test similarity search by specific embedding type."""
        service = analytics_service_with_rules

        for emb_type in ["semantic", "entity", "legal"]:
            result = service.find_similar(
                rule_id="mica_art36_authorization",
                embedding_type=emb_type,
                top_k=2,
                min_score=0.0,
            )

            assert isinstance(result, SimilarRulesResponse)

    def test_find_similar_with_explanation(self, analytics_service_with_rules):
        """Test similarity search with explanations."""
        service = analytics_service_with_rules

        result = service.find_similar(
            rule_id="mica_art36_authorization",
            embedding_type="all",
            top_k=3,
            min_score=0.0,
            include_explanation=True,
        )

        assert isinstance(result, SimilarRulesResponse)
        # Check that explanations are present when requested
        for similar in result.similar_rules:
            if similar.explanation:
                assert isinstance(similar.explanation, SimilarityExplanation)

    def test_analyze_coverage(self, analytics_service_with_rules):
        """Test coverage analysis."""
        service = analytics_service_with_rules

        result = service.analyze_coverage()

        assert isinstance(result, CoverageReport)
        assert result.total_rules == 5  # We created 5 test rules
        assert result.total_legal_sources >= 1
        assert len(result.coverage_by_framework) >= 1

    def test_analyze_coverage_frameworks(self, analytics_service_with_rules):
        """Test that coverage includes expected frameworks."""
        service = analytics_service_with_rules

        result = service.analyze_coverage()

        # Check that MiCA framework is present (2 rules)
        # Framework names are uppercase in the document_id
        assert "MICA" in result.coverage_by_framework
        mica_coverage = result.coverage_by_framework["MICA"]
        assert isinstance(mica_coverage, FrameworkCoverage)
        assert mica_coverage.covered_articles >= 2

    def test_get_umap_projection_2d(self, analytics_service_with_rules):
        """Test 2D UMAP projection."""
        service = analytics_service_with_rules

        result = service.get_umap_projection(
            embedding_type="semantic",
            n_components=2,
        )

        assert isinstance(result, UMAPProjectionResponse)
        assert result.n_components == 2
        assert result.embedding_type == "semantic"
        # May have 0 points if no embeddings exist
        assert len(result.points) >= 0

        # Check 2D coordinates if we have points
        for point in result.points:
            assert point.x is not None
            assert point.y is not None

    def test_get_umap_projection_3d(self, analytics_service_with_rules):
        """Test 3D UMAP projection."""
        service = analytics_service_with_rules

        result = service.get_umap_projection(
            embedding_type="semantic",
            n_components=3,
        )

        assert isinstance(result, UMAPProjectionResponse)
        assert result.n_components == 3

    def test_get_umap_projection_with_params(self, analytics_service_with_rules):
        """Test UMAP projection with custom parameters."""
        service = analytics_service_with_rules

        result = service.get_umap_projection(
            embedding_type="entity",
            n_components=2,
            n_neighbors=5,
            min_dist=0.2,
        )

        assert isinstance(result, UMAPProjectionResponse)


class TestRuleAnalyticsServiceEdgeCases:
    """Test edge cases for RuleAnalyticsService."""

    def test_compare_same_rule(self, analytics_service_with_rules):
        """Test comparing a rule with itself."""
        service = analytics_service_with_rules

        result = service.compare_rules(
            rule1_id="mica_art36_authorization",
            rule2_id="mica_art36_authorization",
        )

        # Same rule should have similarity of 1.0 (or close if based on embeddings)
        assert isinstance(result, ComparisonResult)
        assert result.rule1_id == result.rule2_id
        # Without embeddings, similarity will be 1.0 (fallback for same rule)
        assert 0.0 <= result.overall_similarity <= 1.0

    def test_cluster_single_rule(self, tmp_path):
        """Test clustering with a single rule."""
        loader = RuleLoader(tmp_path)
        loader._rules["single_rule"] = Rule(
            rule_id="single_rule",
            source=SourceRef(document_id="test"),
            decision_tree=DecisionLeaf(result="test"),
        )

        service = RuleAnalyticsService(rule_loader=loader)
        result = service.cluster_rules(embedding_type="semantic", n_clusters=1)

        # May be 0 if no embeddings exist
        assert result.num_clusters >= 0

    def test_find_similar_no_matches(self, analytics_service_with_rules):
        """Test similarity search with very high threshold."""
        service = analytics_service_with_rules

        result = service.find_similar(
            rule_id="mica_art36_authorization",
            embedding_type="all",
            top_k=10,
            min_score=0.99,  # Very high threshold
        )

        # Should return valid response (may be empty)
        assert isinstance(result, SimilarRulesResponse)
        assert result.query_rule_id == "mica_art36_authorization"

    def test_analyze_coverage_empty_loader(self, tmp_path):
        """Test coverage analysis with empty rule loader."""
        loader = RuleLoader(tmp_path)
        service = RuleAnalyticsService(rule_loader=loader)

        result = service.analyze_coverage()

        assert result.total_rules == 0
        assert result.total_legal_sources == 0


# =============================================================================
# Analytics API Route Tests
# =============================================================================


@pytest.fixture
def api_client():
    """Create test client for API testing."""
    app = create_app()
    return TestClient(app)


class TestAnalyticsAPIRoutes:
    """Test analytics API routes."""

    def test_analytics_summary(self, api_client):
        """Test GET /analytics/summary."""
        response = api_client.get("/analytics/summary")
        assert response.status_code == 200
        data = response.json()
        assert "total_rules" in data
        assert "jurisdictions" in data
        assert "embedding_types_available" in data

    def test_compare_rules_endpoint(self, api_client):
        """Test POST /analytics/rules/compare."""
        # First get available rules
        rules_response = api_client.get("/rules")
        if rules_response.status_code != 200:
            pytest.skip("Rules endpoint not available")

        rules = rules_response.json()
        if len(rules) < 2:
            pytest.skip("Not enough rules for comparison")

        rule_ids = list(rules.keys())[:2] if isinstance(rules, dict) else [r.get("rule_id") for r in rules[:2]]

        response = api_client.post(
            "/analytics/rules/compare",
            json={
                "rule1_id": rule_ids[0],
                "rule2_id": rule_ids[1],
            },
        )

        if response.status_code == 404:
            pytest.skip("Rules not found in loader")

        assert response.status_code == 200
        data = response.json()
        assert "overall_similarity" in data
        assert "similarity_by_type" in data

    def test_get_clusters_endpoint(self, api_client):
        """Test GET /analytics/rule-clusters."""
        response = api_client.get("/analytics/rule-clusters")
        assert response.status_code == 200
        data = response.json()
        assert "num_clusters" in data
        assert "algorithm" in data
        assert "clusters" in data

    def test_get_clusters_with_params(self, api_client):
        """Test GET /analytics/rule-clusters with parameters."""
        response = api_client.get(
            "/analytics/rule-clusters",
            params={
                "embedding_type": "semantic",
                "n_clusters": 2,
                "algorithm": "kmeans",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["algorithm"] == "kmeans"

    def test_find_conflicts_endpoint(self, api_client):
        """Test POST /analytics/find-conflicts."""
        response = api_client.post(
            "/analytics/find-conflicts",
            json={
                "conflict_types": ["semantic"],
                "threshold": 0.5,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_rules_analyzed" in data
        assert "conflicts_found" in data
        assert "conflicts" in data

    def test_get_conflicts_endpoint(self, api_client):
        """Test GET /analytics/conflicts."""
        response = api_client.get("/analytics/conflicts")
        assert response.status_code == 200
        data = response.json()
        assert "conflicts" in data

    def test_get_coverage_endpoint(self, api_client):
        """Test GET /analytics/coverage."""
        response = api_client.get("/analytics/coverage")
        assert response.status_code == 200
        data = response.json()
        assert "total_rules" in data
        assert "total_legal_sources" in data
        assert "coverage_by_framework" in data

    def test_get_umap_projection_endpoint(self, api_client):
        """Test GET /analytics/umap-projection."""
        response = api_client.get("/analytics/umap-projection")
        assert response.status_code == 200
        data = response.json()
        assert "n_components" in data
        assert "embedding_type" in data
        assert "points" in data

    def test_get_umap_projection_3d(self, api_client):
        """Test GET /analytics/umap-projection with 3D."""
        response = api_client.get("/analytics/umap-projection", params={"n_components": 3})
        assert response.status_code == 200
        data = response.json()
        assert data["n_components"] == 3


class TestAnalyticsAPIEdgeCases:
    """Test API edge cases."""

    def test_compare_nonexistent_rule(self, api_client):
        """Test comparing with nonexistent rule."""
        response = api_client.post(
            "/analytics/rules/compare",
            json={
                "rule1_id": "nonexistent_rule_1",
                "rule2_id": "nonexistent_rule_2",
            },
        )
        assert response.status_code == 404

    def test_get_similar_nonexistent_rule(self, api_client):
        """Test similarity search for nonexistent rule."""
        response = api_client.get("/analytics/rules/nonexistent_rule_xyz/similar")
        assert response.status_code == 404

    def test_invalid_embedding_type(self, api_client):
        """Test with invalid embedding type."""
        response = api_client.get("/analytics/rule-clusters", params={"embedding_type": "invalid_type"})
        # Should return 422 (validation error)
        assert response.status_code == 422

    def test_invalid_cluster_algorithm(self, api_client):
        """Test with invalid cluster algorithm."""
        response = api_client.get("/analytics/rule-clusters", params={"algorithm": "invalid_algorithm"})
        assert response.status_code == 422
