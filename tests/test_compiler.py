"""
Tests for the compiler layer.

Tests IR generation, rule compilation, premise indexing, and optimization.
"""

from pathlib import Path

from src.production import (
    CompiledCheck,
    DecisionEntry,
    ObligationSpec,
    PremiseIndexBuilder,
    RuleCompiler,
    RuleIR,
    RuleOptimizer,
    compile_rule,
    compile_rules,
    get_premise_index,
    optimize_rule,
    reset_premise_index,
)
from src.rules import (
    ConditionGroupSpec,
    ConditionSpec,
    DecisionLeaf,
    DecisionNode,
    Rule,
    RuleLoader,
    SourceRef,
)
from src.rules import (
    ObligationSpec as RuleObligationSpec,
)


class TestIRTypes:
    """Test IR type definitions."""

    def test_compiled_check_creation(self):
        """Test creating a CompiledCheck."""
        check = CompiledCheck(
            index=0,
            field="instrument_type",
            op="eq",
            value="art",
        )
        assert check.index == 0
        assert check.field == "instrument_type"
        assert check.op == "eq"
        assert check.value == "art"
        assert check.value_set is None

    def test_compiled_check_with_value_set(self):
        """Test CompiledCheck with pre-computed value set."""
        check = CompiledCheck(
            index=0,
            field="instrument_type",
            op="in",
            value=["art", "emt"],
            value_set={"art", "emt"},
        )
        assert check.value_set == {"art", "emt"}

    def test_compiled_check_serialization(self):
        """Test CompiledCheck JSON serialization."""
        check = CompiledCheck(
            index=0,
            field="test",
            op="in",
            value=["a", "b"],
            value_set={"a", "b"},
        )
        data = check.model_dump()
        assert set(data["value_set"]) == {"a", "b"}  # Converted to list (order not guaranteed)

    def test_decision_entry_creation(self):
        """Test creating a DecisionEntry."""
        entry = DecisionEntry(
            entry_id=0,
            condition_mask=[1, -2, 0],
            result="authorized",
            obligations=[ObligationSpec(id="obl_1", description="Test obligation")],
        )
        assert entry.entry_id == 0
        assert entry.condition_mask == [1, -2, 0]
        assert entry.result == "authorized"
        assert len(entry.obligations) == 1

    def test_rule_ir_creation(self):
        """Test creating a RuleIR."""
        ir = RuleIR(
            rule_id="test_rule",
            version=1,
            premise_keys=["instrument_type:art"],
            applicability_checks=[CompiledCheck(index=0, field="instrument_type", op="eq", value="art")],
            decision_table=[DecisionEntry(entry_id=0, condition_mask=[], result="authorized")],
        )
        assert ir.rule_id == "test_rule"
        assert len(ir.premise_keys) == 1
        assert len(ir.applicability_checks) == 1
        assert len(ir.decision_table) == 1

    def test_rule_ir_json_roundtrip(self):
        """Test RuleIR JSON serialization roundtrip."""
        ir = RuleIR(
            rule_id="test_rule",
            version=1,
            premise_keys=["field:value"],
            applicability_checks=[CompiledCheck(index=0, field="field", op="eq", value="value")],
            decision_table=[DecisionEntry(entry_id=0, condition_mask=[1], result="result")],
        )

        json_str = ir.to_json()
        restored = RuleIR.from_json(json_str)

        assert restored.rule_id == ir.rule_id
        assert restored.premise_keys == ir.premise_keys
        assert len(restored.applicability_checks) == 1
        assert len(restored.decision_table) == 1


class TestRuleCompiler:
    """Test rule compilation."""

    def test_compile_simple_rule(self):
        """Test compiling a simple rule."""
        rule = Rule(
            rule_id="simple_test",
            version="1.0",
            applies_if=ConditionGroupSpec(
                all=[
                    ConditionSpec(field="instrument_type", operator="==", value="art"),
                ]
            ),
            decision_tree=DecisionLeaf(result="authorized"),
        )

        compiler = RuleCompiler()
        ir = compiler.compile(rule)

        assert ir.rule_id == "simple_test"
        assert ir.version == 1
        assert "instrument_type:art" in ir.premise_keys
        assert len(ir.applicability_checks) == 1
        assert ir.applicability_checks[0].field == "instrument_type"
        assert ir.applicability_checks[0].op == "eq"

    def test_compile_rule_with_in_operator(self):
        """Test compiling a rule with 'in' operator."""
        rule = Rule(
            rule_id="in_test",
            version="1",
            applies_if=ConditionGroupSpec(
                all=[
                    ConditionSpec(
                        field="instrument_type",
                        operator="in",
                        value=["art", "emt", "stablecoin"],
                    ),
                ]
            ),
            decision_tree=DecisionLeaf(result="applicable"),
        )

        ir = compile_rule(rule)

        # 3 instrument types + jurisdiction:EU + regime:mica_2023 = 5 keys
        assert len(ir.premise_keys) == 5
        assert "instrument_type:art" in ir.premise_keys
        assert "instrument_type:emt" in ir.premise_keys
        assert "instrument_type:stablecoin" in ir.premise_keys
        assert "jurisdiction:EU" in ir.premise_keys
        assert "regime:mica_2023" in ir.premise_keys
        assert ir.applicability_checks[0].value_set == {"art", "emt", "stablecoin"}

    def test_compile_rule_with_decision_tree(self):
        """Test compiling a rule with a decision tree."""
        rule = Rule(
            rule_id="tree_test",
            version="1",
            applies_if=ConditionGroupSpec(all=[ConditionSpec(field="activity", operator="==", value="public_offer")]),
            decision_tree=DecisionNode(
                node_id="check_auth",
                condition=ConditionSpec(field="authorized", operator="==", value=True),
                true_branch=DecisionLeaf(result="authorized"),
                false_branch=DecisionLeaf(
                    result="not_authorized",
                    obligations=[RuleObligationSpec(id="get_auth", description="Get authorization")],
                ),
            ),
        )

        ir = compile_rule(rule)

        assert len(ir.decision_checks) == 1
        assert ir.decision_checks[0].field == "authorized"
        assert len(ir.decision_table) == 2

        # Check decision entries
        results = {e.result for e in ir.decision_table}
        assert "authorized" in results
        assert "not_authorized" in results

        # Check obligations on not_authorized
        not_auth = next(e for e in ir.decision_table if e.result == "not_authorized")
        assert len(not_auth.obligations) == 1
        assert not_auth.obligations[0].id == "get_auth"

    def test_compile_rule_with_nested_tree(self):
        """Test compiling a rule with nested decision tree."""
        rule = Rule(
            rule_id="nested_tree",
            version="1",
            decision_tree=DecisionNode(
                node_id="level_1",
                condition=ConditionSpec(field="a", operator="==", value=True),
                true_branch=DecisionNode(
                    node_id="level_2a",
                    condition=ConditionSpec(field="b", operator="==", value=True),
                    true_branch=DecisionLeaf(result="a_and_b"),
                    false_branch=DecisionLeaf(result="a_not_b"),
                ),
                false_branch=DecisionLeaf(result="not_a"),
            ),
        )

        ir = compile_rule(rule)

        assert len(ir.decision_checks) == 2
        assert len(ir.decision_table) == 3

        results = {e.result for e in ir.decision_table}
        assert results == {"a_and_b", "a_not_b", "not_a"}

    def test_compile_multiple_rules(self):
        """Test compiling multiple rules."""
        rules = [
            Rule(rule_id="rule_1", version="1", decision_tree=DecisionLeaf(result="r1")),
            Rule(rule_id="rule_2", version="1", decision_tree=DecisionLeaf(result="r2")),
            Rule(rule_id="rule_3", version="1", decision_tree=DecisionLeaf(result="r3")),
        ]

        compiled = compile_rules(rules)

        assert len(compiled) == 3
        assert "rule_1" in compiled
        assert "rule_2" in compiled
        assert "rule_3" in compiled

    def test_compile_real_yaml_rules(self):
        """Test compiling actual YAML rules from the project."""
        rules_dir = Path(__file__).parent.parent / "src" / "rules" / "data"
        loader = RuleLoader()
        rules = loader.load_directory(rules_dir)

        assert len(rules) > 0

        for rule in rules:
            ir = compile_rule(rule)
            assert ir.rule_id == rule.rule_id
            # Should have premise keys if applies_if is defined
            if rule.applies_if:
                assert len(ir.premise_keys) > 0


class TestPremiseIndexBuilder:
    """Test premise index building and lookup."""

    def test_build_index_from_rules(self):
        """Test building index from Rule objects."""
        rules = [
            Rule(
                rule_id="r1",
                version="1",
                applies_if=ConditionGroupSpec(all=[ConditionSpec(field="type", operator="==", value="art")]),
            ),
            Rule(
                rule_id="r2",
                version="1",
                applies_if=ConditionGroupSpec(all=[ConditionSpec(field="type", operator="==", value="art")]),
            ),
            Rule(
                rule_id="r3",
                version="1",
                applies_if=ConditionGroupSpec(all=[ConditionSpec(field="type", operator="==", value="emt")]),
            ),
        ]

        builder = PremiseIndexBuilder()
        index = builder.build(rules)

        assert "type:art" in index
        assert len(index["type:art"]) == 2
        assert "r1" in index["type:art"]
        assert "r2" in index["type:art"]

        assert "type:emt" in index
        assert "r3" in index["type:emt"]

    def test_build_index_from_ir(self):
        """Test building index from RuleIR objects."""
        irs = [
            RuleIR(rule_id="ir1", premise_keys=["field:a", "field:b"]),
            RuleIR(rule_id="ir2", premise_keys=["field:a", "field:c"]),
        ]

        builder = PremiseIndexBuilder()
        index = builder.build(irs)

        assert "field:a" in index
        assert len(index["field:a"]) == 2

    def test_lookup_facts(self):
        """Test looking up rules by facts."""
        rules = [
            Rule(
                rule_id="r1",
                version="1",
                applies_if=ConditionGroupSpec(
                    all=[
                        ConditionSpec(field="type", operator="==", value="art"),
                        ConditionSpec(field="jurisdiction", operator="==", value="EU"),
                    ]
                ),
            ),
            Rule(
                rule_id="r2",
                version="1",
                applies_if=ConditionGroupSpec(all=[ConditionSpec(field="type", operator="==", value="emt")]),
            ),
        ]

        builder = PremiseIndexBuilder()
        builder.build(rules)

        # Lookup should return rules matching any fact
        matches = builder.lookup({"type": "art"})
        assert "r1" in matches

        matches = builder.lookup({"type": "emt"})
        assert "r2" in matches

        matches = builder.lookup({"type": "unknown"})
        assert len(matches) == 0

    def test_add_and_remove_rule(self):
        """Test dynamically adding and removing rules."""
        builder = PremiseIndexBuilder()

        rule = Rule(
            rule_id="dynamic",
            version="1",
            applies_if=ConditionGroupSpec(all=[ConditionSpec(field="test", operator="==", value="value")]),
        )

        keys = builder.add_rule(rule)
        assert "test:value" in keys

        matches = builder.lookup({"test": "value"})
        assert "dynamic" in matches

        builder.remove_rule("dynamic")
        matches = builder.lookup({"test": "value"})
        assert "dynamic" not in matches

    def test_get_stats(self):
        """Test getting index statistics."""
        rules = [
            Rule(
                rule_id="r1",
                version="1",
                applies_if=ConditionGroupSpec(all=[ConditionSpec(field="a", operator="==", value="1")]),
            ),
            Rule(
                rule_id="r2",
                version="1",
                applies_if=ConditionGroupSpec(
                    all=[
                        ConditionSpec(field="a", operator="==", value="1"),
                        ConditionSpec(field="b", operator="==", value="2"),
                    ]
                ),
            ),
        ]

        builder = PremiseIndexBuilder()
        builder.build(rules)

        stats = builder.get_stats()
        assert stats["total_keys"] >= 2
        assert stats["total_rules"] == 2

    def test_global_index(self):
        """Test global premise index singleton."""
        reset_premise_index()

        index1 = get_premise_index()
        index2 = get_premise_index()

        assert index1 is index2

        reset_premise_index()
        index3 = get_premise_index()

        assert index3 is not index1


class TestRuleOptimizer:
    """Test rule optimization."""

    def test_ensure_value_sets(self):
        """Test that optimizer ensures value sets for 'in' operators."""
        ir = RuleIR(
            rule_id="test",
            applicability_checks=[CompiledCheck(index=0, field="type", op="in", value=["a", "b", "c"])],
        )

        # value_set should be None initially
        assert ir.applicability_checks[0].value_set is None

        optimizer = RuleOptimizer()
        optimized = optimizer.optimize(ir)

        assert optimized.applicability_checks[0].value_set == {"a", "b", "c"}

    def test_reorder_by_selectivity(self):
        """Test condition reordering by selectivity hints."""
        ir = RuleIR(
            rule_id="test",
            applicability_mode="all",
            applicability_checks=[
                CompiledCheck(index=0, field="active", op="eq", value=True),
                CompiledCheck(index=1, field="id", op="eq", value="123"),
                CompiledCheck(index=2, field="type", op="eq", value="art"),
            ],
        )

        optimizer = RuleOptimizer(
            selectivity_hints={
                "id": 0.01,  # Very selective
                "type": 0.1,  # Moderately selective
                "active": 0.5,  # Not very selective
            }
        )

        optimized = optimizer.optimize(ir)

        # Most selective should be first
        assert optimized.applicability_checks[0].field == "id"
        assert optimized.applicability_checks[1].field == "type"
        assert optimized.applicability_checks[2].field == "active"

    def test_analyze_ir(self):
        """Test IR analysis."""
        ir = RuleIR(
            rule_id="analysis_test",
            premise_keys=["a:1", "b:2"],
            applicability_checks=[
                CompiledCheck(index=0, field="a", op="eq", value="1"),
                CompiledCheck(index=1, field="b", op="in", value=["2", "3"]),
            ],
            decision_checks=[
                CompiledCheck(index=0, field="c", op="eq", value=True),
            ],
            decision_table=[
                DecisionEntry(entry_id=0, condition_mask=[1], result="yes"),
                DecisionEntry(entry_id=1, condition_mask=[-1], result="no"),
            ],
        )

        optimizer = RuleOptimizer()
        analysis = optimizer.analyze_ir(ir)

        assert analysis["rule_id"] == "analysis_test"
        assert analysis["applicability_check_count"] == 2
        assert analysis["decision_check_count"] == 1
        assert analysis["decision_table_size"] == 2
        assert analysis["premise_key_count"] == 2


class TestIntegration:
    """Integration tests for compiler module."""

    def test_full_compilation_pipeline(self):
        """Test full compilation from Rule to optimized IR."""
        rule = Rule(
            rule_id="full_pipeline",
            version="1",
            description="Test rule for full pipeline",
            source=SourceRef(document_id="test_doc", article="1"),
            applies_if=ConditionGroupSpec(
                all=[
                    ConditionSpec(field="type", operator="in", value=["art", "emt"]),
                    ConditionSpec(field="jurisdiction", operator="==", value="EU"),
                ]
            ),
            decision_tree=DecisionNode(
                node_id="check",
                condition=ConditionSpec(field="authorized", operator="==", value=True),
                true_branch=DecisionLeaf(result="allowed"),
                false_branch=DecisionLeaf(
                    result="denied",
                    obligations=[RuleObligationSpec(id="get_auth")],
                ),
            ),
        )

        # Compile
        compiler = RuleCompiler()
        ir = compiler.compile(rule)

        # Verify compilation
        assert ir.rule_id == "full_pipeline"
        assert ir.source_document_id == "test_doc"
        assert ir.source_article == "1"
        # type:art, type:emt, jurisdiction:EU, regime:mica_2023 = 4 keys
        assert len(ir.premise_keys) == 4
        assert "jurisdiction:EU" in ir.premise_keys
        assert "regime:mica_2023" in ir.premise_keys
        assert len(ir.applicability_checks) == 2
        assert len(ir.decision_table) == 2

        # Optimize
        optimized = optimize_rule(ir)

        # Value set should be populated
        in_check = next(c for c in optimized.applicability_checks if c.op == "in")
        assert in_check.value_set is not None

        # Index
        builder = PremiseIndexBuilder()
        builder.add_rule(optimized)

        # Lookup
        matches = builder.lookup({"type": "art", "jurisdiction": "EU"})
        assert "full_pipeline" in matches

        # Serialize and deserialize
        json_str = optimized.to_json()
        restored = RuleIR.from_json(json_str)

        assert restored.rule_id == optimized.rule_id
        assert len(restored.decision_table) == len(optimized.decision_table)
