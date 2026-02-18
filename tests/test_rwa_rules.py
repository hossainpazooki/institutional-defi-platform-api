"""Tests for RWA (Real-World Asset) rules."""

from pathlib import Path

import pytest

from src.ontology import Scenario
from src.rules import DecisionEngine, RuleLoader


@pytest.fixture
def rule_loader():
    """Create a rule loader with RWA rules loaded."""
    loader = RuleLoader()
    rules_dir = Path(__file__).parent.parent / "src" / "rules" / "data"
    loader.load_directory(rules_dir)
    return loader


@pytest.fixture
def engine(rule_loader):
    """Create a decision engine with RWA rules."""
    return DecisionEngine(rule_loader)


class TestRWARuleLoading:
    def test_rwa_rules_loaded(self, rule_loader):
        rules = rule_loader.get_all_rules()
        rwa_rules = [r for r in rules if r.rule_id.startswith("rwa_")]
        assert len(rwa_rules) >= 3

    def test_tokenization_rule_exists(self, rule_loader):
        rule = rule_loader.get_rule("rwa_tokenization_authorization")
        assert rule is not None
        assert "tokenization" in rule.tags
        assert "rwa" in rule.tags

    def test_disclosure_rule_exists(self, rule_loader):
        rule = rule_loader.get_rule("rwa_disclosure_requirements")
        assert rule is not None
        assert "disclosure" in rule.tags

    def test_custody_rule_exists(self, rule_loader):
        rule = rule_loader.get_rule("rwa_custody_requirements")
        assert rule is not None
        assert "custody" in rule.tags

    def test_rwa_rules_have_source(self, rule_loader):
        rule = rule_loader.get_rule("rwa_tokenization_authorization")
        assert rule.source is not None
        assert rule.source.document_id == "rwa_eu_2025"
        assert rule.source.article is not None


class TestRWATokenizationAuthorization:
    def test_not_authorized_no_authorization(self, engine):
        scenario = Scenario(
            instrument_type="rwa_token",
            activity="tokenization",
            jurisdiction="EU",
            is_regulated_market_issuer=False,
            rwa_authorized=False,
        )
        result = engine.evaluate(scenario, "rwa_tokenization_authorization")
        assert result.decision == "not_authorized"
        assert len(result.obligations) >= 1
        obligation_ids = [o.id for o in result.obligations]
        assert "obtain_rwa_authorization" in obligation_ids

    def test_authorized_with_rwa_authorization(self, engine):
        scenario = Scenario(
            instrument_type="rwa_debt",
            activity="tokenization",
            jurisdiction="EU",
            is_regulated_market_issuer=False,
            rwa_authorized=True,
        )
        result = engine.evaluate(scenario, "rwa_tokenization_authorization")
        assert result.decision == "authorized"
        assert len(result.obligations) == 0

    def test_authorized_regulated_market_issuer(self, engine):
        scenario = Scenario(
            instrument_type="rwa_equity",
            activity="tokenization",
            jurisdiction="EU",
            is_regulated_market_issuer=True,
            rwa_authorized=False,
        )
        result = engine.evaluate(scenario, "rwa_tokenization_authorization")
        assert result.decision == "authorized"

    def test_not_applicable_non_eu(self, engine):
        scenario = Scenario(
            instrument_type="rwa_token",
            activity="tokenization",
            jurisdiction="US",
            rwa_authorized=False,
        )
        result = engine.evaluate(scenario, "rwa_tokenization_authorization")
        assert result.decision == "not_applicable"

    def test_not_applicable_wrong_activity(self, engine):
        scenario = Scenario(
            instrument_type="rwa_token",
            activity="custody",
            jurisdiction="EU",
            rwa_authorized=False,
        )
        result = engine.evaluate(scenario, "rwa_tokenization_authorization")
        assert result.decision == "not_applicable"


class TestRWADisclosureRequirements:
    def test_compliant_with_current_disclosure(self, engine):
        scenario = Scenario(
            instrument_type="rwa_property",
            activity="disclosure",
            jurisdiction="EU",
            disclosure_current=True,
            total_token_value_eur=5000000,
        )
        result = engine.evaluate(scenario, "rwa_disclosure_requirements")
        assert result.decision == "compliant"

    def test_non_compliant_missing_disclosure(self, engine):
        scenario = Scenario(
            instrument_type="rwa_debt",
            activity="disclosure",
            jurisdiction="EU",
            disclosure_current=False,
            total_token_value_eur=2000000,
        )
        result = engine.evaluate(scenario, "rwa_disclosure_requirements")
        assert result.decision == "non_compliant"
        obligation_ids = [o.id for o in result.obligations]
        assert "submit_quarterly_report" in obligation_ids
        assert "publish_valuation" in obligation_ids

    def test_exempt_small_offering(self, engine):
        scenario = Scenario(
            instrument_type="rwa_token",
            activity="disclosure",
            jurisdiction="EU",
            disclosure_current=False,
            total_token_value_eur=500000,
        )
        result = engine.evaluate(scenario, "rwa_disclosure_requirements")
        assert result.decision == "exempt"


class TestRWACustodyRequirements:
    def test_compliant_authorized_segregated(self, engine):
        scenario = Scenario(
            instrument_type="rwa_equity",
            activity="custody",
            jurisdiction="EU",
            custodian_authorized=True,
            assets_segregated=True,
        )
        result = engine.evaluate(scenario, "rwa_custody_requirements")
        assert result.decision == "compliant"

    def test_non_compliant_not_segregated(self, engine):
        scenario = Scenario(
            instrument_type="rwa_property",
            activity="custody",
            jurisdiction="EU",
            custodian_authorized=True,
            assets_segregated=False,
        )
        result = engine.evaluate(scenario, "rwa_custody_requirements")
        assert result.decision == "non_compliant"
        obligation_ids = [o.id for o in result.obligations]
        assert "segregate_assets" in obligation_ids

    def test_non_compliant_unauthorized_custodian(self, engine):
        scenario = Scenario(
            instrument_type="rwa_debt",
            activity="custody",
            jurisdiction="EU",
            custodian_authorized=False,
            assets_segregated=False,
        )
        result = engine.evaluate(scenario, "rwa_custody_requirements")
        assert result.decision == "non_compliant"
        obligation_ids = [o.id for o in result.obligations]
        assert "appoint_authorized_custodian" in obligation_ids


class TestRWADecisionTrace:
    def test_trace_contains_nodes(self, engine):
        scenario = Scenario(
            instrument_type="rwa_token",
            activity="tokenization",
            jurisdiction="EU",
            is_regulated_market_issuer=False,
            rwa_authorized=False,
        )
        result = engine.evaluate(scenario, "rwa_tokenization_authorization")
        assert len(result.trace) > 0

    def test_trace_shows_path(self, engine):
        scenario = Scenario(
            instrument_type="rwa_debt",
            activity="tokenization",
            jurisdiction="EU",
            is_regulated_market_issuer=True,
        )
        result = engine.evaluate(scenario, "rwa_tokenization_authorization")
        node_ids = [t.node for t in result.trace]
        assert "check_regulated_market" in node_ids or len(result.trace) > 0


class TestRWAAllRulesEvaluation:
    def test_evaluate_all_rwa_rules(self, engine):
        scenario = Scenario(
            instrument_type="rwa_property",
            activity="tokenization",
            jurisdiction="EU",
            is_regulated_market_issuer=False,
            rwa_authorized=False,
        )
        results = engine.evaluate_all(scenario)
        applicable = [r for r in results if r.decision != "not_applicable"]
        assert len(applicable) >= 1

    def test_multiple_rwa_activities(self, engine):
        tokenization_scenario = Scenario(
            instrument_type="rwa_equity",
            activity="tokenization",
            jurisdiction="EU",
            rwa_authorized=True,
        )
        result1 = engine.evaluate(tokenization_scenario, "rwa_tokenization_authorization")
        assert result1.decision == "authorized"

        custody_scenario = Scenario(
            instrument_type="rwa_equity",
            activity="custody",
            jurisdiction="EU",
            custodian_authorized=True,
            assets_segregated=True,
        )
        result2 = engine.evaluate(custody_scenario, "rwa_custody_requirements")
        assert result2.decision == "compliant"
