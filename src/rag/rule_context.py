"""Rule context retrieval for consistency verification.

This module provides internal RAG functionality specifically for:
1. Retrieving source context for rules
2. Finding cross-references in legal text
3. Locating similar rules by provision
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from .service import RetrievalResult, Retriever, chunk_by_section, chunk_text

if TYPE_CHECKING:
    from src.rules.service import Rule, RuleLoader


@dataclass
class RuleContext:
    """Retrieved context for a rule."""

    rule_id: str
    source_passages: list[RetrievalResult]
    cross_references: list[str]
    related_rules: list[str]


@dataclass
class ProvisionContext:
    """Context for a legal provision."""

    document_id: str
    article: str | None
    text: str
    surrounding_context: str | None = None
    cross_refs: list[str] | None = None


class RuleContextRetriever:
    """Retrieves context for rules from indexed legal documents.

    This is an internal utility for the consistency engine and KE tools.
    It does NOT use external LLMs - only local retrieval.
    """

    def __init__(
        self,
        retriever: Retriever | None = None,
        rule_loader: RuleLoader | None = None,
    ) -> None:
        """Initialize the rule context retriever.

        Args:
            retriever: Document retriever. If None, creates one without vectors.
            rule_loader: Rule loader for finding related rules.
        """
        self._retriever = retriever or Retriever(use_vectors=False)
        self._rule_loader = rule_loader
        self._indexed_documents: set[str] = set()

    def index_document(
        self,
        document_id: str,
        text: str,
        metadata: dict | None = None,
    ) -> int:
        """Index a legal document for retrieval.

        Args:
            document_id: Unique identifier for the document.
            text: Full text of the document.
            metadata: Optional metadata (e.g., source, date).

        Returns:
            Number of chunks indexed.
        """
        metadata = metadata or {}
        metadata["document_id"] = document_id

        # Try to chunk by article/section first
        chunks = chunk_by_section(
            text=text,
            document_id=document_id,
            section_pattern=r"\n(?=Article \d+)",
            metadata=metadata,
        )

        # Fall back to simple chunking if no sections found
        if len(chunks) <= 1 and len(text) > 500:
            chunks = chunk_text(
                text=text,
                document_id=document_id,
                chunk_size=500,
                chunk_overlap=50,
                metadata=metadata,
            )

        if chunks:
            self._retriever.add_chunks(chunks)
            self._indexed_documents.add(document_id)

        return len(chunks)

    def index_document_file(self, path: str | Path, document_id: str | None = None) -> int:
        """Index a document from a file.

        Args:
            path: Path to the document file.
            document_id: Optional ID (defaults to filename).

        Returns:
            Number of chunks indexed.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Document not found: {path}")

        document_id = document_id or path.stem

        with open(path, encoding="utf-8") as f:
            text = f.read()

        return self.index_document(document_id, text, {"file_path": str(path)})

    def get_source_context(
        self,
        rule: Rule,
        top_k: int = 3,
    ) -> list[RetrievalResult]:
        """Retrieve source context for a rule.

        Args:
            rule: The rule to get context for.
            top_k: Number of passages to retrieve.

        Returns:
            List of relevant passages.
        """
        if not rule.source:
            return []

        query_parts = []

        if rule.source.document_id:
            query_parts.append(rule.source.document_id)

        if rule.source.article:
            query_parts.append(f"Article {rule.source.article}")

        if rule.source.section:
            query_parts.append(rule.source.section)

        if rule.description:
            query_parts.append(rule.description)

        if not query_parts:
            return []

        query = " ".join(query_parts)
        return self._retriever.search(query, top_k=top_k, method="bm25")

    def get_source_text(self, rule: Rule) -> str | None:
        """Get concatenated source text for a rule.

        Args:
            rule: The rule to get source text for.

        Returns:
            Concatenated source text or None.
        """
        results = self.get_source_context(rule, top_k=3)
        if not results:
            return None

        return " ".join(r.text for r in results)

    def find_cross_references(
        self,
        text: str,
        document_id: str | None = None,
    ) -> list[str]:
        """Find cross-references in legal text.

        Args:
            text: Text to analyze for cross-references.
            document_id: Optional document ID to scope search.

        Returns:
            List of referenced articles/provisions.
        """
        refs: list[str] = []

        # Article references
        article_pattern = r"Article\s+(\d+)(?:\((\d+)\))?"
        for match in re.finditer(article_pattern, text, re.IGNORECASE):
            article = match.group(1)
            paragraph = match.group(2)
            ref = f"Article {article}"
            if paragraph:
                ref += f"({paragraph})"
            if ref not in refs:
                refs.append(ref)

        # Directive references
        directive_pattern = r"Directive\s+(\d+/\d+/EU)"
        for match in re.finditer(directive_pattern, text, re.IGNORECASE):
            ref = f"Directive {match.group(1)}"
            if ref not in refs:
                refs.append(ref)

        # Regulation references
        regulation_pattern = r"Regulation\s+\(EU\)\s+(\d+/\d+)"
        for match in re.finditer(regulation_pattern, text, re.IGNORECASE):
            ref = f"Regulation (EU) {match.group(1)}"
            if ref not in refs:
                refs.append(ref)

        return refs

    def find_related_rules(
        self,
        rule: Rule,
        top_k: int = 5,
    ) -> list[Rule]:
        """Find rules related to the given rule.

        Args:
            rule: The rule to find related rules for.
            top_k: Maximum number of related rules to return.

        Returns:
            List of related rules.
        """
        if not self._rule_loader:
            return []

        all_rules = self._rule_loader.get_all_rules()
        scored_rules: list[tuple[Rule, float]] = []

        for other in all_rules:
            if other.rule_id == rule.rule_id:
                continue

            score = 0.0

            # Same source document
            if rule.source and other.source and rule.source.document_id == other.source.document_id:
                score += 2.0

                if rule.source.article and rule.source.article == other.source.article:
                    score += 3.0

            # Overlapping tags
            if rule.tags and other.tags:
                overlap = len(set(rule.tags) & set(other.tags))
                score += overlap * 0.5

            # Similar description keywords
            if rule.description and other.description:
                rule_words = set(rule.description.lower().split())
                other_words = set(other.description.lower().split())
                common = len(rule_words & other_words)
                score += common * 0.2

            if score > 0:
                scored_rules.append((other, score))

        scored_rules.sort(key=lambda x: x[1], reverse=True)
        return [r for r, _ in scored_rules[:top_k]]

    def get_rule_context(self, rule: Rule) -> RuleContext:
        """Get complete context for a rule.

        Args:
            rule: The rule to get context for.

        Returns:
            RuleContext with source passages, cross-references, and related rules.
        """
        source_passages = self.get_source_context(rule, top_k=3)

        cross_refs: list[str] = []
        for passage in source_passages:
            refs = self.find_cross_references(passage.text)
            cross_refs.extend(refs)
        cross_refs = list(set(cross_refs))

        related_rules = self.find_related_rules(rule, top_k=5)
        related_rule_ids = [r.rule_id for r in related_rules]

        return RuleContext(
            rule_id=rule.rule_id,
            source_passages=source_passages,
            cross_references=cross_refs,
            related_rules=related_rule_ids,
        )

    @property
    def indexed_documents(self) -> set[str]:
        """Get set of indexed document IDs."""
        return self._indexed_documents.copy()

    def __len__(self) -> int:
        """Return number of chunks indexed."""
        return len(self._retriever)
