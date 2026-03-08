"""Legal corpus loader for regulatory documents.

This module loads legal texts from data/legal/<document_id>/ directories,
where each directory contains:
- meta.yaml: Document metadata (title, citation, jurisdiction, etc.)
- text_normalized.txt: Normalized excerpts of legal provisions
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import yaml


class _Indexable(Protocol):
    def add_documents(self, documents: list[dict[str, Any]]) -> None: ...

# Default path to legal corpus directory
# Path from src/rag/ -> src/ -> project root -> data/legal/
LEGAL_CORPUS_DIR = Path(__file__).parent.parent.parent / "data" / "legal"


@dataclass
class LegalDocument:
    """A legal document with metadata and text."""

    document_id: str
    title: str
    citation: str | None
    jurisdiction: str | None
    source_url: str | None
    text: str

    def get_articles(self) -> list[tuple[str, str]]:
        """Extract article/section references and their text.

        Returns:
            List of (article_ref, text) tuples.
        """
        pattern = r"(?:^|\n)((?:Article|Section|Art\.)\s+\d+(?:\([^)]+\))?(?:\s*-\s*[^\n]+)?)"
        parts = re.split(pattern, self.text, flags=re.IGNORECASE)

        articles = []
        current_article = None

        for part in parts:
            part = part.strip()
            if not part:
                continue

            if re.match(r"^(?:Article|Section|Art\.)\s+\d+", part, re.IGNORECASE):
                current_article = part
            elif current_article:
                articles.append((current_article, part))
                current_article = None

        return articles

    def find_article_text(self, article_ref: str) -> str | None:
        """Find text for a specific article reference.

        Args:
            article_ref: Article reference like "36(1)", "Art. 36", "Section 301"

        Returns:
            Article text if found, None otherwise.
        """
        ref_clean = re.sub(
            r"^(?:Article|Section|Art\.?)\s*",
            "",
            article_ref,
            flags=re.IGNORECASE,
        ).strip()

        match = re.match(r"(\d+)(?:\(([^)]+)\))?", ref_clean)
        if not match:
            return None

        article_num = match.group(1)
        subsection = match.group(2)

        pattern = (
            rf"(?:^|\n)((?:Article|Section)\s+{article_num}\s*"
            rf"(?:-\s*[^\n]+)?)(.*?)(?=(?:\n(?:Article|Section)\s+\d+)|\Z)"
        )
        article_match = re.search(pattern, self.text, re.IGNORECASE | re.DOTALL)

        if article_match:
            header = article_match.group(1).strip()
            body = article_match.group(2).strip()
            full_text = f"{header}\n\n{body}"

            if subsection:
                subsection_pattern = (
                    rf"(?:^|\n)\s*{subsection}\.\s+(.*?)"
                    rf"(?=(?:\n\s*\d+\.)|(?:\n\n)|\Z)"
                )
                sub_match = re.search(subsection_pattern, body, re.DOTALL)
                if sub_match:
                    return f"{header} ({subsection})\n\n{sub_match.group(1).strip()}"

            return full_text

        return None


class LegalCorpusError(Exception):
    """Raised when a legal document cannot be loaded."""


def load_legal_document(
    document_id: str,
    corpus_dir: Path | None = None,
) -> LegalDocument:
    """Load a legal document from the corpus.

    Args:
        document_id: The document identifier (e.g., 'mica_2023')
        corpus_dir: Optional path to corpus directory (defaults to data/legal/)

    Returns:
        LegalDocument with metadata and text.

    Raises:
        LegalCorpusError: If document not found or invalid.
    """
    corpus_dir = corpus_dir or LEGAL_CORPUS_DIR
    doc_dir = corpus_dir / document_id

    if not doc_dir.exists():
        raise LegalCorpusError(f"Legal document not found: {document_id} (looked in {doc_dir})")

    # Load metadata
    meta_path = doc_dir / "meta.yaml"
    if not meta_path.exists():
        raise LegalCorpusError(f"Missing meta.yaml for {document_id}")

    with open(meta_path, encoding="utf-8") as f:
        meta = yaml.safe_load(f)

    if not meta:
        raise LegalCorpusError(f"Empty or invalid meta.yaml for {document_id}")

    # Validate document_id matches
    meta_doc_id = meta.get("document_id")
    if meta_doc_id and meta_doc_id != document_id:
        raise LegalCorpusError(f"Document ID mismatch: directory is '{document_id}' but meta.yaml says '{meta_doc_id}'")

    # Load text
    text_path = doc_dir / "text_normalized.txt"
    if not text_path.exists():
        raise LegalCorpusError(f"Missing text_normalized.txt for {document_id}")

    with open(text_path, encoding="utf-8") as f:
        text = f.read()

    # Strip comment lines from the beginning (lines starting with #)
    lines = text.split("\n")
    content_lines = []
    in_header = True
    for line in lines:
        if in_header and line.strip().startswith("#"):
            continue
        in_header = False
        content_lines.append(line)
    text = "\n".join(content_lines).strip()

    return LegalDocument(
        document_id=document_id,
        title=meta.get("title", document_id),
        citation=meta.get("citation"),
        jurisdiction=meta.get("jurisdiction"),
        source_url=meta.get("source_url"),
        text=text,
    )


def load_all_legal_documents(
    corpus_dir: Path | None = None,
) -> list[LegalDocument]:
    """Load all legal documents from the corpus.

    Args:
        corpus_dir: Optional path to corpus directory (defaults to data/legal/)

    Returns:
        List of LegalDocument objects.
    """
    corpus_dir = corpus_dir or LEGAL_CORPUS_DIR

    if not corpus_dir.exists():
        return []

    documents = []
    for doc_dir in sorted(corpus_dir.iterdir()):
        if doc_dir.is_dir() and not doc_dir.name.startswith("."):
            try:
                doc = load_legal_document(doc_dir.name, corpus_dir)
                documents.append(doc)
            except LegalCorpusError:
                continue

    return documents


def get_available_document_ids(
    corpus_dir: Path | None = None,
) -> list[str]:
    """Get list of available document IDs in the corpus.

    Args:
        corpus_dir: Optional path to corpus directory (defaults to data/legal/)

    Returns:
        List of document_id strings.
    """
    corpus_dir = corpus_dir or LEGAL_CORPUS_DIR

    if not corpus_dir.exists():
        return []

    return [
        d.name
        for d in sorted(corpus_dir.iterdir())
        if d.is_dir() and not d.name.startswith(".") and (d / "meta.yaml").exists()
    ]


def chunk_legal_document(doc: LegalDocument) -> list[dict[str, Any]]:
    """Chunk a legal document by article/section for indexing.

    Args:
        doc: LegalDocument to chunk.

    Returns:
        List of chunk dicts with 'id', 'text', and 'metadata'.
    """
    chunks = []

    pattern = r"(?=(?:^|\n)(?:Article|Section|TITLE|CHAPTER)\s+[\dIVX]+)"
    parts = re.split(pattern, doc.text, flags=re.IGNORECASE)

    for i, part in enumerate(parts):
        part = part.strip()
        if not part or len(part) < 20:
            continue

        first_line = part.split("\n")[0].strip()
        article_ref = None

        article_match = re.match(
            r"^(?:Article|Section)\s+(\d+(?:\([^)]+\))?)",
            first_line,
            re.IGNORECASE,
        )
        if article_match:
            article_ref = article_match.group(1)

        chunk_id = f"{doc.document_id}_legal_{i}"

        chunks.append(
            {
                "id": chunk_id,
                "text": part,
                "metadata": {
                    "document_id": doc.document_id,
                    "document_title": doc.title,
                    "article": article_ref,
                    "citation": doc.citation,
                    "jurisdiction": doc.jurisdiction,
                    "source_type": "legal_text",
                    "source_url": doc.source_url,
                },
            }
        )

    return chunks


def index_legal_corpus(index: _Indexable, corpus_dir: Path | None = None) -> int:
    """Index all legal documents into a BM25Index or Retriever.

    Args:
        index: BM25Index or Retriever instance with add_documents method.
        corpus_dir: Optional path to corpus directory.

    Returns:
        Number of chunks indexed.
    """
    docs = load_all_legal_documents(corpus_dir)

    all_chunks: list[dict[str, Any]] = []
    for doc in docs:
        chunks = chunk_legal_document(doc)
        all_chunks.extend(chunks)

    if all_chunks:
        index.add_documents(all_chunks)

    return len(all_chunks)
