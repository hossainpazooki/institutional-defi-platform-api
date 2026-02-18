"""Tests for chart visualization API endpoints."""

import pytest
from fastapi.testclient import TestClient

from src.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


class TestSupertreeStatus:
    def test_status_returns_availability(self, client):
        response = client.get("/ke/charts/supertree-status")
        assert response.status_code == 200
        data = response.json()
        assert "available" in data
        assert isinstance(data["available"], bool)
        assert "message" in data


class TestRulebookOutlineChart:
    def test_get_rulebook_outline_data(self, client):
        response = client.get("/ke/charts/rulebook-outline")
        assert response.status_code == 200
        data = response.json()
        assert data["chart_type"] == "rulebook_outline"
        assert "data" in data
        assert data["data"]["title"] == "Legal Corpus & Rulebook"
        assert "supertree_available" in data

    def test_get_rulebook_outline_html(self, client):
        response = client.get("/ke/charts/rulebook-outline/html")
        assert response.status_code == 200
        data = response.json()
        assert data["chart_type"] == "rulebook_outline"
        assert "html" in data
        assert "<div" in data["html"]


class TestOntologyChart:
    def test_get_ontology_data(self, client):
        response = client.get("/ke/charts/ontology")
        assert response.status_code == 200
        data = response.json()
        assert data["chart_type"] == "ontology"
        assert "data" in data
        assert data["data"]["title"] == "Regulatory Ontology"

    def test_get_ontology_html(self, client):
        response = client.get("/ke/charts/ontology/html")
        assert response.status_code == 200
        data = response.json()
        assert data["chart_type"] == "ontology"
        assert "html" in data

    def test_ontology_contains_type_categories(self, client):
        response = client.get("/ke/charts/ontology")
        data = response.json()
        children = data["data"]["children"]
        titles = [c["title"] for c in children]
        assert "Actor Types" in titles
        assert "Instrument Types" in titles
        assert "Activity Types" in titles


class TestCorpusLinksChart:
    def test_get_corpus_links_data(self, client):
        response = client.get("/ke/charts/corpus-links")
        assert response.status_code == 200
        data = response.json()
        assert data["chart_type"] == "corpus_links"
        assert "data" in data
        assert data["data"]["title"] == "Corpus-Rule Links"

    def test_get_corpus_links_html(self, client):
        response = client.get("/ke/charts/corpus-links/html")
        assert response.status_code == 200
        data = response.json()
        assert data["chart_type"] == "corpus_links"
        assert "html" in data


class TestDecisionTreeChart:
    def test_get_decision_tree_for_existing_rule(self, client):
        response = client.get("/ke/charts/decision-tree/mica_art36_public_offer_authorization")
        assert response.status_code == 200
        data = response.json()
        assert data["chart_type"] == "decision_tree"
        assert "data" in data
        assert "title" in data["data"] or "type" in data["data"]

    def test_get_decision_tree_for_nonexistent_rule(self, client):
        response = client.get("/ke/charts/decision-tree/nonexistent_rule")
        assert response.status_code == 404


class TestDecisionTraceChart:
    def test_get_decision_trace_data(self, client):
        scenario = {
            "instrument_type": "art",
            "activity": "public_offer",
            "jurisdiction": "EU",
            "is_credit_institution": False,
            "authorized": False,
        }
        response = client.post(
            "/ke/charts/decision-trace/mica_art36_public_offer_authorization", json={"scenario": scenario}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["chart_type"] == "decision_trace"
        assert "data" in data
        assert data["data"]["title"] == "Decision Trace"
        assert data["data"]["rule_id"] == "mica_art36_public_offer_authorization"

    def test_get_decision_trace_html(self, client):
        scenario = {
            "instrument_type": "art",
            "activity": "public_offer",
            "jurisdiction": "EU",
            "authorized": True,
        }
        response = client.post(
            "/ke/charts/decision-trace/mica_art36_public_offer_authorization/html", json={"scenario": scenario}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["chart_type"] == "decision_trace"
        assert "html" in data

    def test_decision_trace_for_nonexistent_rule(self, client):
        response = client.post(
            "/ke/charts/decision-trace/nonexistent_rule", json={"scenario": {"instrument_type": "art"}}
        )
        assert response.status_code == 404

    def test_decision_trace_contains_steps(self, client):
        scenario = {
            "instrument_type": "art",
            "activity": "public_offer",
            "jurisdiction": "EU",
            "is_credit_institution": True,
        }
        response = client.post(
            "/ke/charts/decision-trace/mica_art36_public_offer_authorization", json={"scenario": scenario}
        )
        data = response.json()
        assert "data" in data
        if data.get("data"):
            assert "steps" in data["data"]
            assert data["data"]["steps"] > 0
            assert "children" in data["data"]
            assert len(data["data"]["children"]) > 0
