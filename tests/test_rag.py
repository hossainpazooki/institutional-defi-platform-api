"""Tests for RAG retrieval."""

from src.rag import BM25Index, Chunk, Retriever, chunk_text


class TestBM25Index:
    def test_add_documents(self, bm25_index: BM25Index):
        assert len(bm25_index) == 3

    def test_search_returns_results(self, bm25_index: BM25Index):
        results = bm25_index.search("authorization public offer", top_k=2)
        assert len(results) > 0

        doc, score = results[0]
        assert score > 0
        assert "authorization" in doc.text.lower() or "public offer" in doc.text.lower()

    def test_search_empty_query(self, bm25_index: BM25Index):
        results = bm25_index.search("", top_k=2)
        assert len(results) == 0

    def test_search_no_match(self, bm25_index: BM25Index):
        results = bm25_index.search("xyznonexistent", top_k=2)
        assert len(results) == 0

    def test_search_ranks_by_relevance(self, bm25_index: BM25Index):
        results = bm25_index.search("credit institutions e-money", top_k=3)
        assert len(results) > 0

        top_doc, _ = results[0]
        assert "credit" in top_doc.text.lower() or "e-money" in top_doc.text.lower()


class TestChunker:
    def test_chunk_text_basic(self):
        text = "This is a test. " * 100
        chunks = chunk_text(text, document_id="test_doc", chunk_size=500)

        assert len(chunks) > 1
        assert all(isinstance(c, Chunk) for c in chunks)
        assert all(c.document_id == "test_doc" for c in chunks)

    def test_chunk_text_preserves_content(self):
        text = "Hello world. This is important text."
        chunks = chunk_text(text, document_id="test", chunk_size=100)

        all_text = " ".join(c.text for c in chunks)
        assert "Hello world" in all_text
        assert "important text" in all_text

    def test_chunk_text_with_metadata(self):
        text = "Test content."
        chunks = chunk_text(
            text,
            document_id="test",
            metadata={"source": "MiCA", "article": "36"},
        )

        assert len(chunks) == 1
        assert chunks[0].metadata["source"] == "MiCA"
        assert chunks[0].metadata["article"] == "36"

    def test_chunk_indices(self):
        text = "First sentence. Second sentence. Third sentence."
        chunks = chunk_text(text, document_id="test", chunk_size=20, chunk_overlap=5)

        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i
            assert chunk.start_char >= 0
            assert chunk.end_char <= len(text)


class TestRetriever:
    def test_add_chunks(self, retriever: Retriever):
        assert len(retriever) > 0

    def test_search_bm25(self, retriever: Retriever):
        results = retriever.search("authorization public offer", top_k=2, method="bm25")

        assert len(results) > 0
        assert all(r.retrieval_method == "bm25" for r in results)

    def test_search_returns_retrieval_result(self, retriever: Retriever):
        results = retriever.search("legal person public offer", top_k=1)

        assert len(results) > 0
        result = results[0]
        assert result.chunk_id
        assert result.text
        assert result.score > 0
        assert result.document_id

    def test_search_with_metadata(self, retriever: Retriever):
        results = retriever.search("Article 36 authorization", top_k=1)

        assert len(results) > 0
        result = results[0]
        assert "article" in result.metadata or result.document_id


class TestRetrieverIntegration:
    def test_add_and_search_documents(self):
        retriever = Retriever(use_vectors=False)

        documents = [
            {
                "id": "doc1",
                "text": "MiCA requires authorization for public offers of crypto-assets in the European Union.",
            },
            {"id": "doc2", "text": "Stablecoins must maintain adequate reserves to ensure stability."},
            {"id": "doc3", "text": "Trading platforms need to register with competent authorities."},
            {"id": "doc4", "text": "Asset-referenced tokens are subject to specific requirements."},
        ]
        retriever.add_documents(documents)

        results = retriever.search("authorization crypto European", top_k=2, method="bm25")
        assert len(results) > 0

        assert "authorization" in results[0].text.lower() or "crypto" in results[0].text.lower()

    def test_search_empty_index(self):
        retriever = Retriever(use_vectors=False)
        results = retriever.search("anything", top_k=5)
        assert len(results) == 0
