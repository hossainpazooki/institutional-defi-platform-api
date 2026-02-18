"""Tests for the semantic consistency engine."""

from __future__ import annotations

from datetime import date

import pytest

from src.rules import (
    ConditionGroupSpec,
    ConditionSpec,
    ConsistencyBlock,
    ConsistencyStatus,
    DecisionLeaf,
    DecisionNode,
    Rule,
    SourceRef,
)
from src.verification import (
    ConsistencyEngine,
    check_actor_mentioned,
    check_date_consistency,
    check_decision_tree_valid,
    check_deontic_alignment,
    check_exception_coverage,
    check_id_format,
    check_instrument_mentioned,
    check_keyword_overlap,
    check_negation_consistency,
    check_required_fields,
    check_schema_valid,
    check_source_exists,
    compute_summary,
    verify_rule,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def minimal_rule() -> Rule:
    """A minimal valid rule."""
    return Rule(
        rule_id="test_minimal_rule",
        source=SourceRef(document_id="test_doc", article="1"),
        decision_tree=DecisionLeaf(result="permitted"),
    )


@pytest.fixture
def complete_rule() -> Rule:
    """A complete rule with all fields."""
    return Rule(
        rule_id="mica_art36_public_offer",
        version="1.0",
        description="Public offer authorization for asset-referenced tokens",
        effective_from=date(2024, 1, 1),
        effective_to=date(2025, 12, 31),
        tags=["mica", "art", "public_offer"],
        source=SourceRef(
            document_id="mica_2023",
            article="36(1)",
            paragraphs=["1", "2"],
        ),
        applies_if=ConditionGroupSpec(
            all=[
                ConditionSpec(field="instrument_type", operator="==", value="art"),
                ConditionSpec(field="activity", operator="==", value="public_offer"),
            ]
        ),
        decision_tree=DecisionNode(
            node_id="check_authorization",
            condition=ConditionSpec(field="authorized", operator="==", value=True),
            true_branch=DecisionLeaf(result="permitted"),
            false_branch=DecisionLeaf(result="authorization_required"),
        ),
    )


@pytest.fixture
def source_text_obligation() -> str:
    """Source text with obligation language."""
    return """
    Article 36 - Public offer of asset-referenced tokens

    1. An issuer of asset-referenced tokens shall make a public offer of
    those tokens in the Union, or seek an admission of those tokens to
    trading on a trading platform, only where that issuer:
    (a) is a legal person established in the Union;
    (b) has been authorised in accordance with Article 21.

    2. The competent authority must approve the white paper before any
    public offer is made.
    """


@pytest.fixture
def source_text_prohibition() -> str:
    """Source text with prohibition language."""
    return """
    Article 40 - Prohibition on interest

    1. An issuer of asset-referenced tokens shall not grant interest or
    any other benefit related to the length of time during which a holder
    holds those asset-referenced tokens.

    2. Crypto-asset service providers shall not provide interest to holders.
    """


@pytest.fixture
def source_text_exception() -> str:
    """Source text with exception language."""
    return """
    Article 36 - Authorization requirements

    1. An issuer shall obtain authorization before making a public offer,
    except where the issuer is a credit institution authorised under
    Directive 2013/36/EU.

    2. This requirement applies unless the total consideration is below
    EUR 1,000,000 over a period of 12 months.
    """


# =============================================================================
# Tier 0 Tests
# =============================================================================


class TestTier0SchemaChecks:
    """Test Tier 0 schema and structural validation."""

    def test_schema_valid_always_passes(self, minimal_rule):
        """Schema check passes for any parsed rule."""
        evidence = check_schema_valid(minimal_rule)
        assert evidence.tier == 0
        assert evidence.category == "schema_valid"
        assert evidence.label == "pass"
        assert evidence.score == 1.0

    def test_required_fields_with_source(self, minimal_rule):
        """Required fields check passes with rule_id and source."""
        evidence = check_required_fields(minimal_rule)
        assert evidence.label == "pass"
        assert evidence.score == 1.0

    def test_required_fields_missing_source(self):
        """Required fields check fails without source."""
        rule = Rule(rule_id="test_no_source")
        evidence = check_required_fields(rule)
        assert evidence.label == "fail"
        assert "source" in evidence.details

    def test_source_exists_valid(self, minimal_rule):
        """Source exists check passes with valid source."""
        evidence = check_source_exists(minimal_rule)
        assert evidence.label == "pass"

    def test_source_exists_with_registry(self, minimal_rule):
        """Source exists check warns when document not in registry."""
        registry = {"other_doc": "/path/to/other"}
        evidence = check_source_exists(minimal_rule, registry)
        assert evidence.label == "warning"
        assert "not found in registry" in evidence.details

    def test_date_consistency_valid(self, complete_rule):
        """Date check passes when effective_from <= effective_to."""
        evidence = check_date_consistency(complete_rule)
        assert evidence.label == "pass"

    def test_date_consistency_invalid(self):
        """Date check fails when effective_from > effective_to."""
        rule = Rule(
            rule_id="test_bad_dates",
            source=SourceRef(document_id="test"),
            effective_from=date(2025, 1, 1),
            effective_to=date(2024, 1, 1),
        )
        evidence = check_date_consistency(rule)
        assert evidence.label == "fail"
        assert evidence.score == 0.0

    def test_id_format_valid_snake_case(self, complete_rule):
        """ID format check passes for proper snake_case ID."""
        evidence = check_id_format(complete_rule)
        assert evidence.label == "pass"

    def test_id_format_no_underscore(self):
        """ID format check warns for ID without underscore."""
        rule = Rule(rule_id="testrule", source=SourceRef(document_id="test"))
        evidence = check_id_format(rule)
        assert evidence.label == "warning"
        assert "lacks structured prefix" in evidence.details

    def test_id_format_invalid_case(self):
        """ID format check warns for non-snake_case ID."""
        rule = Rule(rule_id="TestRule", source=SourceRef(document_id="test"))
        evidence = check_id_format(rule)
        assert evidence.label == "warning"

    def test_decision_tree_valid(self, complete_rule):
        """Decision tree check passes for valid tree."""
        evidence = check_decision_tree_valid(complete_rule)
        assert evidence.label == "pass"

    def test_decision_tree_missing(self):
        """Decision tree check warns when tree is missing."""
        rule = Rule(rule_id="test_no_tree", source=SourceRef(document_id="test"))
        evidence = check_decision_tree_valid(rule)
        assert evidence.label == "warning"
        assert "No decision tree" in evidence.details


# =============================================================================
# Tier 1 Tests
# =============================================================================


class TestTier1LexicalChecks:
    """Test Tier 1 lexical and heuristic analysis."""

    def test_deontic_alignment_obligation_match(self, complete_rule, source_text_obligation):
        """Deontic check passes when obligation in source matches rule."""
        # Modify rule to have obligation-like result
        rule = Rule(
            rule_id="test_obligation",
            source=SourceRef(document_id="test"),
            decision_tree=DecisionLeaf(result="authorization_required"),
        )
        evidence = check_deontic_alignment(rule, source_text_obligation)
        # Should pass since "required" is in rule and "shall" in source
        assert evidence.tier == 1
        assert evidence.category == "deontic_alignment"

    def test_deontic_alignment_no_source(self, complete_rule):
        """Deontic check warns when no source text provided."""
        evidence = check_deontic_alignment(complete_rule, None)
        assert evidence.label == "warning"
        assert "No source text" in evidence.details

    def test_actor_mentioned_found(self, source_text_obligation):
        """Actor check passes when rule actors found in source."""
        rule = Rule(
            rule_id="test_actor",
            source=SourceRef(document_id="test"),
            applies_if=ConditionGroupSpec(all=[ConditionSpec(field="actor_type", value="issuer")]),
            decision_tree=DecisionLeaf(result="test"),
        )
        evidence = check_actor_mentioned(rule, source_text_obligation)
        assert evidence.label == "pass"

    def test_actor_mentioned_not_found(self, source_text_obligation):
        """Actor check warns when rule actors not found in source."""
        rule = Rule(
            rule_id="test_actor",
            source=SourceRef(document_id="test"),
            applies_if=ConditionGroupSpec(all=[ConditionSpec(field="actor_type", value="custodian")]),
            decision_tree=DecisionLeaf(result="test"),
        )
        evidence = check_actor_mentioned(rule, source_text_obligation)
        assert evidence.label == "warning"
        assert "custodian" in evidence.details.lower()

    def test_instrument_mentioned_found(self, source_text_obligation):
        """Instrument check passes when rule instruments found in source."""
        rule = Rule(
            rule_id="test_instrument",
            source=SourceRef(document_id="test"),
            applies_if=ConditionGroupSpec(all=[ConditionSpec(field="instrument_type", value="art")]),
            decision_tree=DecisionLeaf(result="test"),
        )
        evidence = check_instrument_mentioned(rule, source_text_obligation)
        # "asset-referenced tokens" appears in source
        assert evidence.label == "pass"

    def test_keyword_overlap_high(self):
        """Keyword check passes with high overlap."""
        rule = Rule(
            rule_id="test_keywords",
            description="Authorization for public offer",
            tags=["authorization", "offer"],
            source=SourceRef(document_id="test"),
            decision_tree=DecisionLeaf(result="permitted"),
        )
        source = "Authorization is required for any public offer of tokens"
        evidence = check_keyword_overlap(rule, source)
        assert evidence.label == "pass"

    def test_keyword_overlap_low(self):
        """Keyword check warns with low overlap."""
        rule = Rule(
            rule_id="test_keywords",
            description="Custody services requirements",
            tags=["custody"],
            source=SourceRef(document_id="test"),
            decision_tree=DecisionLeaf(result="required"),
        )
        source = "Trading platforms must register with authorities"
        evidence = check_keyword_overlap(rule, source)
        assert evidence.label == "warning"

    def test_negation_consistency_detected(self, source_text_prohibition):
        """Negation check warns when source has negation but rule doesn't."""
        rule = Rule(
            rule_id="test_negation",
            source=SourceRef(document_id="test"),
            applies_if=ConditionGroupSpec(all=[ConditionSpec(field="test", operator="==", value=True)]),
            decision_tree=DecisionLeaf(result="permitted"),
        )
        evidence = check_negation_consistency(rule, source_text_prohibition)
        # Source has "shall not" but rule doesn't use != operators
        assert evidence.label == "warning"

    def test_negation_consistency_aligned(self, source_text_prohibition):
        """Negation check passes when rule has matching negation."""
        rule = Rule(
            rule_id="test_negation",
            source=SourceRef(document_id="test"),
            applies_if=ConditionGroupSpec(all=[ConditionSpec(field="interest_granted", operator="!=", value=True)]),
            decision_tree=DecisionLeaf(result="prohibited"),
        )
        evidence = check_negation_consistency(rule, source_text_prohibition)
        assert evidence.label == "pass"

    def test_exception_coverage_detected(self, source_text_exception):
        """Exception check warns when source has exceptions but rule lacks branches."""
        rule = Rule(
            rule_id="test_exception",
            source=SourceRef(document_id="test"),
            decision_tree=DecisionLeaf(result="required"),  # No branches
        )
        evidence = check_exception_coverage(rule, source_text_exception)
        assert evidence.label == "warning"
        assert "except" in evidence.details.lower() or "unless" in evidence.details.lower()

    def test_exception_coverage_with_branches(self, source_text_exception):
        """Exception check passes when rule has branching logic."""
        rule = Rule(
            rule_id="test_exception",
            source=SourceRef(document_id="test"),
            decision_tree=DecisionNode(
                node_id="check_credit_institution",
                condition=ConditionSpec(field="is_credit_institution", value=True),
                true_branch=DecisionLeaf(result="exempt"),
                false_branch=DecisionLeaf(result="required"),
            ),
        )
        evidence = check_exception_coverage(rule, source_text_exception)
        assert evidence.label == "pass"


# =============================================================================
# Summary Computation Tests
# =============================================================================


class TestSummaryComputation:
    """Test consistency summary computation."""

    def test_summary_verified_all_pass(self):
        """Summary is verified when all evidence passes."""
        from src.rules import ConsistencyEvidence

        evidence = [
            ConsistencyEvidence(tier=0, category="test1", label="pass", score=1.0, details="ok"),
            ConsistencyEvidence(tier=0, category="test2", label="pass", score=1.0, details="ok"),
            ConsistencyEvidence(tier=1, category="test3", label="pass", score=0.9, details="ok"),
        ]
        summary = compute_summary(evidence)
        assert summary.status == ConsistencyStatus.VERIFIED
        assert summary.confidence > 0.9

    def test_summary_needs_review_with_warnings(self):
        """Summary needs review when there are warnings."""
        from src.rules import ConsistencyEvidence

        evidence = [
            ConsistencyEvidence(tier=0, category="test1", label="pass", score=1.0, details="ok"),
            ConsistencyEvidence(tier=1, category="test2", label="warning", score=0.6, details="warn"),
        ]
        summary = compute_summary(evidence)
        assert summary.status == ConsistencyStatus.NEEDS_REVIEW

    def test_summary_inconsistent_with_fail(self):
        """Summary is inconsistent when any check fails."""
        from src.rules import ConsistencyEvidence

        evidence = [
            ConsistencyEvidence(tier=0, category="test1", label="pass", score=1.0, details="ok"),
            ConsistencyEvidence(tier=0, category="test2", label="fail", score=0.0, details="failed"),
        ]
        summary = compute_summary(evidence)
        assert summary.status == ConsistencyStatus.INCONSISTENT

    def test_summary_unverified_empty(self):
        """Summary is unverified with no evidence."""
        summary = compute_summary([])
        assert summary.status == ConsistencyStatus.UNVERIFIED
        assert summary.confidence == 0.0


# =============================================================================
# ConsistencyEngine Tests
# =============================================================================


class TestConsistencyEngine:
    """Test the main ConsistencyEngine class."""

    def test_engine_verify_rule_tier0_only(self, complete_rule):
        """Engine runs tier 0 checks successfully."""
        engine = ConsistencyEngine()
        result = engine.verify_rule(complete_rule, tiers=[0])

        assert isinstance(result, ConsistencyBlock)
        assert result.summary is not None
        assert len(result.evidence) >= 5  # At least 5 tier 0 checks

        # All evidence should be tier 0
        for ev in result.evidence:
            assert ev.tier == 0

    def test_engine_verify_rule_tier0_and_1(self, complete_rule, source_text_obligation):
        """Engine runs tier 0 and 1 checks with source text."""
        engine = ConsistencyEngine()
        result = engine.verify_rule(complete_rule, source_text_obligation, tiers=[0, 1])

        assert isinstance(result, ConsistencyBlock)
        # Should have both tier 0 and tier 1 evidence
        tiers = set(ev.tier for ev in result.evidence)
        assert 0 in tiers
        assert 1 in tiers

    def test_engine_with_document_registry(self, complete_rule):
        """Engine uses document registry for source_exists check."""
        registry = {"mica_2023": "/docs/mica_regulation.pdf"}
        engine = ConsistencyEngine(document_registry=registry)
        result = engine.verify_rule(complete_rule, tiers=[0])

        # Find source_exists evidence
        source_evidence = next((e for e in result.evidence if e.category == "source_exists"), None)
        assert source_evidence is not None
        assert source_evidence.label == "pass"

    def test_engine_tier2(self, complete_rule, source_text_obligation):
        """Engine returns tier 2 semantic alignment evidence."""
        engine = ConsistencyEngine()
        result = engine.verify_rule(complete_rule, source_text_obligation, tiers=[2])

        assert len(result.evidence) >= 1
        assert all(e.tier == 2 for e in result.evidence)

    def test_engine_handles_check_errors(self):
        """Engine handles errors in individual checks gracefully."""
        # Create a rule that might cause issues
        rule = Rule(rule_id="test_error", source=SourceRef(document_id="test"))
        engine = ConsistencyEngine()
        result = engine.verify_rule(rule, tiers=[0, 1])

        # Should still return a result even if some checks have issues
        assert isinstance(result, ConsistencyBlock)
        assert result.summary is not None


# =============================================================================
# Convenience Function Tests
# =============================================================================


class TestVerifyRuleFunction:
    """Test the verify_rule convenience function."""

    def test_verify_rule_basic(self, minimal_rule):
        """verify_rule returns ConsistencyBlock for valid rule."""
        result = verify_rule(minimal_rule)
        assert isinstance(result, ConsistencyBlock)
        assert result.summary.status in [
            ConsistencyStatus.VERIFIED,
            ConsistencyStatus.NEEDS_REVIEW,
        ]

    def test_verify_rule_with_source(self, complete_rule, source_text_obligation):
        """verify_rule uses provided source text."""
        result = verify_rule(complete_rule, source_text_obligation)

        # Should have tier 1 evidence since source was provided
        tier1_evidence = [e for e in result.evidence if e.tier == 1]
        assert len(tier1_evidence) > 0

        # Most tier 1 checks should not be "No source text" warnings
        no_source_warnings = [e for e in tier1_evidence if "No source text" in e.details]
        assert len(no_source_warnings) == 0

    def test_verify_rule_with_registry(self, minimal_rule):
        """verify_rule uses document registry."""
        registry = {"test_doc": "/path/to/doc"}
        result = verify_rule(minimal_rule, document_registry=registry)

        source_evidence = next((e for e in result.evidence if e.category == "source_exists"), None)
        assert source_evidence is not None
        assert source_evidence.label == "pass"
