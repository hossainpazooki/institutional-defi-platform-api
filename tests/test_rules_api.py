"""Tests for FastAPI endpoints."""

import pytest
from fastapi.testclient import TestClient

from src.main import app


@pytest.fixture
def client():
    """Test client for the FastAPI app."""
    return TestClient(app)


class TestRootEndpoints:
    def test_root(self, client):
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "endpoints" in data

    def test_health(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


class TestDecideEndpoint:
    def test_decide_not_authorized(self, client):
        response = client.post(
            "/decide",
            json={
                "instrument_type": "art",
                "activity": "public_offer",
                "jurisdiction": "EU",
                "authorized": False,
                "is_credit_institution": False,
            },
        )
        assert response.status_code == 200
        data = response.json()

        assert "results" in data
        assert len(data["results"]) >= 1

        auth_result = next(
            (r for r in data["results"] if "art36" in r["rule_id"]),
            None,
        )
        assert auth_result is not None
        assert auth_result["decision"] == "not_authorized"
        assert len(auth_result["obligations"]) >= 1

    def test_decide_authorized(self, client):
        response = client.post(
            "/decide",
            json={
                "instrument_type": "art",
                "activity": "public_offer",
                "jurisdiction": "EU",
                "authorized": True,
                "is_credit_institution": False,
            },
        )
        assert response.status_code == 200
        data = response.json()

        auth_result = next(
            (r for r in data["results"] if "art36" in r["rule_id"]),
            None,
        )
        assert auth_result is not None
        assert auth_result["decision"] == "authorized"

    def test_decide_exempt(self, client):
        response = client.post(
            "/decide",
            json={
                "instrument_type": "art",
                "activity": "public_offer",
                "jurisdiction": "EU",
                "authorized": False,
                "is_credit_institution": True,
            },
        )
        assert response.status_code == 200
        data = response.json()

        auth_result = next(
            (r for r in data["results"] if "art36" in r["rule_id"]),
            None,
        )
        assert auth_result is not None
        assert auth_result["decision"] == "exempt"

    def test_decide_specific_rule(self, client):
        response = client.post(
            "/decide",
            json={
                "instrument_type": "art",
                "activity": "public_offer",
                "jurisdiction": "EU",
                "authorized": False,
                "rule_id": "mica_art36_public_offer_authorization",
            },
        )
        assert response.status_code == 200
        data = response.json()

        assert len(data["results"]) == 1
        assert data["results"][0]["rule_id"] == "mica_art36_public_offer_authorization"

    def test_decide_includes_trace(self, client):
        response = client.post(
            "/decide",
            json={
                "instrument_type": "art",
                "activity": "public_offer",
                "jurisdiction": "EU",
                "authorized": False,
            },
        )
        assert response.status_code == 200
        data = response.json()

        result = data["results"][0]
        assert "trace" in result
        assert len(result["trace"]) > 0
        assert "node" in result["trace"][0]
        assert "condition" in result["trace"][0]
        assert "result" in result["trace"][0]

    def test_decide_includes_summary(self, client):
        response = client.post(
            "/decide",
            json={
                "instrument_type": "art",
                "activity": "public_offer",
                "jurisdiction": "EU",
                "authorized": False,
            },
        )
        assert response.status_code == 200
        data = response.json()

        assert "summary" in data
        assert data["summary"] is not None


class TestRulesEndpoint:
    def test_list_rules(self, client):
        response = client.get("/rules")
        assert response.status_code == 200
        data = response.json()

        assert "rules" in data
        assert "total" in data
        assert data["total"] >= 2

    def test_list_rules_with_tag(self, client):
        response = client.get("/rules?tag=authorization")
        assert response.status_code == 200
        data = response.json()

        assert all("authorization" in r["tags"] for r in data["rules"])

    def test_get_rule_detail(self, client):
        response = client.get("/rules/mica_art36_public_offer_authorization")
        assert response.status_code == 200
        data = response.json()

        assert data["rule_id"] == "mica_art36_public_offer_authorization"
        assert "applies_if" in data
        assert "decision_tree" in data
        assert "source" in data

    def test_get_rule_not_found(self, client):
        response = client.get("/rules/nonexistent_rule")
        assert response.status_code == 404

    def test_list_tags(self, client):
        response = client.get("/rules/tags/all")
        assert response.status_code == 200
        data = response.json()

        assert "tags" in data
        assert "mica" in data["tags"]


class TestQAEndpoint:
    def test_qa_status(self, client):
        response = client.get("/qa/status")
        assert response.status_code == 200
        data = response.json()

        assert "documents_indexed" in data
        assert "vector_search_available" in data

    def test_qa_ask_no_documents(self, client):
        response = client.post(
            "/qa/ask",
            json={"question": "What is MiCA?"},
        )
        assert response.status_code == 200
        data = response.json()

        assert "answer" in data
        assert "sources" in data

    def test_qa_index_document(self, client):
        response = client.post(
            "/qa/index",
            json={
                "id": "test_doc",
                "text": "This is a test document about regulatory requirements.",
            },
        )
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "indexed"
        assert data["document_id"] == "test_doc"

    def test_qa_index_invalid(self, client):
        response = client.post(
            "/qa/index",
            json={"text": "Missing ID"},
        )
        assert response.status_code == 400


class TestReloadEndpoint:
    def test_reload_rules(self, client):
        response = client.post("/decide/reload")
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "reloaded"
        assert data["rules_loaded"] >= 2
