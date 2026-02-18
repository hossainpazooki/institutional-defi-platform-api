"""Tests for KE-internal API endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

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

if TYPE_CHECKING:
    from pathlib import Path

# =============================================================================
# Test Client Setup
# =============================================================================


@pytest.fixture
def ke_client(tmp_path: Path):
    """Create test client with KE routes."""
    import sys

    from fastapi import FastAPI

    # Must use sys.modules to get the actual module (src.ke.__init__ shadows it)
    from src.ke.router import router as ke_router

    ke_router_module = sys.modules["src.ke.router"]

    # Save original state
    original_ke_service = ke_router_module._ke_service

    # Reset module state
    ke_router_module._ke_service = None

    # Create test rules
    loader = RuleLoader(tmp_path)

    rules = [
        Rule(
            rule_id="test_rule_verified",
            source=SourceRef(document_id="mica_2023", article="36"),
            description="Test rule that is verified",
            tags=["test", "mica"],
            decision_tree=DecisionLeaf(result="permitted"),
            consistency=ConsistencyBlock(
                summary=ConsistencySummary(
                    status=ConsistencyStatus.VERIFIED,
                    confidence=0.95,
                    verified_by="system",
                ),
                evidence=[
                    ConsistencyEvidence(tier=0, category="schema_valid", label="pass", score=1.0, details="OK"),
                    ConsistencyEvidence(tier=0, category="required_fields", label="pass", score=1.0, details="OK"),
                ],
            ),
        ),
        Rule(
            rule_id="test_rule_needs_review",
            source=SourceRef(document_id="mica_2023", article="37"),
            description="Test rule needing review",
            tags=["test", "mica"],
            decision_tree=DecisionLeaf(result="required"),
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
                ],
            ),
        ),
        Rule(
            rule_id="test_rule_no_consistency",
            source=SourceRef(document_id="mica_2023", article="38"),
            description="Test rule without consistency",
            tags=["test"],
            decision_tree=DecisionLeaf(result="test"),
        ),
    ]

    for rule in rules:
        loader._rules[rule.rule_id] = rule

    # Inject test service with pre-loaded loader
    from src.ke.service import KEService

    svc = KEService()
    svc._rule_loader = loader
    ke_router_module._ke_service = svc

    # Create FastAPI app
    app = FastAPI()
    app.include_router(ke_router)

    yield TestClient(app)

    # Restore original state
    ke_router_module._ke_service = original_ke_service


# =============================================================================
# Verification Endpoint Tests
# =============================================================================


class TestVerifyEndpoints:
    """Test consistency verification endpoints."""

    def test_verify_rule(self, ke_client):
        """Test verifying a single rule."""
        response = ke_client.post(
            "/ke/verify",
            json={"rule_id": "test_rule_verified", "tiers": [0]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["rule_id"] == "test_rule_verified"
        assert data["status"] in ["verified", "needs_review", "inconsistent"]
        assert data["evidence_count"] > 0

    def test_verify_rule_not_found(self, ke_client):
        """Test verifying non-existent rule."""
        response = ke_client.post(
            "/ke/verify",
            json={"rule_id": "nonexistent_rule"},
        )

        assert response.status_code == 404

    def test_verify_all_rules(self, ke_client):
        """Test verifying all rules."""
        response = ke_client.post("/ke/verify-all?tiers=0&tiers=1")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert "results" in data


# =============================================================================
# Analytics Endpoint Tests
# =============================================================================


class TestAnalyticsEndpoints:
    """Test analytics endpoints."""

    def test_get_summary(self, ke_client):
        """Test getting analytics summary."""
        response = ke_client.get("/ke/analytics/summary")

        assert response.status_code == 200
        data = response.json()
        assert "total_rules" in data
        assert data["total_rules"] == 3
        assert "verified" in data
        assert "timestamp" in data

    def test_get_patterns(self, ke_client):
        """Test getting error patterns."""
        response = ke_client.get("/ke/analytics/patterns?min_affected=1")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_error_matrix(self, ke_client):
        """Test getting error matrix."""
        response = ke_client.get("/ke/analytics/matrix")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        # Should have at least schema_valid category
        assert "schema_valid" in data

    def test_get_review_queue(self, ke_client):
        """Test getting review queue."""
        response = ke_client.get("/ke/analytics/review-queue?max_items=10")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

        # Rules needing review should be in queue
        rule_ids = [item["rule_id"] for item in data]
        assert "test_rule_needs_review" in rule_ids or "test_rule_no_consistency" in rule_ids


# =============================================================================
# Drift Detection Endpoint Tests
# =============================================================================


class TestDriftEndpoints:
    """Test drift detection endpoints."""

    def test_set_baseline(self, ke_client):
        """Test setting drift baseline."""
        response = ke_client.post("/ke/drift/baseline")

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Baseline set"
        assert "timestamp" in data
        assert data["total_rules"] == 3

    def test_detect_drift(self, ke_client):
        """Test detecting drift."""
        # First set baseline
        ke_client.post("/ke/drift/baseline")

        # Then detect drift
        response = ke_client.get("/ke/drift/detect")

        assert response.status_code == 200
        data = response.json()
        assert "drift_detected" in data
        assert "drift_severity" in data
        assert "summary" in data

    def test_get_history(self, ke_client):
        """Test getting drift history."""
        # Capture some metrics first
        ke_client.post("/ke/drift/baseline")

        response = ke_client.get("/ke/drift/history?window=5")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_author_comparison(self, ke_client):
        """Test getting author comparison."""
        response = ke_client.get("/ke/drift/authors")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        # Should have "system" author from test rules
        assert "system" in data


# =============================================================================
# Context Endpoint Tests
# =============================================================================


class TestContextEndpoints:
    """Test rule context endpoints."""

    def test_get_rule_context(self, ke_client):
        """Test getting rule context."""
        response = ke_client.get("/ke/context/test_rule_verified")

        assert response.status_code == 200
        data = response.json()
        assert data["rule_id"] == "test_rule_verified"
        assert "source_passages" in data
        assert "cross_references" in data
        assert "related_rules" in data

    def test_get_rule_context_not_found(self, ke_client):
        """Test getting context for non-existent rule."""
        response = ke_client.get("/ke/context/nonexistent")

        assert response.status_code == 404

    def test_get_related_rules(self, ke_client):
        """Test getting related rules."""
        response = ke_client.get("/ke/related/test_rule_verified?top_k=5")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

        # Related rules should be from same document
        for related in data:
            assert "rule_id" in related
            assert related["rule_id"] != "test_rule_verified"

    def test_get_related_rules_not_found(self, ke_client):
        """Test getting related for non-existent rule."""
        response = ke_client.get("/ke/related/nonexistent")

        assert response.status_code == 404
