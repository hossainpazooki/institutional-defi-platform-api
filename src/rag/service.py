"""RAG service layer - chunking, indexing, retrieval, and generation."""

from __future__ import annotations

import re
from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from src.config import get_settings, ml_available

# =============================================================================
# Chunking
# =============================================================================


@dataclass
class Chunk:
    """A chunk of text from a document."""

    id: str
    text: str
    document_id: str
    chunk_index: int
    start_char: int
    end_char: int
    metadata: dict


def chunk_text(
    text: str,
    document_id: str,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
    metadata: dict | None = None,
) -> list[Chunk]:
    """Split text into overlapping chunks.

    Args:
        text: The text to chunk.
        document_id: Identifier for the source document.
        chunk_size: Target size of each chunk in characters.
        chunk_overlap: Overlap between chunks in characters.
        metadata: Additional metadata to attach to each chunk.

    Returns:
        List of Chunk objects.
    """
    if not text:
        return []

    metadata = metadata or {}
    chunks = []
    start = 0
    chunk_index = 0

    while start < len(text):
        # Find end position
        end = start + chunk_size

        # Try to break at sentence boundary
        if end < len(text):
            # Look for sentence ending punctuation
            for punct in [". ", ".\n", "? ", "?\n", "! ", "!\n"]:
                last_punct = text.rfind(punct, start, end)
                if last_punct > start + chunk_size // 2:
                    end = last_punct + 1
                    break

        # Ensure we don't go past the text
        end = min(end, len(text))

        chunk_text_str = text[start:end].strip()
        if chunk_text_str:
            chunk_id = f"{document_id}_chunk_{chunk_index}"
            chunks.append(
                Chunk(
                    id=chunk_id,
                    text=chunk_text_str,
                    document_id=document_id,
                    chunk_index=chunk_index,
                    start_char=start,
                    end_char=end,
                    metadata=metadata.copy(),
                )
            )
            chunk_index += 1

        # Move start position with overlap
        start = end - chunk_overlap
        if start <= chunks[-1].start_char if chunks else 0:
            start = end

    return chunks


def chunk_by_section(
    text: str,
    document_id: str,
    section_pattern: str = r"\n(?=Article \d+)",
    metadata: dict | None = None,
) -> list[Chunk]:
    """Split text by section headers (e.g., articles).

    Args:
        text: The text to chunk.
        document_id: Identifier for the source document.
        section_pattern: Regex pattern for section boundaries.
        metadata: Additional metadata to attach to each chunk.

    Returns:
        List of Chunk objects.
    """
    if not text:
        return []

    metadata = metadata or {}
    chunks = []

    # Split by pattern
    parts = re.split(section_pattern, text)
    current_pos = 0

    for i, part in enumerate(parts):
        part = part.strip()
        if not part:
            continue

        chunk_id = f"{document_id}_section_{i}"
        start_char = text.find(part, current_pos)
        end_char = start_char + len(part)

        # Try to extract section title
        section_metadata = metadata.copy()
        first_line = part.split("\n")[0]
        if first_line:
            section_metadata["section_title"] = first_line[:100]

        chunks.append(
            Chunk(
                id=chunk_id,
                text=part,
                document_id=document_id,
                chunk_index=i,
                start_char=start_char,
                end_char=end_char,
                metadata=section_metadata,
            )
        )
        current_pos = end_char

    return chunks


# =============================================================================
# BM25 Index
# =============================================================================


@dataclass
class BM25Document:
    """A document in the BM25 index."""

    id: str
    text: str
    tokens: list[str]
    metadata: dict


class BM25Index:
    """BM25 index for text retrieval."""

    def __init__(self) -> None:
        self._documents: list[BM25Document] = []
        self._index: BM25Okapi | None = None

    def add_documents(self, documents: list[dict]) -> None:
        """Add documents to the index.

        Args:
            documents: List of dicts with 'id', 'text', and optional 'metadata'.
        """
        for doc in documents:
            tokens = self._tokenize(doc["text"])
            self._documents.append(
                BM25Document(
                    id=doc["id"],
                    text=doc["text"],
                    tokens=tokens,
                    metadata=doc.get("metadata", {}),
                )
            )

        # Rebuild index
        if self._documents:
            corpus = [doc.tokens for doc in self._documents]
            self._index = BM25Okapi(corpus)

    def search(self, query: str, top_k: int = 5) -> list[tuple[BM25Document, float]]:
        """Search the index.

        Args:
            query: Search query.
            top_k: Number of results to return.

        Returns:
            List of (document, score) tuples.
        """
        if not self._index or not self._documents:
            return []

        query_tokens = self._tokenize(query)
        scores = self._index.get_scores(query_tokens)

        # Get top-k results
        indexed_scores = list(enumerate(scores))
        indexed_scores.sort(key=lambda x: x[1], reverse=True)
        top_results = indexed_scores[:top_k]

        results = []
        for idx, score in top_results:
            if score > 0:
                results.append((self._documents[idx], score))

        return results

    def _tokenize(self, text: str) -> list[str]:
        """Tokenize text for BM25."""
        text = text.lower()
        text = re.sub(r"[^a-z0-9\s]", " ", text)
        tokens = [t for t in text.split() if len(t) > 1]
        return tokens

    def __len__(self) -> int:
        return len(self._documents)


# =============================================================================
# Retrieval
# =============================================================================


@dataclass
class RetrievalResult:
    """A retrieval result with source information."""

    chunk_id: str
    text: str
    score: float
    document_id: str
    metadata: dict
    retrieval_method: str  # "bm25", "vector", or "hybrid"


class Retriever:
    """Hybrid retriever combining BM25 and optional vector search."""

    def __init__(self, use_vectors: bool | None = None) -> None:
        """Initialize the retriever.

        Args:
            use_vectors: Whether to use vector search. If None, auto-detect.
        """
        self._bm25 = BM25Index()
        self._vector_store = None
        self._embedder = None
        self._collection = None

        # Auto-detect ML availability
        if use_vectors is None:
            settings = get_settings()
            use_vectors = settings.enable_vector_search and ml_available()

        if use_vectors:
            self._init_vector_store()

    def _init_vector_store(self) -> None:
        """Initialize vector store if ML dependencies available."""
        try:
            import chromadb
            from sentence_transformers import SentenceTransformer

            self._embedder = SentenceTransformer("all-MiniLM-L6-v2")
            self._vector_store = chromadb.Client()
            self._collection = self._vector_store.create_collection(
                name="documents",
                metadata={"hnsw:space": "cosine"},
            )
        except ImportError:
            pass

    def add_chunks(self, chunks: list[Chunk]) -> None:
        """Add chunks to the index.

        Args:
            chunks: List of Chunk objects.
        """
        # Add to BM25
        bm25_docs = [
            {
                "id": chunk.id,
                "text": chunk.text,
                "metadata": {
                    "document_id": chunk.document_id,
                    "chunk_index": chunk.chunk_index,
                    **chunk.metadata,
                },
            }
            for chunk in chunks
        ]
        self._bm25.add_documents(bm25_docs)

        # Add to vector store if available
        if self._collection is not None and self._embedder is not None:
            texts = [chunk.text for chunk in chunks]
            embeddings = self._embedder.encode(texts).tolist()

            self._collection.add(
                ids=[chunk.id for chunk in chunks],
                embeddings=embeddings,
                documents=texts,
                metadatas=[
                    {
                        "document_id": chunk.document_id,
                        "chunk_index": str(chunk.chunk_index),
                    }
                    for chunk in chunks
                ],
            )

    def add_documents(self, documents: list[dict]) -> None:
        """Add raw documents (will be chunked internally).

        Args:
            documents: List of dicts with 'id', 'text', and optional 'metadata'.
        """
        all_chunks = []
        for doc in documents:
            chunks = chunk_text(
                text=doc["text"],
                document_id=doc["id"],
                metadata=doc.get("metadata", {}),
            )
            all_chunks.extend(chunks)

        self.add_chunks(all_chunks)

    def search(
        self,
        query: str,
        top_k: int = 5,
        method: str = "hybrid",
    ) -> list[RetrievalResult]:
        """Search for relevant chunks.

        Args:
            query: Search query.
            top_k: Number of results to return.
            method: "bm25", "vector", or "hybrid".

        Returns:
            List of RetrievalResult objects.
        """
        results: list[RetrievalResult] = []

        if method in ("bm25", "hybrid"):
            bm25_results = self._search_bm25(query, top_k)
            results.extend(bm25_results)

        if method in ("vector", "hybrid") and self._collection is not None:
            vector_results = self._search_vector(query, top_k)
            results.extend(vector_results)

        # Deduplicate and sort by score
        seen_ids: set[str] = set()
        unique_results: list[RetrievalResult] = []
        for result in sorted(results, key=lambda x: x.score, reverse=True):
            if result.chunk_id not in seen_ids:
                seen_ids.add(result.chunk_id)
                unique_results.append(result)

        return unique_results[:top_k]

    def _search_bm25(self, query: str, top_k: int) -> list[RetrievalResult]:
        """Search using BM25."""
        results = []
        for doc, score in self._bm25.search(query, top_k):
            results.append(
                RetrievalResult(
                    chunk_id=doc.id,
                    text=doc.text,
                    score=score,
                    document_id=doc.metadata.get("document_id", ""),
                    metadata=doc.metadata,
                    retrieval_method="bm25",
                )
            )
        return results

    def _search_vector(self, query: str, top_k: int) -> list[RetrievalResult]:
        """Search using vector similarity."""
        if self._collection is None or self._embedder is None:
            return []

        query_embedding = self._embedder.encode([query]).tolist()

        results = self._collection.query(
            query_embeddings=query_embedding,
            n_results=top_k,
        )

        retrieval_results = []
        if results["ids"] and results["ids"][0]:
            for i, chunk_id in enumerate(results["ids"][0]):
                # ChromaDB returns distances, convert to similarity score
                distance = results["distances"][0][i] if results["distances"] else 0
                score = 1.0 / (1.0 + distance)

                retrieval_results.append(
                    RetrievalResult(
                        chunk_id=chunk_id,
                        text=(results["documents"][0][i] if results["documents"] else ""),
                        score=score,
                        document_id=(results["metadatas"][0][i].get("document_id", "") if results["metadatas"] else ""),
                        metadata=(results["metadatas"][0][i] if results["metadatas"] else {}),
                        retrieval_method="vector",
                    )
                )

        return retrieval_results

    def __len__(self) -> int:
        return len(self._bm25)


# =============================================================================
# Answer Generation
# =============================================================================


class AnswerGenerator:
    """Generates answers from retrieved context."""

    def __init__(self) -> None:
        self._client = None
        self._init_llm()

    def _init_llm(self) -> None:
        """Initialize LLM client if API key available."""
        settings = get_settings()
        if settings.openai_api_key:
            try:
                from openai import OpenAI

                self._client = OpenAI(api_key=settings.openai_api_key)
            except ImportError:
                pass

    def generate(
        self,
        question: str,
        context: list[RetrievalResult],
        max_tokens: int = 500,
    ) -> dict:
        """Generate an answer from the question and context.

        Args:
            question: User's question.
            context: Retrieved context chunks.
            max_tokens: Maximum tokens in response.

        Returns:
            Dict with 'answer', 'sources', and 'method'.
        """
        if not context:
            return {
                "answer": "No relevant information found.",
                "sources": [],
                "method": "no_context",
            }

        # Build context string
        context_text = self._format_context(context)
        sources = self._extract_sources(context)

        # If no LLM, return raw excerpts
        if self._client is None:
            return {
                "answer": self._fallback_answer(question, context),
                "sources": sources,
                "method": "excerpt",
            }

        # Generate with LLM
        answer = self._generate_with_llm(question, context_text, max_tokens)
        return {
            "answer": answer,
            "sources": sources,
            "method": "llm",
        }

    def _format_context(self, context: list[RetrievalResult]) -> str:
        """Format context for LLM prompt."""
        parts = []
        for i, result in enumerate(context, 1):
            source = result.metadata.get("section_title", result.document_id)
            parts.append(f"[{i}] {source}:\n{result.text}\n")
        return "\n".join(parts)

    def _extract_sources(self, context: list[RetrievalResult]) -> list[dict]:
        """Extract source citations from context."""
        sources = []
        for result in context:
            sources.append(
                {
                    "document_id": result.document_id,
                    "chunk_id": result.chunk_id,
                    "section": result.metadata.get("section_title"),
                    "score": round(result.score, 3),
                }
            )
        return sources

    def _fallback_answer(self, question: str, context: list[RetrievalResult]) -> str:
        """Generate answer from excerpts when no LLM available."""
        excerpts = []
        for result in context[:3]:
            text = result.text[:300]
            if len(result.text) > 300:
                text += "..."
            source = result.metadata.get("section_title", result.document_id)
            excerpts.append(f"**{source}**:\n{text}")

        return "Relevant excerpts:\n\n" + "\n\n---\n\n".join(excerpts)

    def _generate_with_llm(self, question: str, context: str, max_tokens: int) -> str:
        """Generate answer using LLM."""
        system_prompt = (
            "You are a regulatory expert assistant. Answer questions based "
            "solely on the provided context.\n"
            "If the context doesn't contain enough information, say so.\n"
            "Always cite the source when making claims.\n"
            "Be precise and concise."
        )

        user_prompt = f"Context:\n{context}\n\nQuestion: {question}\n\nAnswer based on the context above:"

        try:
            response = self._client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=max_tokens,
                temperature=0.1,
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"Error generating answer: {e!s}"
