"""Routes for factual Q&A (RAG)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .schemas import AskRequest, AskResponse, SourceCitation
from .service import AnswerGenerator, Retriever

router = APIRouter(prefix="/qa", tags=["Q&A"])

_retriever: Retriever | None = None
_generator: AnswerGenerator | None = None


def get_retriever() -> Retriever:
    """Get or create the retriever instance."""
    global _retriever
    if _retriever is None:
        _retriever = Retriever()
    return _retriever


def get_generator() -> AnswerGenerator:
    """Get or create the generator instance."""
    global _generator
    if _generator is None:
        _generator = AnswerGenerator()
    return _generator


@router.post("/ask", response_model=AskResponse)
async def ask_question(request: AskRequest) -> AskResponse:
    """Answer a factual question using RAG."""
    retriever = get_retriever()
    generator = get_generator()

    if len(retriever) == 0:
        return AskResponse(
            answer="No documents have been indexed. Please add documents to the corpus first.",
            sources=[],
            method="no_documents",
        )

    results = retriever.search(request.question, top_k=request.top_k)

    if not results:
        return AskResponse(
            answer="No relevant information found for your question.",
            sources=[],
            method="no_results",
        )

    response = generator.generate(request.question, results)

    sources = [
        SourceCitation(
            document_id=s["document_id"],
            chunk_id=s["chunk_id"],
            section=s.get("section"),
            score=s["score"],
        )
        for s in response["sources"]
    ]

    return AskResponse(
        answer=response["answer"],
        sources=sources,
        method=response["method"],
    )


@router.post("/index")
async def index_document(document: dict) -> dict:
    """Index a document for retrieval."""
    retriever = get_retriever()

    if "id" not in document or "text" not in document:
        raise HTTPException(
            status_code=400,
            detail="Document must have 'id' and 'text' fields",
        )

    retriever.add_documents([document])

    return {
        "status": "indexed",
        "document_id": document["id"],
        "total_documents": len(retriever),
    }


@router.get("/status")
async def get_status() -> dict:
    """Get the status of the RAG system."""
    retriever = get_retriever()

    return {
        "documents_indexed": len(retriever),
        "vector_search_available": retriever._collection is not None,
    }
