"""Unit tests for decoder service."""

import pytest

from src.decoder import (
    CitationInjector,
    CounterfactualEngine,
    DecoderService,
    DeltaAnalysis,
    DeltaAnalyzer,
    ExplanationTier,
    OutcomeSummary,
    Scenario,
    ScenarioType,
    TemplateRegistry,
)

# ============================================================================
# DeltaAnalyzer Tests
# ============================================================================


class TestDeltaAnalyzer:
    """Tests for DeltaAnalyzer."""

    @pytest.fixture
    def analyzer(self):
        return DeltaAnalyzer()

    def test_compare_identical_outcomes(self, analyzer):
        """Test comparing identical outcomes produces no changes."""
        baseline = OutcomeSummary(
            status="APPROVED",
            framework="MiCA",
            risk_level="LOW",
            conditions=["Condition A", "Condition B"],
        )
        counterfactual = OutcomeSummary(
            status="APPROVED",
            framework="MiCA",
            risk_level="LOW",
            conditions=["Condition A", "Condition B"],
        )

        delta = analyzer.compare(baseline, counterfactual)

        assert delta.status_changed is False
        assert delta.framework_changed is False
        assert delta.risk_delta == 0
        assert len(delta.new_requirements) == 0
        assert len(delta.removed_requirements) == 0

    def test_compare_status_change(self, analyzer):
        """Test detecting status changes."""
        baseline = OutcomeSummary(
            status="APPROVED",
            framework="MiCA",
            risk_level="LOW",
        )
        counterfactual = OutcomeSummary(
            status="DENIED",
            framework="MiCA",
            risk_level="HIGH",
        )

        delta = analyzer.compare(baseline, counterfactual)

        assert delta.status_changed is True
        assert delta.status_from == "APPROVED"
        assert delta.status_to == "DENIED"

    def test_compare_framework_change(self, analyzer):
        """Test detecting framework changes."""
        baseline = OutcomeSummary(
            status="APPROVED",
            framework="MiCA",
            risk_level="LOW",
        )
        counterfactual = OutcomeSummary(
            status="APPROVED",
            framework="FCA",
            risk_level="LOW",
        )

        delta = analyzer.compare(baseline, counterfactual)

        assert delta.framework_changed is True
        assert delta.frameworks_removed == ["MiCA"]
        assert delta.frameworks_added == ["FCA"]

    def test_compare_risk_increase(self, analyzer):
        """Test detecting risk level increase."""
        baseline = OutcomeSummary(
            status="APPROVED",
            framework="MiCA",
            risk_level="LOW",
        )
        counterfactual = OutcomeSummary(
            status="CONDITIONAL",
            framework="MiCA",
            risk_level="HIGH",
        )

        delta = analyzer.compare(baseline, counterfactual)

        assert delta.risk_delta == 2  # LOW -> HIGH is +2
        assert len(delta.risk_factors_added) > 0

    def test_compare_risk_decrease(self, analyzer):
        """Test detecting risk level decrease."""
        baseline = OutcomeSummary(
            status="CONDITIONAL",
            framework="MiCA",
            risk_level="HIGH",
        )
        counterfactual = OutcomeSummary(
            status="APPROVED",
            framework="MiCA",
            risk_level="LOW",
        )

        delta = analyzer.compare(baseline, counterfactual)

        assert delta.risk_delta == -2  # HIGH -> LOW is -2
        assert len(delta.risk_factors_removed) > 0

    def test_compare_new_requirements(self, analyzer):
        """Test detecting new requirements."""
        baseline = OutcomeSummary(
            status="APPROVED",
            framework="MiCA",
            conditions=["Existing condition"],
        )
        counterfactual = OutcomeSummary(
            status="CONDITIONAL",
            framework="MiCA",
            conditions=["Existing condition", "New requirement"],
        )

        delta = analyzer.compare(baseline, counterfactual)

        assert "New requirement" in delta.new_requirements

    def test_compare_removed_requirements(self, analyzer):
        """Test detecting removed requirements."""
        baseline = OutcomeSummary(
            status="CONDITIONAL",
            framework="MiCA",
            conditions=["Existing condition", "Removable condition"],
        )
        counterfactual = OutcomeSummary(
            status="APPROVED",
            framework="MiCA",
            conditions=["Existing condition"],
        )

        delta = analyzer.compare(baseline, counterfactual)

        assert "Removable condition" in delta.removed_requirements

    def test_summarize_impact_no_changes(self, analyzer):
        """Test impact summary when no changes."""
        delta = DeltaAnalysis()
        summary = analyzer.summarize_impact(delta)
        assert summary == "No significant changes detected."

    def test_summarize_impact_with_changes(self, analyzer):
        """Test impact summary with multiple changes."""
        delta = DeltaAnalysis(
            status_changed=True,
            status_from="APPROVED",
            status_to="DENIED",
            risk_delta=2,
            new_requirements=["Req 1", "Req 2"],
        )
        summary = analyzer.summarize_impact(delta)

        assert "APPROVED" in summary
        assert "DENIED" in summary
        assert "increases" in summary
        assert "2 new requirement" in summary

    def test_calculate_severity_low(self, analyzer):
        """Test severity calculation for minor changes."""
        delta = DeltaAnalysis()
        severity = analyzer.calculate_severity(delta)
        assert severity == "low"

    def test_calculate_severity_critical(self, analyzer):
        """Test severity calculation for critical changes."""
        delta = DeltaAnalysis(
            status_changed=True,
            status_from="APPROVED",
            status_to="DENIED",
            risk_delta=2,
            new_requirements=["A", "B", "C"],
        )
        severity = analyzer.calculate_severity(delta)
        assert severity == "critical"


# ============================================================================
# TemplateRegistry Tests
# ============================================================================


class TestTemplateRegistry:
    """Tests for TemplateRegistry."""

    @pytest.fixture
    def registry(self):
        return TemplateRegistry()

    def test_default_templates_loaded(self, registry):
        """Test that default templates are loaded on init."""
        templates = registry.list_templates()
        assert len(templates) > 0

    def test_get_template_by_id(self, registry):
        """Test getting a template by ID."""
        template = registry.get("mica_compliant_general")
        assert template is not None
        assert template.id == "mica_compliant_general"

    def test_get_nonexistent_template(self, registry):
        """Test getting a nonexistent template returns None."""
        template = registry.get("nonexistent")
        assert template is None

    def test_select_mica_compliant(self, registry):
        """Test selecting MiCA compliant template."""
        template = registry.select(
            activity_type="trading",
            framework="MiCA",
            outcome="compliant",
        )
        assert template is not None
        assert "MiCA" in template.frameworks
        assert template.outcome == "compliant"

    def test_select_mica_conditional(self, registry):
        """Test selecting MiCA conditional template."""
        template = registry.select(
            activity_type="public_offer",
            framework="MiCA",
            outcome="conditional",
        )
        assert template is not None
        assert template.outcome == "conditional"

    def test_select_mica_non_compliant(self, registry):
        """Test selecting MiCA non-compliant template."""
        template = registry.select(
            activity_type="swap",
            framework="MiCA",
            outcome="non_compliant",
        )
        assert template is not None
        assert template.outcome == "non_compliant"

    def test_select_fca_template(self, registry):
        """Test selecting FCA template."""
        template = registry.select(
            activity_type="trading",
            framework="FCA",
            outcome="compliant",
        )
        assert template is not None
        assert "FCA" in template.frameworks

    def test_select_fallback_template(self, registry):
        """Test fallback template when no match."""
        template = registry.select(
            activity_type="unknown",
            framework="Unknown",
            outcome="compliant",
        )
        assert template is not None
        assert template.id == "generic_fallback"

    def test_render_template(self, registry):
        """Test rendering a template with variables."""
        template = registry.get("mica_compliant_general")
        rendered = registry.render_template(
            template,
            ExplanationTier.RETAIL,
            {"activity_type": "swap", "rule_id": "test_rule"},
        )
        assert "headline" in rendered
        assert "body" in rendered
        assert "swap" in rendered["body"]


# ============================================================================
# CitationInjector Tests
# ============================================================================


class TestCitationInjector:
    """Tests for CitationInjector."""

    @pytest.fixture
    def injector(self):
        return CitationInjector()

    def test_get_citations_pattern_based(self, injector):
        """Test getting citations using pattern matching."""
        citations = injector.get_citations(
            rule_id="mica_authorization_check",
            framework="MiCA",
            max_citations=3,
        )
        assert len(citations) <= 3
        for citation in citations:
            assert citation.framework == "MiCA"

    def test_get_citation_by_reference(self, injector):
        """Test getting a specific citation by reference."""
        citation = injector.get_citation_by_reference(
            framework="MiCA",
            reference="Art. 3(1)(5)",
        )
        assert citation is not None
        assert citation.framework == "MiCA"
        assert citation.reference == "Art. 3(1)(5)"
        assert "Regulation (EU) 2023/1114" in citation.full_reference

    def test_citation_enrichment(self, injector):
        """Test that citations are enriched with metadata."""
        citations = injector.get_citations(
            rule_id="mica_stablecoin_reserve",
            framework="MiCA",
            activity_type="stablecoin",
        )
        if citations:
            citation = citations[0]
            assert citation.full_reference is not None
            assert citation.url is not None

    def test_extract_categories(self, injector):
        """Test category extraction from rule ID."""
        categories = injector._extract_categories(
            rule_id="mica_casp_authorization",
            activity_type="trading",
        )
        assert "casp" in categories or "authorization" in categories


# ============================================================================
# DecoderService Tests
# ============================================================================


class TestDecoderService:
    """Tests for DecoderService."""

    @pytest.fixture
    def decoder(self):
        return DecoderService()

    def test_citation_limit_by_tier(self, decoder):
        """Test citation limits for different tiers."""
        assert decoder._citation_limit_for_tier(ExplanationTier.RETAIL) == 0
        assert decoder._citation_limit_for_tier(ExplanationTier.PROTOCOL) == 3
        assert decoder._citation_limit_for_tier(ExplanationTier.INSTITUTIONAL) == 5
        assert decoder._citation_limit_for_tier(ExplanationTier.REGULATOR) == 10

    def test_map_outcome(self, decoder):
        """Test mapping status to template outcome."""
        assert decoder._map_outcome("APPROVED") == "compliant"
        assert decoder._map_outcome("NOT_APPLICABLE") == "compliant"
        assert decoder._map_outcome("CONDITIONAL") == "conditional"
        assert decoder._map_outcome("DENIED") == "non_compliant"

    def test_assess_risk(self, decoder):
        """Test risk assessment from mock decision."""

        # Create a mock decision
        class MockDecision:
            applicable = True
            decision = "denied"
            trace = []

        mock = MockDecision()
        mock.rule_metadata = None
        risk = decoder._assess_risk(mock)
        assert risk == "HIGH"

        mock.decision = "approved"
        risk = decoder._assess_risk(mock)
        assert risk == "LOW"

    def test_explain_by_id_placeholder(self, decoder):
        """Test explain_by_id returns placeholder for unknown decision."""
        response = decoder.explain_by_id("unknown_decision_id")
        assert response.decision_id == "unknown_decision_id"
        assert response.summary.status == "UNKNOWN"
        assert "could not find" in response.explanation.body.lower()


# ============================================================================
# CounterfactualEngine Tests
# ============================================================================


class TestCounterfactualEngine:
    """Tests for CounterfactualEngine."""

    @pytest.fixture
    def engine(self):
        return CounterfactualEngine()

    def test_outcome_score(self, engine):
        """Test outcome scoring."""
        approved_low = OutcomeSummary(
            status="APPROVED",
            framework="MiCA",
            risk_level="LOW",
        )
        denied_high = OutcomeSummary(
            status="DENIED",
            framework="MiCA",
            risk_level="HIGH",
        )

        score_approved = engine._outcome_score(approved_low)
        score_denied = engine._outcome_score(denied_high)

        assert score_approved > score_denied

    def test_apply_jurisdiction_change(self, engine):
        """Test jurisdiction change scenario."""

        # Create a mock baseline decision
        class MockDecision:
            rule_id = "test_rule"
            applicable = True
            decision = "approved"
            trace = []
            obligations = []
            source = None
            notes = None
            rule_metadata = None

        mock = MockDecision()

        scenario = Scenario(
            type=ScenarioType.JURISDICTION_CHANGE,
            name="Move to UK",
            parameters={"to_jurisdiction": "UK"},
        )

        outcome = engine._apply_jurisdiction_change(mock, scenario)

        assert outcome.framework == "FCA"

    def test_apply_entity_change_retail(self, engine):
        """Test entity change to retail."""

        class MockDecision:
            rule_id = "test_rule"
            applicable = True
            decision = "approved"
            trace = []
            obligations = []
            source = None
            notes = None
            rule_metadata = None

        mock = MockDecision()

        scenario = Scenario(
            type=ScenarioType.ENTITY_CHANGE,
            parameters={"to_entity_type": "retail"},
        )

        outcome = engine._apply_entity_change(mock, scenario)

        # Retail typically adds restrictions
        assert any("retail" in c.lower() for c in outcome.conditions)

    def test_generate_explanation(self, engine):
        """Test explanation generation."""
        baseline = OutcomeSummary(
            status="APPROVED",
            framework="MiCA",
            risk_level="LOW",
        )
        counterfactual = OutcomeSummary(
            status="DENIED",
            framework="FCA",
            risk_level="HIGH",
        )
        delta = DeltaAnalysis(
            status_changed=True,
            status_from="APPROVED",
            status_to="DENIED",
            framework_changed=True,
            risk_delta=2,
        )
        scenario = Scenario(
            type=ScenarioType.JURISDICTION_CHANGE,
            parameters={"to_jurisdiction": "UK"},
        )

        explanation = engine._generate_explanation(baseline, counterfactual, delta, scenario)

        assert "APPROVED" in explanation.summary
        assert "DENIED" in explanation.summary

    def test_build_matrix(self, engine):
        """Test comparison matrix building."""
        baseline = OutcomeSummary(
            status="APPROVED",
            framework="MiCA",
            risk_level="LOW",
        )

        # Create mock results
        from src.decoder import CounterfactualResponse

        results = [
            CounterfactualResponse(
                baseline_decision_id="test",
                scenario_applied=Scenario(
                    type=ScenarioType.JURISDICTION_CHANGE,
                    name="Scenario 1",
                    parameters={},
                ),
                baseline_outcome=baseline,
                counterfactual_outcome=OutcomeSummary(
                    status="CONDITIONAL",
                    framework="FCA",
                    risk_level="MEDIUM",
                ),
                delta=DeltaAnalysis(),
            ),
        ]

        matrix = engine._build_matrix(baseline, results)

        assert "scenario" in matrix
        assert "status" in matrix
        assert "Baseline" in matrix["scenario"]
        assert "Scenario 1" in matrix["scenario"]


# ============================================================================
# Scenario Tests
# ============================================================================


class TestScenario:
    """Tests for Scenario model."""

    def test_scenario_creation(self):
        """Test creating a scenario."""
        scenario = Scenario(
            type=ScenarioType.JURISDICTION_CHANGE,
            name="Move to EU",
            parameters={"from_jurisdiction": "UK", "to_jurisdiction": "EU"},
        )

        assert scenario.type == ScenarioType.JURISDICTION_CHANGE
        assert scenario.name == "Move to EU"
        assert scenario.parameters["to_jurisdiction"] == "EU"

    def test_all_scenario_types(self):
        """Test all scenario types are valid."""
        types = [
            ScenarioType.JURISDICTION_CHANGE,
            ScenarioType.ENTITY_CHANGE,
            ScenarioType.ACTIVITY_RESTRUCTURE,
            ScenarioType.THRESHOLD,
            ScenarioType.TEMPORAL,
            ScenarioType.PROTOCOL_CHANGE,
            ScenarioType.REGULATORY_CHANGE,
        ]

        for scenario_type in types:
            scenario = Scenario(type=scenario_type, parameters={})
            assert scenario.type == scenario_type
