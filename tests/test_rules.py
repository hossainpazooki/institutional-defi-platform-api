"""Tests for rule loading and decision engine."""

from datetime import date
from pathlib import Path

from src.ontology import Scenario
from src.rules import ConditionSpec, DecisionEngine, Rule, RuleLoader


class TestRuleLoader:
    def test_load_yaml_file(self, rules_dir: Path):
        loader = RuleLoader()
        rules = loader.load_file(rules_dir / "mica_authorization.yaml")
        assert len(rules) >= 1
        assert all(isinstance(r, Rule) for r in rules)

    def test_load_directory(self, rules_dir: Path):
        loader = RuleLoader(rules_dir)
        rules = loader.load_directory()
        assert len(rules) >= 2  # At least authorization and stablecoin rules

    def test_get_rule_by_id(self, rule_loader: RuleLoader):
        rule = rule_loader.get_rule("mica_art36_public_offer_authorization")
        assert rule is not None
        assert rule.rule_id == "mica_art36_public_offer_authorization"

    def test_get_all_rules(self, rule_loader: RuleLoader):
        rules = rule_loader.get_all_rules()
        assert len(rules) >= 2

    def test_rule_has_source(self, rule_loader: RuleLoader):
        rule = rule_loader.get_rule("mica_art36_public_offer_authorization")
        assert rule.source is not None
        assert rule.source.document_id == "mica_2023"
        assert rule.source.article == "36(1)"

    def test_rule_has_tags(self, rule_loader: RuleLoader):
        rule = rule_loader.get_rule("mica_art36_public_offer_authorization")
        assert "mica" in rule.tags
        assert "authorization" in rule.tags

    def test_rule_has_effective_date(self, rule_loader: RuleLoader):
        rule = rule_loader.get_rule("mica_art36_public_offer_authorization")
        assert rule.effective_from == date(2024, 6, 30)


class TestDecisionEngine:
    def test_evaluate_not_authorized(self, decision_engine: DecisionEngine):
        scenario = Scenario(
            instrument_type="art",
            activity="public_offer",
            jurisdiction="EU",
            authorized=False,
            is_credit_institution=False,
        )
        result = decision_engine.evaluate(scenario, "mica_art36_public_offer_authorization")

        assert result.applicable is True
        assert result.decision == "not_authorized"
        assert len(result.obligations) >= 1

    def test_evaluate_authorized(self, decision_engine: DecisionEngine):
        scenario = Scenario(
            instrument_type="art",
            activity="public_offer",
            jurisdiction="EU",
            authorized=True,
            is_credit_institution=False,
        )
        result = decision_engine.evaluate(scenario, "mica_art36_public_offer_authorization")

        assert result.applicable is True
        assert result.decision == "authorized"
        assert len(result.obligations) == 0

    def test_evaluate_credit_institution_exempt(self, decision_engine: DecisionEngine):
        scenario = Scenario(
            instrument_type="art",
            activity="public_offer",
            jurisdiction="EU",
            authorized=False,
            is_credit_institution=True,
        )
        result = decision_engine.evaluate(scenario, "mica_art36_public_offer_authorization")

        assert result.applicable is True
        assert result.decision == "exempt"

    def test_evaluate_not_applicable_wrong_jurisdiction(self, decision_engine: DecisionEngine):
        scenario = Scenario(
            instrument_type="art",
            activity="public_offer",
            jurisdiction="US",
            authorized=False,
        )
        result = decision_engine.evaluate(scenario, "mica_art36_public_offer_authorization")

        assert result.applicable is False
        assert result.decision == "not_applicable"

    def test_evaluate_not_applicable_wrong_activity(self, decision_engine: DecisionEngine):
        scenario = Scenario(
            instrument_type="art",
            activity="custody",
            jurisdiction="EU",
            authorized=False,
        )
        result = decision_engine.evaluate(scenario, "mica_art36_public_offer_authorization")

        assert result.applicable is False

    def test_trace_contains_steps(self, decision_engine: DecisionEngine):
        scenario = Scenario(
            instrument_type="art",
            activity="public_offer",
            jurisdiction="EU",
            authorized=False,
            is_credit_institution=False,
        )
        result = decision_engine.evaluate(scenario, "mica_art36_public_offer_authorization")

        assert len(result.trace) > 0
        # Should have applicability checks + decision tree checks
        assert any("instrument_type" in step.condition for step in result.trace)

    def test_evaluate_all_applicable_rules(self, decision_engine: DecisionEngine):
        scenario = Scenario(
            instrument_type="art",
            activity="public_offer",
            jurisdiction="EU",
            authorized=False,
            is_credit_institution=False,
            has_reserve=True,
            reserve_custodian_authorized=True,
        )
        results = decision_engine.evaluate_all(scenario)

        # Should match multiple rules
        assert len(results) >= 1
        rule_ids = [r.rule_id for r in results]
        assert "mica_art36_public_offer_authorization" in rule_ids

    def test_evaluate_unknown_rule(self, decision_engine: DecisionEngine):
        scenario = Scenario(instrument_type="art")
        result = decision_engine.evaluate(scenario, "nonexistent_rule")

        assert result.applicable is False
        assert result.decision == "rule_not_found"

    def test_obligation_has_source(self, decision_engine: DecisionEngine):
        scenario = Scenario(
            instrument_type="art",
            activity="public_offer",
            jurisdiction="EU",
            authorized=False,
            is_credit_institution=False,
        )
        result = decision_engine.evaluate(scenario, "mica_art36_public_offer_authorization")

        assert len(result.obligations) > 0
        obl = result.obligations[0]
        assert obl.source is not None
        assert "mica" in obl.source.lower() or "MiCA" in obl.source


class TestConditionEvaluation:
    def test_equals_operator(self, decision_engine: DecisionEngine):
        scenario = Scenario(instrument_type="art")
        flat = scenario.to_flat_dict()

        cond = ConditionSpec(field="instrument_type", operator="==", value="art")
        result, _ = decision_engine._evaluate_condition(cond, flat, "test")
        assert result is True

    def test_in_operator(self, decision_engine: DecisionEngine):
        scenario = Scenario(instrument_type="art")
        flat = scenario.to_flat_dict()

        cond = ConditionSpec(field="instrument_type", operator="in", value=["art", "emt"])
        result, _ = decision_engine._evaluate_condition(cond, flat, "test")
        assert result is True

        cond = ConditionSpec(field="instrument_type", operator="in", value=["emt", "nft"])
        result, _ = decision_engine._evaluate_condition(cond, flat, "test")
        assert result is False

    def test_exists_operator(self, decision_engine: DecisionEngine):
        scenario = Scenario(instrument_type="art", authorized=None)
        flat = scenario.to_flat_dict()

        cond = ConditionSpec(field="instrument_type", operator="exists", value=True)
        result, _ = decision_engine._evaluate_condition(cond, flat, "test")
        assert result is True

        cond = ConditionSpec(field="authorized", operator="exists", value=True)
        result, _ = decision_engine._evaluate_condition(cond, flat, "test")
        assert result is False
