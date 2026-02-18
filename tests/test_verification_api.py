"""Tests for KE API endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.main import app


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


class TestRootEndpoint:
    def test_root_returns_app_info(self, client):
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "endpoints" in data
        assert any("/ke/" in ep for ep in data["endpoints"])


class TestVerifyEndpoint:
    def test_verify_known_rule(self, client):
        response = client.post(
            "/ke/verify",
            json={
                "rule_id": "mica_art36_public_offer_authorization",
                "tiers": [0, 1],
            },
        )
        if response.status_code == 200:
            data = response.json()
            assert "rule_id" in data
            assert "status" in data
            assert "confidence" in data
            assert "evidence" in data
        else:
            assert response.status_code == 404

    def test_verify_unknown_rule(self, client):
        response = client.post(
            "/ke/verify",
            json={
                "rule_id": "nonexistent_rule_xyz",
                "tiers": [0],
            },
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_verify_with_source_text(self, client):
        response = client.post(
            "/ke/verify",
            json={
                "rule_id": "mica_art36_public_offer_authorization",
                "source_text": "An issuer shall obtain authorization before making a public offer.",
                "tiers": [0, 1],
            },
        )
        if response.status_code == 200:
            data = response.json()
            tier1_evidence = [e for e in data["evidence"] if e["tier"] == 1]
            assert len(tier1_evidence) > 0


class TestVerifyAllEndpoint:
    def test_verify_all_rules(self, client):
        response = client.post("/ke/verify-all?tiers=0&tiers=1")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "results" in data
        assert isinstance(data["results"], list)

    def test_verify_all_with_tier_filter(self, client):
        response = client.post("/ke/verify-all?tiers=0")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data


class TestAnalyticsSummaryEndpoint:
    def test_analytics_summary(self, client):
        response = client.get("/ke/analytics/summary")
        assert response.status_code == 200
        data = response.json()
        assert "total_rules" in data
        assert "verification_rate" in data
        assert "average_score" in data


class TestAnalyticsPatternsEndpoint:
    def test_analytics_patterns(self, client):
        response = client.get("/ke/analytics/patterns")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestReviewQueueEndpoint:
    def test_review_queue(self, client):
        response = client.get("/ke/analytics/review-queue")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_review_queue_with_limit(self, client):
        response = client.get("/ke/analytics/review-queue?max_items=5")
        assert response.status_code == 200
        data = response.json()
        assert len(data) <= 5


class TestHumanReviewEndpoint:
    def test_submit_review_valid(self, client):
        response = client.post(
            "/ke/rules/mica_art36_public_offer_authorization/review",
            json={
                "label": "consistent",
                "notes": "Verified against source text manually",
                "reviewer_id": "test_reviewer",
            },
        )
        if response.status_code == 200:
            data = response.json()
            assert data["rule_id"] == "mica_art36_public_offer_authorization"
            assert data["status"] == "verified"
            assert data["review_tier"] == 4
            assert data["reviewer_id"] == "test_reviewer"
        else:
            assert response.status_code == 404

    def test_submit_review_invalid_label(self, client):
        response = client.post(
            "/ke/rules/mica_art36_public_offer_authorization/review",
            json={
                "label": "invalid_label",
                "notes": "Test notes",
                "reviewer_id": "test_reviewer",
            },
        )
        assert response.status_code in (400, 404)

    def test_submit_review_unknown_rule(self, client):
        response = client.post(
            "/ke/rules/nonexistent_rule_xyz/review",
            json={
                "label": "consistent",
                "notes": "Test notes",
                "reviewer_id": "test_reviewer",
            },
        )
        assert response.status_code == 404

    def test_get_reviews_for_rule(self, client):
        response = client.get("/ke/rules/mica_art36_public_offer_authorization/reviews")
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, list)
            for review in data:
                assert review["tier"] == 4
                assert review["category"] == "human_review"
        else:
            assert response.status_code == 404


class TestDriftEndpoints:
    def test_set_drift_baseline(self, client):
        response = client.post("/ke/drift/baseline")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert data["message"] == "Baseline set"

    def test_detect_drift(self, client):
        client.post("/ke/drift/baseline")
        response = client.get("/ke/drift/detect")
        assert response.status_code == 200
        data = response.json()
        assert "drift_detected" in data
        assert "drift_severity" in data
        assert "summary" in data

    def test_drift_history(self, client):
        response = client.get("/ke/drift/history")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_drift_history_with_window(self, client):
        response = client.get("/ke/drift/history?window=5")
        assert response.status_code == 200
        data = response.json()
        assert len(data) <= 5


class TestContextEndpoints:
    def test_get_rule_context(self, client):
        response = client.get("/ke/context/mica_art36_public_offer_authorization")
        if response.status_code == 200:
            data = response.json()
            assert "rule_id" in data
            assert "source_passages" in data
            assert "related_rules" in data
        else:
            assert response.status_code == 404

    def test_get_rule_context_unknown(self, client):
        response = client.get("/ke/context/nonexistent_rule_xyz")
        assert response.status_code == 404

    def test_get_related_rules(self, client):
        response = client.get("/ke/related/mica_art36_public_offer_authorization")
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, list)
            for rule in data:
                assert "rule_id" in rule
        else:
            assert response.status_code == 404

    def test_get_related_rules_with_limit(self, client):
        response = client.get("/ke/related/mica_art36_public_offer_authorization?top_k=3")
        if response.status_code == 200:
            data = response.json()
            assert len(data) <= 3


class TestVerificationWorkflow:
    def test_verify_then_review_workflow(self, client):
        rule_id = "mica_art36_public_offer_authorization"

        verify_response = client.post(
            "/ke/verify",
            json={"rule_id": rule_id, "tiers": [0, 1]},
        )
        if verify_response.status_code != 200:
            pytest.skip("Rule not available in test environment")

        review_response = client.post(
            f"/ke/rules/{rule_id}/review",
            json={
                "label": "consistent",
                "notes": "Verified against source",
                "reviewer_id": "integration_test",
            },
        )
        assert review_response.status_code == 200
        review_data = review_response.json()
        assert review_data["status"] == "verified"
        assert review_data["review_tier"] == 4

        reviews_response = client.get(f"/ke/rules/{rule_id}/reviews")
        assert reviews_response.status_code == 200
        reviews = reviews_response.json()
        assert len(reviews) > 0
        assert reviews[-1]["category"] == "human_review"
