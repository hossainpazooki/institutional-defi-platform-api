"""Runtime executor for compiled rule IR.

Provides efficient O(1) rule lookup and linear condition evaluation.

From Workbench storage/retrieval/runtime/executor.py.
"""

from __future__ import annotations

from typing import Any

from .cache import IRCache, get_ir_cache
from .premise_index import PremiseIndexBuilder
from .schemas import CompiledCheck, DecisionEntry, RuleIR
from .trace import DecisionResult, ExecutionTrace


# Operator implementations
def _eval_eq(actual: Any, expected: Any) -> bool:
    return bool(actual == expected)


def _eval_ne(actual: Any, expected: Any) -> bool:
    return bool(actual != expected)


def _eval_in(actual: Any, expected: Any, value_set: set[str] | None = None) -> bool:
    if value_set is not None:
        return str(actual) in value_set
    if isinstance(expected, (list, tuple, set)):
        return actual in expected
    return False


def _eval_not_in(actual: Any, expected: Any, value_set: set[str] | None = None) -> bool:
    return not _eval_in(actual, expected, value_set)


def _eval_gt(actual: Any, expected: Any) -> bool:
    try:
        return bool(actual > expected)
    except TypeError:
        return False


def _eval_lt(actual: Any, expected: Any) -> bool:
    try:
        return bool(actual < expected)
    except TypeError:
        return False


def _eval_gte(actual: Any, expected: Any) -> bool:
    try:
        return bool(actual >= expected)
    except TypeError:
        return False


def _eval_lte(actual: Any, expected: Any) -> bool:
    try:
        return bool(actual <= expected)
    except TypeError:
        return False


def _eval_exists(actual: Any, expected: Any) -> bool:
    return actual is not None


OPERATORS = {
    "eq": _eval_eq,
    "ne": _eval_ne,
    "in": _eval_in,
    "not_in": _eval_not_in,
    "gt": _eval_gt,
    "lt": _eval_lt,
    "gte": _eval_gte,
    "lte": _eval_lte,
    "exists": _eval_exists,
}


class RuleRuntime:
    """Runtime executor for compiled rules.

    Provides efficient rule evaluation using:
    - O(1) rule lookup via premise index
    - Linear condition evaluation (no tree traversal)
    - In-memory IR caching
    """

    def __init__(
        self,
        cache: IRCache | None = None,
        premise_index: PremiseIndexBuilder | None = None,
    ) -> None:
        self._cache = cache or get_ir_cache()
        self._premise_index = premise_index or PremiseIndexBuilder()

    def load_ir(self, rule_id: str, ir_json: str | None = None) -> RuleIR | None:
        """Load a rule IR, using cache if available."""
        ir = self._cache.get(rule_id)
        if ir is not None:
            return ir

        if ir_json:
            ir = RuleIR.from_json(ir_json)
            self._cache.put(rule_id, ir)
            return ir

        return None

    def find_applicable_rules(self, facts: dict[str, Any]) -> set[str]:
        """Find all rules that might apply to given facts via premise index."""
        return self._premise_index.lookup(facts)

    def check_applicability(
        self,
        ir: RuleIR,
        facts: dict[str, Any],
        trace: ExecutionTrace | None = None,
    ) -> bool:
        """Check if a rule is applicable to given facts."""
        if not ir.applicability_checks:
            return True

        mode = ir.applicability_mode
        results: list[bool] = []

        for check in ir.applicability_checks:
            result = self._evaluate_check(check, facts)
            results.append(result)

            if trace:
                trace.add_applicability_step(
                    node_id=f"applicability_{check.index}",
                    description=f"Check {check.field} {check.op} {check.value}",
                    field=check.field,
                    operator=check.op,
                    expected_value=check.value,
                    actual_value=facts.get(check.field),
                    result=result,
                )

            if mode == "all" and not result:
                return False
            if mode == "any" and result:
                return True

        if mode == "all":
            return all(results)
        else:
            return any(results)

    def evaluate_decision_table(
        self,
        ir: RuleIR,
        facts: dict[str, Any],
        trace: ExecutionTrace | None = None,
    ) -> DecisionEntry | None:
        """Evaluate decision checks and find matching table entry."""
        if not ir.decision_table:
            return None

        check_results: list[bool] = []
        for check in ir.decision_checks:
            result = self._evaluate_check(check, facts)
            check_results.append(result)

            if trace:
                trace.add_decision_step(
                    node_id=f"decision_{check.index}",
                    description=f"Check {check.field} {check.op} {check.value}",
                    field=check.field,
                    operator=check.op,
                    expected_value=check.value,
                    actual_value=facts.get(check.field),
                    result=result,
                )

        for entry in ir.decision_table:
            if self._matches_mask(check_results, entry.condition_mask):
                if trace:
                    trace.add_decision_step(
                        node_id=f"entry_{entry.entry_id}",
                        description=f"Matched entry: {entry.result}",
                        result=True,
                        source_ref=entry.source_ref,
                    )
                    trace.entry_matched = entry.entry_id
                return entry

        return None

    def infer(
        self,
        ir: RuleIR,
        facts: dict[str, Any],
        include_trace: bool = True,
    ) -> DecisionResult:
        """Execute a compiled rule IR against facts."""
        trace = ExecutionTrace(rule_id=ir.rule_id) if include_trace else None

        if trace:
            trace.facts_used = {
                k: v
                for k, v in facts.items()
                if any(c.field == k for c in ir.applicability_checks + ir.decision_checks)
            }

        applicable = self.check_applicability(ir, facts, trace)

        if trace:
            trace.applicable = applicable

        if not applicable:
            if trace:
                trace.complete()
            return DecisionResult.not_applicable(ir.rule_id, trace)

        entry = self.evaluate_decision_table(ir, facts, trace)

        if entry is None:
            if trace:
                trace.complete()
            return DecisionResult.not_applicable(ir.rule_id, trace)

        obligations = [{"id": o.id, "description": o.description, "deadline": o.deadline} for o in entry.obligations]

        if trace:
            trace.obligations = obligations
            trace.complete(entry.result)

        return DecisionResult.with_decision(
            rule_id=ir.rule_id,
            decision=entry.result,
            obligations=obligations,
            trace=trace,
        )

    def evaluate(
        self,
        rule_id: str,
        facts: dict[str, Any],
        ir_json: str | None = None,
        include_trace: bool = True,
    ) -> DecisionResult | None:
        """Evaluate a rule by ID. Convenience method that handles IR loading."""
        ir = self.load_ir(rule_id, ir_json)
        if ir is None:
            return None
        return self.infer(ir, facts, include_trace)

    def evaluate_all(
        self,
        facts: dict[str, Any],
        rule_irs: list[RuleIR] | None = None,
        include_trace: bool = True,
    ) -> list[DecisionResult]:
        """Evaluate all applicable rules against facts."""
        results = []

        if rule_irs:
            for ir in rule_irs:
                result = self.infer(ir, facts, include_trace)
                if result.applicable:
                    results.append(result)
        else:
            candidates = self.find_applicable_rules(facts)
            for rule_id in candidates:
                cached_ir = self._cache.get(rule_id)
                if cached_ir:
                    result = self.infer(cached_ir, facts, include_trace)
                    if result.applicable:
                        results.append(result)

        return results

    def _evaluate_check(self, check: CompiledCheck, facts: dict[str, Any]) -> bool:
        """Evaluate a single check against facts."""
        actual = facts.get(check.field)
        op_func = OPERATORS.get(check.op, _eval_eq)

        if check.op in ("in", "not_in"):
            return bool(op_func(actual, check.value, check.value_set))  # type: ignore[operator]
        return bool(op_func(actual, check.value))  # type: ignore[operator]

    def _matches_mask(
        self,
        check_results: list[bool],
        mask: list[int],
    ) -> bool:
        """Check if evaluation results match a condition mask."""
        for _i, requirement in enumerate(mask):
            if requirement == 0:
                continue

            check_idx = abs(requirement) - 1

            if check_idx >= len(check_results):
                continue

            required_value = requirement > 0
            if check_results[check_idx] != required_value:
                return False

        return True


def execute_rule(
    ir: RuleIR,
    facts: dict[str, Any],
    include_trace: bool = True,
) -> DecisionResult:
    """Convenience function to execute a single rule."""
    runtime = RuleRuntime()
    return runtime.infer(ir, facts, include_trace)
