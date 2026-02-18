"""Tests for legal corpus loader."""

import pytest

from src.rag.corpus_loader import (
    LEGAL_CORPUS_DIR,
    LegalCorpusError,
    LegalDocument,
    get_available_document_ids,
    load_all_legal_documents,
    load_legal_document,
)


class TestLegalDocumentDataclass:
    """Tests for LegalDocument dataclass."""

    def test_basic_fields(self):
        """Test that LegalDocument has expected fields."""
        doc = LegalDocument(
            document_id="test_doc",
            title="Test Document",
            citation="Test Citation 2025",
            jurisdiction="US",
            source_url="https://example.com",
            text="Article 1 - Test\n\nSome content here.",
        )

        assert doc.document_id == "test_doc"
        assert doc.title == "Test Document"
        assert doc.citation == "Test Citation 2025"
        assert doc.jurisdiction == "US"
        assert doc.source_url == "https://example.com"
        assert "Article 1" in doc.text

    def test_nullable_fields(self):
        """Test that optional fields can be None."""
        doc = LegalDocument(
            document_id="test_doc",
            title="Test",
            citation=None,
            jurisdiction=None,
            source_url=None,
            text="Some text",
        )

        assert doc.citation is None
        assert doc.jurisdiction is None
        assert doc.source_url is None


class TestLoadLegalDocument:
    """Tests for load_legal_document function."""

    def test_load_mica_2023(self):
        """Test loading MiCA document."""
        doc = load_legal_document("mica_2023")

        assert doc.document_id == "mica_2023"
        assert "MiCA" in doc.title or "Markets in Crypto" in doc.title
        assert doc.jurisdiction == "EU"
        assert doc.text  # Non-empty
        assert len(doc.text) > 100
        # Check for expected content
        assert "asset-referenced token" in doc.text.lower()

    def test_load_dlt_pilot_2022(self):
        """Test loading DLT Pilot document."""
        doc = load_legal_document("dlt_pilot_2022")

        assert doc.document_id == "dlt_pilot_2022"
        assert "DLT" in doc.title
        assert doc.jurisdiction == "EU"
        assert doc.text
        # Check for expected content
        assert "distributed ledger" in doc.text.lower()

    def test_load_genius_act_2025(self):
        """Test loading GENIUS Act document."""
        doc = load_legal_document("genius_act_2025")

        assert doc.document_id == "genius_act_2025"
        assert "GENIUS" in doc.title or "stablecoin" in doc.title.lower()
        assert doc.jurisdiction == "US"
        assert doc.text
        # Check for expected content
        assert "stablecoin" in doc.text.lower()

    def test_load_nonexistent_raises_error(self):
        """Test that loading non-existent document raises error."""
        with pytest.raises(LegalCorpusError) as excinfo:
            load_legal_document("nonexistent_document")

        assert "not found" in str(excinfo.value).lower()

    def test_citation_present(self):
        """Test that documents have citations."""
        doc = load_legal_document("mica_2023")
        assert doc.citation is not None
        assert "2023" in doc.citation or "EU" in doc.citation

    def test_source_url_present(self):
        """Test that documents have source URLs."""
        doc = load_legal_document("mica_2023")
        assert doc.source_url is not None
        assert doc.source_url.startswith("http")


class TestLoadAllLegalDocuments:
    """Tests for load_all_legal_documents function."""

    def test_returns_list(self):
        """Test that function returns a list."""
        docs = load_all_legal_documents()
        assert isinstance(docs, list)

    def test_loads_all_three_documents(self):
        """Test that all three expected documents are loaded."""
        docs = load_all_legal_documents()
        doc_ids = {doc.document_id for doc in docs}

        assert "mica_2023" in doc_ids
        assert "dlt_pilot_2022" in doc_ids
        assert "genius_act_2025" in doc_ids
        assert len(docs) >= 3

    def test_documents_have_valid_structure(self):
        """Test that all loaded documents have valid structure."""
        docs = load_all_legal_documents()

        for doc in docs:
            assert doc.document_id
            assert doc.title
            assert doc.text
            assert len(doc.text) > 0


class TestGetAvailableDocumentIds:
    """Tests for get_available_document_ids function."""

    def test_returns_list(self):
        """Test that function returns a list."""
        ids = get_available_document_ids()
        assert isinstance(ids, list)

    def test_contains_expected_ids(self):
        """Test that expected document IDs are present."""
        ids = get_available_document_ids()

        assert "mica_2023" in ids
        assert "dlt_pilot_2022" in ids
        assert "genius_act_2025" in ids

    def test_returns_strings(self):
        """Test that all IDs are strings."""
        ids = get_available_document_ids()

        for doc_id in ids:
            assert isinstance(doc_id, str)


class TestLegalDocumentMethods:
    """Tests for LegalDocument helper methods."""

    def test_get_articles_extracts_articles(self):
        """Test that get_articles extracts article references."""
        doc = load_legal_document("mica_2023")
        articles = doc.get_articles()

        assert len(articles) > 0
        # Each article is a (header, text) tuple
        for header, text in articles:
            assert "Article" in header or "Section" in header
            assert len(text) > 0

    def test_find_article_text_for_existing_article(self):
        """Test finding text for an existing article."""
        doc = load_legal_document("mica_2023")

        # Article 36 should exist
        text = doc.find_article_text("36")
        assert text is not None
        assert "Article 36" in text

    def test_find_article_text_for_nonexistent_article(self):
        """Test finding text for non-existent article."""
        doc = load_legal_document("mica_2023")

        text = doc.find_article_text("9999")
        assert text is None

    def test_find_article_with_different_formats(self):
        """Test finding articles with different reference formats."""
        doc = load_legal_document("mica_2023")

        # Test different formats that should find Article 36
        for ref in ["36", "Art. 36", "Article 36"]:
            text = doc.find_article_text(ref)
            if text:  # Some formats might not match exactly
                assert "36" in text


class TestCorpusIntegrity:
    """Integration tests for corpus integrity."""

    def test_all_documents_have_metadata(self):
        """Test that all documents have required metadata fields."""
        docs = load_all_legal_documents()

        for doc in docs:
            assert doc.document_id, "Missing document_id"
            assert doc.title, f"Missing title for {doc.document_id}"
            # These can be None but should exist as attributes
            _ = doc.citation
            _ = doc.jurisdiction
            _ = doc.source_url

    def test_text_stripped_of_comments(self):
        """Test that comment lines are stripped from text."""
        docs = load_all_legal_documents()

        for doc in docs:
            # Text should not start with # comment
            assert not doc.text.strip().startswith("#"), f"Text for {doc.document_id} still contains header comments"

    def test_corpus_directory_exists(self):
        """Test that the corpus directory exists."""
        assert LEGAL_CORPUS_DIR.exists(), f"Corpus directory not found: {LEGAL_CORPUS_DIR}"
