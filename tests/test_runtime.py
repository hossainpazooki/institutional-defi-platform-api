"""
Tests for the runtime layer.

Tests IR execution, caching, and tracing.
"""

from pathlib import Path

from src.production import (
    CompiledCheck,
    DecisionEntry,
    DecisionResult,
    ExecutionTrace,
    IRCache,
    ObligationSpec,
    PremiseIndexBuilder,
    RuleIR,
    RuleRuntime,
    compile_rule,
    get_ir_cache,
    reset_ir_cache,
)
from src.rules import (
    ConditionGroupSpec,
    ConditionSpec,
    DecisionLeaf,
    DecisionNode,
    Rule,
    RuleLoader,
)
from src.rules import (
    ObligationSpec as RuleObligationSpec,
)


class TestExecutionTrace:
    """Test execution tracing."""

    def test_create_trace(self):
        """Test creating an execution trace."""
        trace = ExecutionTrace(rule_id="test_rule")
        assert trace.rule_id == "test_rule"
        assert trace.applicable is False
        assert trace.decision is None
        assert len(trace.applicability_steps) == 0

    def test_add_steps(self):
        """Test adding steps to trace."""
        trace = ExecutionTrace(rule_id="test_rule")

        trace.add_applicability_step(
            node_id="check_0",
            description="Check type == art",
            field="type",
            operator="eq",
            expected_value="art",
            actual_value="art",
            result=True,
        )

        assert len(trace.applicability_steps) == 1
        assert trace.applicability_steps[0].result is True

        trace.add_decision_step(
            node_id="decision_0",
            description="Check authorized",
            field="authorized",
            operator="eq",
            expected_value=True,
            actual_value=True,
            result=True,
        )

        assert len(trace.decision_steps) == 1

    def test_complete_trace(self):
        """Test completing a trace."""
        trace = ExecutionTrace(rule_id="test_rule")
        trace.complete("authorized")

        assert trace.decision == "authorized"
        assert trace.completed_at is not None

    def test_legacy_format(self):
        """Test conversion to legacy format."""
        trace = ExecutionTrace(rule_id="test_rule")
        trace.add_applicability_step(node_id="app_0", description="App check", result=True)
        trace.add_decision_step(node_id="dec_0", description="Dec check", result=True)

        legacy = trace.to_legacy_trace()
        assert len(legacy) == 2
        assert legacy[0]["node_id"] == "app_0"
        assert legacy[1]["node_id"] == "dec_0"


class TestDecisionResult:
    """Test decision result creation."""

    def test_not_applicable(self):
        """Test creating not-applicable result."""
        result = DecisionResult.not_applicable("test_rule")
        assert result.rule_id == "test_rule"
        assert result.applicable is False
        assert result.decision is None

    def test_with_decision(self):
        """Test creating result with decision."""
        result = DecisionResult.with_decision(
            rule_id="test_rule",
            decision="authorized",
            obligations=[{"id": "obl_1"}],
        )
        assert result.applicable is True
        assert result.decision == "authorized"
        assert len(result.obligations) == 1


class TestIRCache:
    """Test IR caching."""

    def test_cache_put_get(self):
        """Test basic cache put/get."""
        cache = IRCache()
        ir = RuleIR(rule_id="test_rule")

        cache.put("test_rule", ir)
        retrieved = cache.get("test_rule")

        assert retrieved is not None
        assert retrieved.rule_id == "test_rule"

    def test_cache_miss(self):
        """Test cache miss."""
        cache = IRCache()
        result = cache.get("nonexistent")
        assert result is None

    def test_cache_invalidate(self):
        """Test cache invalidation."""
        cache = IRCache()
        ir = RuleIR(rule_id="test_rule")

        cache.put("test_rule", ir)
        assert cache.contains("test_rule")

        cache.invalidate("test_rule")
        assert not cache.contains("test_rule")

    def test_cache_stats(self):
        """Test cache statistics."""
        cache = IRCache()
        ir = RuleIR(rule_id="test_rule")

        cache.put("test_rule", ir)
        cache.get("test_rule")  # Hit
        cache.get("test_rule")  # Hit
        cache.get("missing")  # Miss

        stats = cache.get_stats()
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["size"] == 1

    def test_cache_eviction(self):
        """Test cache eviction when full."""
        cache = IRCache(max_size=3)

        for i in range(5):
            cache.put(f"rule_{i}", RuleIR(rule_id=f"rule_{i}"))

        # Should have evicted some entries
        assert cache.get_stats()["size"] <= 3

    def test_get_or_load(self):
        """Test get_or_load with loader function."""
        cache = IRCache()

        def loader(rule_id: str) -> RuleIR:
            return RuleIR(rule_id=rule_id)

        # First call loads
        ir1 = cache.get_or_load("test_rule", loader)
        assert ir1 is not None
        assert cache.get_stats()["misses"] == 1

        # Second call uses cache
        ir2 = cache.get_or_load("test_rule", loader)
        assert ir2 is ir1
        assert cache.get_stats()["hits"] == 1

    def test_global_cache(self):
        """Test global cache singleton."""
        reset_ir_cache()
        cache1 = get_ir_cache()
        cache2 = get_ir_cache()
        assert cache1 is cache2


class TestRuleRuntime:
    """Test rule runtime execution."""

    def test_evaluate_simple_check(self):
        """Test evaluating simple equality check."""
        ir = RuleIR(
            rule_id="simple_test",
            applicability_checks=[CompiledCheck(index=0, field="type", op="eq", value="art")],
            decision_table=[DecisionEntry(entry_id=0, condition_mask=[], result="allowed")],
        )

        runtime = RuleRuntime()
        result = runtime.infer(ir, {"type": "art"})

        assert result.applicable is True
        assert result.decision == "allowed"

    def test_evaluate_not_applicable(self):
        """Test when rule is not applicable."""
        ir = RuleIR(
            rule_id="not_applicable_test",
            applicability_checks=[CompiledCheck(index=0, field="type", op="eq", value="art")],
            decision_table=[DecisionEntry(entry_id=0, condition_mask=[], result="allowed")],
        )

        runtime = RuleRuntime()
        result = runtime.infer(ir, {"type": "emt"})

        assert result.applicable is False
        assert result.decision is None

    def test_evaluate_in_operator(self):
        """Test 'in' operator with value set."""
        ir = RuleIR(
            rule_id="in_test",
            applicability_checks=[
                CompiledCheck(
                    index=0,
                    field="type",
                    op="in",
                    value=["art", "emt"],
                    value_set={"art", "emt"},
                )
            ],
            decision_table=[DecisionEntry(entry_id=0, condition_mask=[], result="allowed")],
        )

        runtime = RuleRuntime()

        result1 = runtime.infer(ir, {"type": "art"})
        assert result1.applicable is True

        result2 = runtime.infer(ir, {"type": "stablecoin"})
        assert result2.applicable is False

    def test_evaluate_decision_table(self):
        """Test decision table evaluation."""
        ir = RuleIR(
            rule_id="decision_test",
            applicability_checks=[],
            decision_checks=[CompiledCheck(index=0, field="authorized", op="eq", value=True)],
            decision_table=[
                DecisionEntry(
                    entry_id=0,
                    condition_mask=[1],  # authorized must be True
                    result="allowed",
                ),
                DecisionEntry(
                    entry_id=1,
                    condition_mask=[-1],  # authorized must be False
                    result="denied",
                    obligations=[ObligationSpec(id="get_auth", description="Get authorization")],
                ),
            ],
        )

        runtime = RuleRuntime()

        result1 = runtime.infer(ir, {"authorized": True})
        assert result1.decision == "allowed"

        result2 = runtime.infer(ir, {"authorized": False})
        assert result2.decision == "denied"
        assert len(result2.obligations) == 1
        assert result2.obligations[0]["id"] == "get_auth"

    def test_trace_generation(self):
        """Test that traces are generated correctly."""
        ir = RuleIR(
            rule_id="trace_test",
            applicability_checks=[CompiledCheck(index=0, field="type", op="eq", value="art")],
            decision_checks=[CompiledCheck(index=0, field="authorized", op="eq", value=True)],
            decision_table=[
                DecisionEntry(entry_id=0, condition_mask=[1], result="allowed"),
            ],
        )

        runtime = RuleRuntime()
        result = runtime.infer(ir, {"type": "art", "authorized": True}, include_trace=True)

        assert result.trace is not None
        assert len(result.trace.applicability_steps) == 1
        assert len(result.trace.decision_steps) >= 1
        assert result.trace.applicable is True
        assert result.trace.decision == "allowed"

    def test_all_operator(self):
        """Test AND (all) mode for applicability."""
        ir = RuleIR(
            rule_id="all_test",
            applicability_mode="all",
            applicability_checks=[
                CompiledCheck(index=0, field="a", op="eq", value=True),
                CompiledCheck(index=1, field="b", op="eq", value=True),
            ],
            decision_table=[DecisionEntry(entry_id=0, condition_mask=[], result="ok")],
        )

        runtime = RuleRuntime()

        # Both true = applicable
        result1 = runtime.infer(ir, {"a": True, "b": True})
        assert result1.applicable is True

        # One false = not applicable
        result2 = runtime.infer(ir, {"a": True, "b": False})
        assert result2.applicable is False

    def test_any_operator(self):
        """Test OR (any) mode for applicability."""
        ir = RuleIR(
            rule_id="any_test",
            applicability_mode="any",
            applicability_checks=[
                CompiledCheck(index=0, field="a", op="eq", value=True),
                CompiledCheck(index=1, field="b", op="eq", value=True),
            ],
            decision_table=[DecisionEntry(entry_id=0, condition_mask=[], result="ok")],
        )

        runtime = RuleRuntime()

        # One true = applicable
        result1 = runtime.infer(ir, {"a": True, "b": False})
        assert result1.applicable is True

        # Both false = not applicable
        result2 = runtime.infer(ir, {"a": False, "b": False})
        assert result2.applicable is False

    def test_comparison_operators(self):
        """Test all comparison operators."""
        facts = {"value": 10}

        runtime = RuleRuntime()

        # Greater than
        ir_gt = RuleIR(
            rule_id="gt_test",
            applicability_checks=[CompiledCheck(index=0, field="value", op="gt", value=5)],
            decision_table=[DecisionEntry(entry_id=0, condition_mask=[], result="ok")],
        )
        assert runtime.infer(ir_gt, facts).applicable is True

        # Less than
        ir_lt = RuleIR(
            rule_id="lt_test",
            applicability_checks=[CompiledCheck(index=0, field="value", op="lt", value=20)],
            decision_table=[DecisionEntry(entry_id=0, condition_mask=[], result="ok")],
        )
        assert runtime.infer(ir_lt, facts).applicable is True

        # Greater than or equal
        ir_gte = RuleIR(
            rule_id="gte_test",
            applicability_checks=[CompiledCheck(index=0, field="value", op="gte", value=10)],
            decision_table=[DecisionEntry(entry_id=0, condition_mask=[], result="ok")],
        )
        assert runtime.infer(ir_gte, facts).applicable is True

        # Not equal
        ir_ne = RuleIR(
            rule_id="ne_test",
            applicability_checks=[CompiledCheck(index=0, field="value", op="ne", value=5)],
            decision_table=[DecisionEntry(entry_id=0, condition_mask=[], result="ok")],
        )
        assert runtime.infer(ir_ne, facts).applicable is True

    def test_exists_operator(self):
        """Test exists operator."""
        ir = RuleIR(
            rule_id="exists_test",
            applicability_checks=[CompiledCheck(index=0, field="optional_field", op="exists", value=True)],
            decision_table=[DecisionEntry(entry_id=0, condition_mask=[], result="ok")],
        )

        runtime = RuleRuntime()

        # Field exists
        result1 = runtime.infer(ir, {"optional_field": "value"})
        assert result1.applicable is True

        # Field is None
        result2 = runtime.infer(ir, {"optional_field": None})
        assert result2.applicable is False

        # Field missing
        result3 = runtime.infer(ir, {})
        assert result3.applicable is False


class TestIntegration:
    """Integration tests for runtime."""

    def test_compile_and_execute(self):
        """Test full compile-and-execute pipeline."""
        # Create rule
        rule = Rule(
            rule_id="integration_test",
            version="1",
            applies_if=ConditionGroupSpec(
                all=[
                    ConditionSpec(field="type", operator="in", value=["art", "emt"]),
                    ConditionSpec(field="jurisdiction", operator="==", value="EU"),
                ]
            ),
            decision_tree=DecisionNode(
                node_id="check_auth",
                condition=ConditionSpec(field="authorized", operator="==", value=True),
                true_branch=DecisionLeaf(result="allowed"),
                false_branch=DecisionLeaf(
                    result="denied",
                    obligations=[RuleObligationSpec(id="get_auth")],
                ),
            ),
        )

        # Compile
        ir = compile_rule(rule)

        # Execute
        runtime = RuleRuntime()

        # Test applicable + authorized
        result1 = runtime.infer(
            ir,
            {"type": "art", "jurisdiction": "EU", "authorized": True},
        )
        assert result1.applicable is True
        assert result1.decision == "allowed"

        # Test applicable + not authorized
        result2 = runtime.infer(
            ir,
            {"type": "art", "jurisdiction": "EU", "authorized": False},
        )
        assert result2.applicable is True
        assert result2.decision == "denied"
        assert len(result2.obligations) == 1

        # Test not applicable (wrong type)
        result3 = runtime.infer(
            ir,
            {"type": "stablecoin", "jurisdiction": "EU", "authorized": True},
        )
        assert result3.applicable is False

    def test_execute_real_rules(self):
        """Test executing actual YAML rules."""
        rules_dir = Path(__file__).parent.parent / "src" / "rules" / "data"
        loader = RuleLoader()
        rules = loader.load_directory(rules_dir)

        runtime = RuleRuntime()

        for rule in rules:
            ir = compile_rule(rule)

            # Execute with minimal facts
            result = runtime.infer(ir, {})

            # Should return a valid result (applicable or not)
            assert result.rule_id == rule.rule_id

    def test_premise_index_lookup(self):
        """Test using premise index for rule lookup."""
        rules = [
            Rule(
                rule_id="r1",
                version="1",
                applies_if=ConditionGroupSpec(all=[ConditionSpec(field="type", operator="==", value="art")]),
                decision_tree=DecisionLeaf(result="r1_result"),
            ),
            Rule(
                rule_id="r2",
                version="1",
                applies_if=ConditionGroupSpec(all=[ConditionSpec(field="type", operator="==", value="emt")]),
                decision_tree=DecisionLeaf(result="r2_result"),
            ),
        ]

        # Compile rules
        compiled = [compile_rule(r) for r in rules]

        # Build index
        index = PremiseIndexBuilder()
        index.build(compiled)

        # Create runtime with index
        runtime = RuleRuntime(premise_index=index)

        # Cache compiled rules
        for ir in compiled:
            runtime._cache.put(ir.rule_id, ir)

        # Lookup and execute
        candidates = runtime.find_applicable_rules({"type": "art"})
        assert "r1" in candidates
        assert "r2" not in candidates

    def test_json_roundtrip(self):
        """Test IR JSON serialization/deserialization."""
        rule = Rule(
            rule_id="json_test",
            version="1",
            applies_if=ConditionGroupSpec(all=[ConditionSpec(field="type", operator="==", value="art")]),
            decision_tree=DecisionLeaf(result="ok"),
        )

        # Compile
        ir = compile_rule(rule)

        # Serialize
        json_str = ir.to_json()

        # Load via runtime
        runtime = RuleRuntime()
        loaded_ir = runtime.load_ir("json_test", json_str)

        assert loaded_ir is not None
        assert loaded_ir.rule_id == "json_test"

        # Execute
        result = runtime.infer(loaded_ir, {"type": "art"})
        assert result.decision == "ok"
