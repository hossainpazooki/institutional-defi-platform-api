"""Tests for embedding rule CRUD."""

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from src.database import get_session
from src.main import app


@pytest.fixture(name="engine")
def engine_fixture():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture(name="client")
def client_fixture(engine):
    def get_session_override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_session_override
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def sample_rule_data():
    return {
        "rule_id": "income_eligibility_001",
        "name": "Income Eligibility Check",
        "description": "Verify applicant meets minimum income requirements",
        "conditions": [
            {"field": "applicant.annual_income", "operator": "gte", "value": "50000"},
            {"field": "applicant.age", "operator": "gte", "value": "18"},
        ],
        "decision": {"outcome": "eligible", "confidence": 1.0, "explanation": "Meets criteria"},
        "legal_sources": [{"citation": "Consumer Credit Act Section 4.2", "document_id": "cca_2023"}],
    }


class TestEmbeddingRules:
    def test_create_rule(self, client: TestClient, sample_rule_data: dict):
        response = client.post("/embedding/rules", json=sample_rule_data)
        assert response.status_code == 201
        data = response.json()
        assert data["rule_id"] == sample_rule_data["rule_id"]
        assert len(data["conditions"]) == 2
        assert data["decision"]["outcome"] == "eligible"

    def test_get_rule(self, client: TestClient, sample_rule_data: dict):
        client.post("/embedding/rules", json=sample_rule_data)
        response = client.get(f"/embedding/rules/{sample_rule_data['rule_id']}")
        assert response.status_code == 200
        assert response.json()["rule_id"] == sample_rule_data["rule_id"]

    def test_get_rule_not_found(self, client: TestClient):
        response = client.get("/embedding/rules/nonexistent")
        assert response.status_code == 404

    def test_list_rules(self, client: TestClient, sample_rule_data: dict):
        client.post("/embedding/rules", json=sample_rule_data)
        response = client.get("/embedding/rules")
        assert response.status_code == 200
        assert len(response.json()) == 1

    def test_update_rule(self, client: TestClient, sample_rule_data: dict):
        client.post("/embedding/rules", json=sample_rule_data)
        response = client.put(f"/embedding/rules/{sample_rule_data['rule_id']}", json={"name": "Updated"})
        assert response.status_code == 200
        assert response.json()["name"] == "Updated"

    def test_delete_rule(self, client: TestClient, sample_rule_data: dict):
        client.post("/embedding/rules", json=sample_rule_data)
        response = client.delete(f"/embedding/rules/{sample_rule_data['rule_id']}")
        assert response.status_code == 200
        assert response.json()["is_active"] is False
