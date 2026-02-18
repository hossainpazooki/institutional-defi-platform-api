"""RAG domain - factual Q&A with retrieval augmented generation."""

from .corpus_loader import (
    LegalCorpusError,
    LegalDocument,
    chunk_legal_document,
    get_available_document_ids,
    index_legal_corpus,
    load_all_legal_documents,
    load_legal_document,
)
from .router import router
from .rule_context import (
    ProvisionContext,
    RuleContext,
    RuleContextRetriever,
)
from .schemas import AskRequest, AskResponse, SourceCitation
from .service import (
    AnswerGenerator,
    BM25Document,
    BM25Index,
    Chunk,
    RetrievalResult,
    Retriever,
    chunk_by_section,
    chunk_text,
)
from .utils import (
    ArticleHit,
    RelatedProvision,
    RuleContextPayload,
    SearchResult,
    SemanticHit,
    get_related_provisions,
    get_rule_context,
    search_corpus,
)

__all__ = [
    # Router
    "router",
    # Schemas
    "AskRequest",
    "AskResponse",
    "SourceCitation",
    # Chunking
    "Chunk",
    "chunk_text",
    "chunk_by_section",
    # BM25
    "BM25Document",
    "BM25Index",
    # Retrieval
    "RetrievalResult",
    "Retriever",
    # Generation
    "AnswerGenerator",
    # Legal Corpus
    "LegalDocument",
    "LegalCorpusError",
    "load_legal_document",
    "load_all_legal_documents",
    "get_available_document_ids",
    "chunk_legal_document",
    "index_legal_corpus",
    # Rule Context
    "RuleContextRetriever",
    "RuleContext",
    "ProvisionContext",
    # Utils (formerly frontend_helpers)
    "RuleContextPayload",
    "RelatedProvision",
    "ArticleHit",
    "SemanticHit",
    "SearchResult",
    "get_rule_context",
    "get_related_provisions",
    "search_corpus",
]
