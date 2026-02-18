"""Pytest fixtures for test suite."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.ontology import Scenario
from src.rag import BM25Index, Retriever
from src.rules import DecisionEngine, RuleLoader

# =============================================================================
# Core Fixtures
# =============================================================================


@pytest.fixture
def client():
    """Test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def rules_dir() -> Path:
    """Path to the rules directory."""
    return Path(__file__).parent.parent / "src" / "rules" / "data"


@pytest.fixture
def rule_loader(rules_dir: Path) -> RuleLoader:
    """Rule loader with rules loaded from the rules directory."""
    loader = RuleLoader(rules_dir)
    loader.load_directory()
    return loader


@pytest.fixture
def decision_engine(rule_loader: RuleLoader) -> DecisionEngine:
    """Decision engine with rules loaded."""
    return DecisionEngine(rule_loader)


@pytest.fixture
def sample_scenario() -> Scenario:
    """Sample scenario for testing."""
    return Scenario(
        instrument_type="art",
        activity="public_offer",
        jurisdiction="EU",
        authorized=False,
        is_credit_institution=False,
    )


@pytest.fixture
def bm25_index() -> BM25Index:
    """BM25 index with sample documents."""
    index = BM25Index()
    index.add_documents(
        [
            {
                "id": "doc1",
                "text": "Article 36 requires authorization for public offers of asset-referenced tokens.",
                "metadata": {"source": "MiCA"},
            },
            {
                "id": "doc2",
                "text": "E-money tokens can only be issued by authorized credit institutions.",
                "metadata": {"source": "MiCA"},
            },
            {
                "id": "doc3",
                "text": "Reserve assets must be held by authorized custodians.",
                "metadata": {"source": "MiCA"},
            },
        ]
    )
    return index


@pytest.fixture
def retriever() -> Retriever:
    """Retriever with sample documents (BM25 only)."""
    retriever = Retriever(use_vectors=False)
    retriever.add_documents(
        [
            {
                "id": "mica_art36",
                "text": """Article 36 — Authorisation
            No person shall make a public offer in the Union of an asset-referenced token,
            or seek admission of such a crypto-asset to trading on a trading platform,
            unless that person is a legal person that has been authorised in accordance
            with Article 21 or is a credit institution.""",
                "metadata": {"article": "36"},
            },
            {
                "id": "mica_art38",
                "text": """Article 38 — Reserve of assets
            Issuers of asset-referenced tokens shall constitute and maintain a reserve
            of assets. The reserve shall be composed and managed in such a way that
            the risks associated with the assets referenced are covered.""",
                "metadata": {"article": "38"},
            },
        ]
    )
    return retriever
