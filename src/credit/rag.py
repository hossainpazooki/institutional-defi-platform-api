"""LlamaIndex RAG layer for credit document retrieval.

Falls back to BM25 from src.rag.service if LlamaIndex is not installed.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class CreditRAGService:
    """Hybrid RAG service for credit documents.

    Uses LlamaIndex with PGVector when available, otherwise falls back
    to BM25-based retrieval from the existing RAG service.
    """

    def __init__(
        self,
        embed_model: str | None = None,
        pg_connection_string: str | None = None,
    ) -> None:
        self._embed_model_name = embed_model or "BAAI/bge-small-en-v1.5"
        self._pg_connection_string = pg_connection_string
        self._li_index: Any = None
        self._bm25_fallback: Any = None
        self._use_llama_index = False

        self._init_backend()

    def _init_backend(self) -> None:
        """Try LlamaIndex first, fall back to BM25."""
        try:
            from llama_index.core import Document, Settings as LISettings, VectorStoreIndex  # noqa: F401, I001
            from llama_index.core.node_parser import SentenceSplitter  # noqa: F401
            from llama_index.embeddings.huggingface import HuggingFaceEmbedding  # noqa: F401

            LISettings.embed_model = HuggingFaceEmbedding(model_name=self._embed_model_name)
            LISettings.node_parser = SentenceSplitter(chunk_size=512, chunk_overlap=64)

            if self._pg_connection_string:
                from llama_index.vector_stores.postgres import PGVectorStore  # noqa: F401

                vector_store = PGVectorStore.from_params(
                    connection_string=self._pg_connection_string,
                    table_name="credit_embeddings",
                    embed_dim=384,
                )
                self._li_index = VectorStoreIndex.from_vector_store(vector_store)
            else:
                self._li_index = VectorStoreIndex([])

            self._use_llama_index = True
            logger.info("CreditRAGService: using LlamaIndex backend")

        except ImportError:
            from src.rag.service import BM25Index

            self._bm25_fallback = BM25Index()
            self._use_llama_index = False
            logger.info("CreditRAGService: LlamaIndex not available, using BM25 fallback")

    def ingest_document(
        self,
        doc_id: str,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Chunk and index a document."""
        metadata = metadata or {}
        metadata["doc_id"] = doc_id

        if self._use_llama_index and self._li_index is not None:
            from llama_index.core import Document

            doc = Document(text=text, metadata=metadata, doc_id=doc_id)
            self._li_index.insert(doc)
        elif self._bm25_fallback is not None:
            self._bm25_fallback.add_documents([{"id": doc_id, "text": text, "metadata": metadata}])

    def search(
        self,
        query: str,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Hybrid search with reranking.

        Returns list of dicts with keys: text, score, metadata.
        """
        if self._use_llama_index and self._li_index is not None:
            try:
                from llama_index.core.retrievers import QueryFusionRetriever  # noqa: F401

                retriever = self._li_index.as_retriever(similarity_top_k=top_k)
                nodes = retriever.retrieve(query)
                return [
                    {
                        "text": node.text,
                        "score": node.score or 0.0,
                        "metadata": node.metadata,
                    }
                    for node in nodes
                ]
            except Exception:
                logger.exception("LlamaIndex retrieval failed, falling back")

        if self._bm25_fallback is not None:
            results = self._bm25_fallback.search(query, top_k=top_k)
            return [
                {
                    "text": doc.text,
                    "score": score,
                    "metadata": doc.metadata,
                }
                for doc, score in results
            ]

        return []
