"""Business logic for embedding rules.

Supports automatic generation of 4 embedding types per rule:
- Semantic: from description
- Structural: from conditions/logic
- Entity: from field names
- Legal: from citations
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import func
from sqlmodel import Session, select

from .generator import EmbeddingGenerator, create_embedding_records
from .models import (
    EmbeddingCondition,
    EmbeddingDecision,
    EmbeddingLegalSource,
    EmbeddingRule,
    EmbeddingType,
    RuleEmbedding,
)

if TYPE_CHECKING:
    from .schemas import RuleCreate, RuleUpdate


class EmbeddingRuleService:
    """Service for embedding rule CRUD operations.

    Automatically generates embeddings when rules are created or updated.
    """

    def __init__(self, session: Session, generate_embeddings: bool = True):
        self.session = session
        self.generate_embeddings = generate_embeddings
        self._generator: EmbeddingGenerator | None = None

    @property
    def generator(self) -> EmbeddingGenerator:
        """Lazy-load the embedding generator."""
        if self._generator is None:
            self._generator = EmbeddingGenerator()
        return self._generator

    def create_rule(self, rule_data: RuleCreate) -> EmbeddingRule:
        rule = EmbeddingRule(
            rule_id=rule_data.rule_id,
            name=rule_data.name,
            description=rule_data.description,
        )
        self.session.add(rule)
        self.session.flush()
        assert rule.id is not None

        for cond_data in rule_data.conditions:
            condition = EmbeddingCondition(
                field=cond_data.field,
                operator=cond_data.operator,
                value=cond_data.value,
                description=cond_data.description,
                rule_id=rule.id,
            )
            self.session.add(condition)

        if rule_data.decision:
            decision = EmbeddingDecision(
                outcome=rule_data.decision.outcome,
                confidence=rule_data.decision.confidence,
                explanation=rule_data.decision.explanation,
                rule_id=rule.id,
            )
            self.session.add(decision)

        for source_data in rule_data.legal_sources:
            source = EmbeddingLegalSource(
                citation=source_data.citation,
                document_id=source_data.document_id,
                url=source_data.url,
                rule_id=rule.id,
            )
            self.session.add(source)

        self.session.flush()
        self.session.refresh(rule)

        if self.generate_embeddings and rule_data.generate_embeddings:
            self._generate_rule_embeddings(rule)

        self.session.commit()
        self.session.refresh(rule)
        return rule

    def _generate_rule_embeddings(self, rule: EmbeddingRule) -> None:
        """Generate and store embeddings for a rule."""
        for emb in rule.embeddings:
            self.session.delete(emb)
        self.session.flush()
        assert rule.id is not None

        generated = self.generator.generate_all(rule)
        records = create_embedding_records(rule.id, generated)

        for record in records:
            self.session.add(record)

    def regenerate_embeddings(self, rule_id: str) -> EmbeddingRule | None:
        """Regenerate embeddings for a rule."""
        rule = self.get_rule_by_rule_id(rule_id)
        if not rule:
            return None

        self._generate_rule_embeddings(rule)
        rule.updated_at = datetime.now(UTC)
        self.session.commit()
        self.session.refresh(rule)
        return rule

    def get_rule_by_rule_id(self, rule_id: str) -> EmbeddingRule | None:
        statement = select(EmbeddingRule).where(EmbeddingRule.rule_id == rule_id)
        return self.session.exec(statement).first()

    def get_rules(self, skip: int = 0, limit: int = 100) -> list[EmbeddingRule]:
        statement = select(EmbeddingRule).offset(skip).limit(limit).order_by(EmbeddingRule.created_at.desc())  # type: ignore[attr-defined]
        return list(self.session.exec(statement).all())

    def update_rule(self, rule_id: str, rule_data: RuleUpdate) -> EmbeddingRule | None:
        rule = self.get_rule_by_rule_id(rule_id)
        if not rule:
            return None
        assert rule.id is not None

        if rule_data.name is not None:
            rule.name = rule_data.name
        if rule_data.description is not None:
            rule.description = rule_data.description
        if rule_data.is_active is not None:
            rule.is_active = rule_data.is_active

        if rule_data.conditions is not None:
            for cond in rule.conditions:
                self.session.delete(cond)
            for cond_data in rule_data.conditions:
                condition = EmbeddingCondition(
                    field=cond_data.field,
                    operator=cond_data.operator,
                    value=cond_data.value,
                    description=cond_data.description,
                    rule_id=rule.id,
                )
                self.session.add(condition)

        if rule_data.decision is not None:
            if rule.decision:
                self.session.delete(rule.decision)
                self.session.flush()
            decision = EmbeddingDecision(
                outcome=rule_data.decision.outcome,
                confidence=rule_data.decision.confidence,
                explanation=rule_data.decision.explanation,
                rule_id=rule.id,
            )
            self.session.add(decision)

        if rule_data.legal_sources is not None:
            for source in rule.legal_sources:
                self.session.delete(source)
            for source_data in rule_data.legal_sources:
                source = EmbeddingLegalSource(
                    citation=source_data.citation,
                    document_id=source_data.document_id,
                    url=source_data.url,
                    rule_id=rule.id,
                )
                self.session.add(source)

        self.session.flush()
        self.session.refresh(rule)

        if self.generate_embeddings and rule_data.regenerate_embeddings:
            self._generate_rule_embeddings(rule)

        rule.updated_at = datetime.now(UTC)
        self.session.commit()
        self.session.refresh(rule)
        return rule

    def soft_delete_rule(self, rule_id: str) -> EmbeddingRule | None:
        rule = self.get_rule_by_rule_id(rule_id)
        if not rule:
            return None

        rule.is_active = False
        rule.updated_at = datetime.now(UTC)
        self.session.commit()
        self.session.refresh(rule)
        return rule

    def search_similar(
        self,
        query: str,
        embedding_types: list[str] | None = None,
        limit: int = 10,
        min_score: float = 0.0,
    ) -> list[dict[str, object]]:
        """Search for rules similar to a query."""
        if embedding_types is None:
            embedding_types = [e.value for e in EmbeddingType]

        query_vector = self.generator._encode(query)

        statement = (
            select(RuleEmbedding, EmbeddingRule)
            .join(EmbeddingRule)
            .where(RuleEmbedding.embedding_type.in_(embedding_types))  # type: ignore[attr-defined]
            .where(EmbeddingRule.is_active == True)  # noqa: E712
        )
        results = self.session.exec(statement).all()

        scored_results = []
        for embedding, rule in results:
            stored_vector = json.loads(embedding.vector_json)
            score = self._cosine_similarity(query_vector, stored_vector)

            if score >= min_score:
                scored_results.append(
                    {
                        "rule_id": rule.rule_id,
                        "rule_name": rule.name,
                        "score": score,
                        "embedding_type": embedding.embedding_type,
                        "matched_text": embedding.source_text,
                    }
                )

        scored_results.sort(key=lambda x: float(x["score"]), reverse=True)  # type: ignore[arg-type]
        return scored_results[:limit]

    @staticmethod
    def _cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        if len(vec1) != len(vec2):
            return 0.0

        dot_product = sum(a * b for a, b in zip(vec1, vec2, strict=False))
        magnitude1 = math.sqrt(sum(a * a for a in vec1))
        magnitude2 = math.sqrt(sum(b * b for b in vec2))

        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0

        return dot_product / (magnitude1 * magnitude2)

    def get_embedding_stats(self) -> dict[str, Any]:
        """Get statistics about stored embeddings."""
        stats: dict[str, Any] = {"total": 0, "by_type": {}}

        for emb_type in EmbeddingType:
            count = self.session.exec(
                select(func.count(RuleEmbedding.id)).where(RuleEmbedding.embedding_type == emb_type.value)  # type: ignore[arg-type]
            ).one()
            stats["by_type"][emb_type.value] = count
            stats["total"] += count

        return stats
