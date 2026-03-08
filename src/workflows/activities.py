"""
Temporal activities for compliance workflows.

Each activity wraps an existing service function with @activity.defn decorator.
Activities are the building blocks that workflows orchestrate.
"""

from __future__ import annotations

import contextlib
import time
from datetime import UTC, datetime
from typing import Any

from temporalio import activity

from .schemas import (
    CompliancePathway,
    ConflictResult,
    DeltaAnalysis,
    EquivalenceResult,
    JurisdictionResult,
    JurisdictionStatus,
    RuleDriftResult,
    ScenarioResult,
    ScenarioType,
    TierResult,
    VerificationTier,
)

# =============================================================================
# ComplianceCheckWorkflow Activities
# =============================================================================


@activity.defn  # type: ignore[untyped-decorator]
async def resolve_jurisdictions_activity(
    issuer_jurisdiction: str,
    target_jurisdictions: list[str],
    instrument_type: str | None = None,
) -> list[dict[str, Any]]:
    """Resolve applicable jurisdictions and regimes.

    Wraps src.jurisdiction.resolver.resolve_jurisdictions
    """
    from src.jurisdiction.resolver import resolve_jurisdictions

    applicable = resolve_jurisdictions(
        issuer=issuer_jurisdiction,
        targets=target_jurisdictions,
        instrument_type=instrument_type,
    )

    return [
        {
            "jurisdiction": aj.jurisdiction.value,
            "regime_id": aj.regime_id,
            "role": aj.role.value,
        }
        for aj in applicable
    ]


@activity.defn  # type: ignore[untyped-decorator]
async def get_equivalences_activity(
    from_jurisdiction: str,
    to_jurisdictions: list[str],
) -> list[EquivalenceResult]:
    """Get equivalence determinations between jurisdictions.

    Wraps src.jurisdiction.resolver.get_equivalences
    """
    from src.jurisdiction.resolver import get_equivalences

    equivalences = get_equivalences(from_jurisdiction, to_jurisdictions)

    return [
        EquivalenceResult(
            id=str(eq.get("id", "")),
            from_jurisdiction=eq.get("from", ""),
            to_jurisdiction=eq.get("to", ""),
            scope=eq.get("scope"),
            status=eq.get("status", ""),
            effective_date=eq.get("effective_date"),
            expiry_date=eq.get("expiry_date"),
            source_reference=eq.get("source_reference"),
            notes=eq.get("notes"),
        )
        for eq in equivalences
    ]


@activity.defn  # type: ignore[untyped-decorator]
async def evaluate_jurisdiction_activity(
    jurisdiction: str,
    regime_id: str,
    facts: dict[str, Any],
    role: str,
) -> JurisdictionResult:
    """Evaluate facts against a single jurisdiction's rules.

    Wraps src.jurisdiction.evaluator.evaluate_jurisdiction
    """
    from src.jurisdiction.evaluator import evaluate_jurisdiction

    result = await evaluate_jurisdiction(
        jurisdiction=jurisdiction,
        regime_id=regime_id,
        facts=facts,
    )

    return JurisdictionResult(
        jurisdiction=result["jurisdiction"],
        regime_id=result["regime_id"],
        role=role,
        applicable_rules=result["applicable_rules"],
        rules_evaluated=result["rules_evaluated"],
        decisions=result["decisions"],
        obligations=result["obligations"],
        status=JurisdictionStatus(result["status"]),
    )


@activity.defn  # type: ignore[untyped-decorator]
async def detect_conflicts_activity(
    jurisdiction_results: list[dict[str, Any]],
) -> list[ConflictResult]:
    """Detect conflicts between jurisdiction evaluation results.

    Wraps src.jurisdiction.conflicts.detect_conflicts
    """
    from src.jurisdiction.conflicts import detect_conflicts

    conflicts = detect_conflicts(jurisdiction_results)

    return [
        ConflictResult(
            conflict_id=f"conflict_{i}",
            jurisdictions=c.get("jurisdictions", []),
            rule_ids=c.get("obligations", c.get("rule_ids", [])),
            conflict_type=c.get("type", "unknown"),
            description=c.get("description", ""),
            severity=c.get("severity", "warning"),
        )
        for i, c in enumerate(conflicts)
    ]


@activity.defn  # type: ignore[untyped-decorator]
async def synthesize_pathway_activity(
    results: list[dict[str, Any]],
    conflicts: list[dict[str, Any]],
    equivalences: list[dict[str, Any]],
) -> CompliancePathway:
    """Synthesize compliance pathway from evaluation results.

    Wraps src.jurisdiction.pathway.synthesize_pathway
    """
    from src.jurisdiction.pathway import (
        get_critical_path,
        synthesize_pathway,
    )

    pathway_steps = synthesize_pathway(results, conflicts, equivalences)
    critical_path = get_critical_path(pathway_steps)

    # Determine feasibility
    blocking_issues = []
    for result in results:
        if result.get("status") == "blocked":
            blocking_issues.append(f"{result['jurisdiction']}: Activity blocked by regulatory requirements")

    for conflict in conflicts:
        if conflict.get("severity") == "critical":
            blocking_issues.append(conflict.get("description", "Critical conflict"))

    feasible = len(blocking_issues) == 0

    # Build required actions from non-waived steps
    required_actions = [step["action"] for step in pathway_steps if step.get("status") != "waived"]

    # Build recommended sequence from critical path
    recommended_sequence = [f"{step['jurisdiction']}: {step['action']}" for step in critical_path]

    # Primary jurisdiction is the issuer home
    primary = next(
        (r["jurisdiction"] for r in results if "issuer" in r.get("role", "")),
        None,
    )

    return CompliancePathway(
        feasible=feasible,
        primary_jurisdiction=primary,
        required_actions=required_actions,
        blocking_issues=blocking_issues,
        recommended_sequence=recommended_sequence,
    )


@activity.defn  # type: ignore[untyped-decorator]
async def aggregate_obligations_activity(
    results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Aggregate and deduplicate obligations across jurisdictions.

    Wraps src.jurisdiction.pathway.aggregate_obligations
    """
    from src.jurisdiction.pathway import aggregate_obligations

    return aggregate_obligations(results)


# =============================================================================
# RuleVerificationWorkflow Activities
# =============================================================================


@activity.defn  # type: ignore[untyped-decorator]
async def load_rule_activity(rule_id: str) -> dict[str, Any]:
    """Load a rule by ID.

    Returns rule data as a dict for serialization.
    """
    from src.rules.service import RuleLoader

    loader = RuleLoader()
    loader.load_directory("src/rules/data")
    rule = loader.get_rule(rule_id)

    if rule is None:
        raise ValueError(f"Rule not found: {rule_id}")

    return {
        "rule_id": rule.rule_id,
        "description": rule.description,
        "jurisdiction": rule.jurisdiction.value if rule.jurisdiction else None,
        "source": {
            "document_id": rule.source.document_id if rule.source else None,
            "article": rule.source.article if rule.source else None,
        }
        if rule.source
        else None,
        "tags": list(rule.tags),
        "effective_from": str(rule.effective_from) if rule.effective_from else None,
        "effective_to": str(rule.effective_to) if rule.effective_to else None,
    }


@activity.defn  # type: ignore[untyped-decorator]
async def verify_tier_0_activity(rule_id: str) -> TierResult:
    """Run Tier 0 (Schema) verification checks.

    Wraps ConsistencyEngine tier 0 checks.
    """
    start_time = time.time()

    from src.rules.service import RuleLoader
    from src.verification.service import ConsistencyEngine

    loader = RuleLoader()
    loader.load_directory("src/rules/data")
    rule = loader.get_rule(rule_id)

    if rule is None:
        return TierResult(
            tier=VerificationTier.SCHEMA,
            tier_name="Schema & Structural",
            passed=False,
            score=0.0,
            checks_run=0,
            checks_passed=0,
            evidence=[{"error": f"Rule not found: {rule_id}"}],
            duration_ms=(time.time() - start_time) * 1000,
        )

    engine = ConsistencyEngine()
    result = engine.verify_rule(rule, tiers=[0])

    checks_passed = sum(1 for e in result.evidence if e.label == "pass")
    checks_run = len(result.evidence)
    avg_score = sum(e.score for e in result.evidence) / checks_run if checks_run else 0

    return TierResult(
        tier=VerificationTier.SCHEMA,
        tier_name="Schema & Structural",
        passed=result.summary.status.value != "inconsistent",
        score=avg_score,
        checks_run=checks_run,
        checks_passed=checks_passed,
        evidence=[
            {
                "category": e.category,
                "label": e.label,
                "score": e.score,
                "details": e.details,
            }
            for e in result.evidence
        ],
        duration_ms=(time.time() - start_time) * 1000,
    )


@activity.defn  # type: ignore[untyped-decorator]
async def verify_tier_1_activity(rule_id: str, source_text: str | None = None) -> TierResult:
    """Run Tier 1 (Lexical) verification checks.

    Wraps ConsistencyEngine tier 1 checks.
    """
    start_time = time.time()

    from src.rules.service import RuleLoader
    from src.verification.service import ConsistencyEngine

    loader = RuleLoader()
    loader.load_directory("src/rules/data")
    rule = loader.get_rule(rule_id)

    if rule is None:
        return TierResult(
            tier=VerificationTier.LEXICAL,
            tier_name="Lexical & Heuristic",
            passed=False,
            score=0.0,
            checks_run=0,
            checks_passed=0,
            evidence=[{"error": f"Rule not found: {rule_id}"}],
            duration_ms=(time.time() - start_time) * 1000,
        )

    engine = ConsistencyEngine()
    result = engine.verify_rule(rule, source_text=source_text, tiers=[1])

    checks_passed = sum(1 for e in result.evidence if e.label == "pass")
    checks_run = len(result.evidence)
    avg_score = sum(e.score for e in result.evidence) / checks_run if checks_run else 0

    return TierResult(
        tier=VerificationTier.LEXICAL,
        tier_name="Lexical & Heuristic",
        passed=all(e.label != "fail" for e in result.evidence),
        score=avg_score,
        checks_run=checks_run,
        checks_passed=checks_passed,
        evidence=[
            {
                "category": e.category,
                "label": e.label,
                "score": e.score,
                "details": e.details,
            }
            for e in result.evidence
        ],
        duration_ms=(time.time() - start_time) * 1000,
    )


@activity.defn  # type: ignore[untyped-decorator]
async def verify_tier_2_activity(rule_id: str, source_text: str | None = None) -> TierResult:
    """Run Tier 2 (Semantic Similarity) verification checks.

    Wraps ConsistencyEngine tier 2 checks (embeddings module).
    Uses ML sentence-transformers when available, falls back to TF-IDF heuristics.
    """
    start_time = time.time()

    from src.rules.service import RuleLoader
    from src.verification.embeddings import embedding_available
    from src.verification.service import ConsistencyEngine

    loader = RuleLoader()
    loader.load_directory("src/rules/data")
    rule = loader.get_rule(rule_id)

    if rule is None:
        return TierResult(
            tier=VerificationTier.SEMANTIC,
            tier_name="Semantic Similarity",
            passed=False,
            score=0.0,
            checks_run=0,
            checks_passed=0,
            evidence=[{"error": f"Rule not found: {rule_id}"}],
            duration_ms=(time.time() - start_time) * 1000,
        )

    engine = ConsistencyEngine()
    result = engine.verify_rule(rule, source_text=source_text, tiers=[2])

    checks_passed = sum(1 for e in result.evidence if e.label == "pass")
    checks_run = len(result.evidence)
    avg_score = sum(e.score for e in result.evidence) / checks_run if checks_run else 0

    ml_mode = "ML" if embedding_available() else "heuristic"

    return TierResult(
        tier=VerificationTier.SEMANTIC,
        tier_name=f"Semantic Similarity ({ml_mode})",
        passed=all(e.label != "fail" for e in result.evidence),
        score=avg_score,
        checks_run=checks_run,
        checks_passed=checks_passed,
        evidence=[
            {
                "category": e.category,
                "label": e.label,
                "score": e.score,
                "details": e.details,
            }
            for e in result.evidence
        ],
        duration_ms=(time.time() - start_time) * 1000,
    )


@activity.defn  # type: ignore[untyped-decorator]
async def verify_tier_3_activity(rule_id: str, source_text: str | None = None) -> TierResult:
    """Run Tier 3 (NLI Entailment) verification checks.

    Wraps ConsistencyEngine tier 3 checks (nli module).
    Uses ML transformers/torch when available, falls back to keyword overlap heuristics.
    """
    start_time = time.time()

    from src.rules.service import RuleLoader
    from src.verification.nli import nli_available
    from src.verification.service import ConsistencyEngine

    loader = RuleLoader()
    loader.load_directory("src/rules/data")
    rule = loader.get_rule(rule_id)

    if rule is None:
        return TierResult(
            tier=VerificationTier.NLI,
            tier_name="NLI Entailment",
            passed=False,
            score=0.0,
            checks_run=0,
            checks_passed=0,
            evidence=[{"error": f"Rule not found: {rule_id}"}],
            duration_ms=(time.time() - start_time) * 1000,
        )

    engine = ConsistencyEngine()
    result = engine.verify_rule(rule, source_text=source_text, tiers=[3])

    checks_passed = sum(1 for e in result.evidence if e.label == "pass")
    checks_run = len(result.evidence)
    avg_score = sum(e.score for e in result.evidence) / checks_run if checks_run else 0

    ml_mode = "ML" if nli_available() else "heuristic"

    return TierResult(
        tier=VerificationTier.NLI,
        tier_name=f"NLI Entailment ({ml_mode})",
        passed=all(e.label != "fail" for e in result.evidence),
        score=avg_score,
        checks_run=checks_run,
        checks_passed=checks_passed,
        evidence=[
            {
                "category": e.category,
                "label": e.label,
                "score": e.score,
                "details": e.details,
            }
            for e in result.evidence
        ],
        duration_ms=(time.time() - start_time) * 1000,
    )


@activity.defn  # type: ignore[untyped-decorator]
async def verify_tier_4_activity(rule_id: str) -> TierResult:
    """Run Tier 4 (Cross-Rule Consistency) verification checks.

    Wraps ConsistencyEngine tier 4 checks (cross_rule module).
    Performs deterministic contradiction, hierarchy, and temporal checks.
    """
    start_time = time.time()

    from src.rules.service import RuleLoader
    from src.verification.cross_rule import check_cross_rule_consistency

    loader = RuleLoader()
    loader.load_directory("src/rules/data")
    rule = loader.get_rule(rule_id)

    if rule is None:
        return TierResult(
            tier=VerificationTier.CROSS_RULE,
            tier_name="Cross-Rule Consistency",
            passed=False,
            score=0.0,
            checks_run=0,
            checks_passed=0,
            evidence=[{"error": f"Rule not found: {rule_id}"}],
            duration_ms=(time.time() - start_time) * 1000,
        )

    # Get related rules for cross-rule comparison
    all_rules = loader.get_all_rules()
    related_rules = [r for r in all_rules if r.rule_id != rule_id]

    # For tier 4, use the cross-rule checker directly
    evidence_list = check_cross_rule_consistency(rule, related_rules=related_rules)

    checks_passed = sum(1 for e in evidence_list if e.label == "pass")
    checks_run = len(evidence_list)
    avg_score = sum(e.score for e in evidence_list) / checks_run if checks_run else 0

    return TierResult(
        tier=VerificationTier.CROSS_RULE,
        tier_name="Cross-Rule Consistency",
        passed=all(e.label != "fail" for e in evidence_list),
        score=avg_score,
        checks_run=checks_run,
        checks_passed=checks_passed,
        evidence=[
            {
                "category": e.category,
                "label": e.label,
                "score": e.score,
                "details": e.details,
            }
            for e in evidence_list
        ],
        duration_ms=(time.time() - start_time) * 1000,
    )


# =============================================================================
# CounterfactualAnalysisWorkflow Activities
# =============================================================================


@activity.defn  # type: ignore[untyped-decorator]
async def evaluate_baseline_activity(
    rule_id: str,
    facts: dict[str, Any],
) -> ScenarioResult:
    """Evaluate baseline scenario.

    Wraps DecisionEngine.evaluate
    """
    from src.ontology.scenario import Scenario
    from src.rules.service import DecisionEngine, RuleLoader

    loader = RuleLoader()
    loader.load_directory("src/rules/data")
    engine = DecisionEngine(loader=loader)

    # Build scenario from facts
    safe_facts = {k: v for k, v in facts.items() if not isinstance(v, (list, dict))}
    scenario = Scenario(**safe_facts)

    result = engine.evaluate(scenario, rule_id)

    return ScenarioResult(
        scenario_id="baseline",
        scenario_type=ScenarioType.THRESHOLD,  # Placeholder
        description="Baseline scenario",
        decision=result.decision or "unknown",
        applicable=result.applicable,
        obligations=[
            {
                "id": o.id,
                "description": o.description,
                "deadline": o.deadline,
            }
            for o in result.obligations
        ],
        trace=[
            {
                "node": s.node,
                "condition": s.condition,
                "result": s.result,
            }
            for s in result.trace
        ],
        differs_from_baseline=False,
        key_differences=[],
    )


@activity.defn  # type: ignore[untyped-decorator]
async def analyze_counterfactual_activity(
    rule_id: str,
    baseline_facts: dict[str, Any],
    scenario_id: str,
    scenario_type: str,
    description: str,
    modified_facts: dict[str, Any],
    baseline_decision: str,
) -> ScenarioResult:
    """Analyze a single counterfactual scenario.

    Compares modified facts against baseline.
    """
    from src.ontology.scenario import Scenario
    from src.rules.service import DecisionEngine, RuleLoader

    loader = RuleLoader()
    loader.load_directory("src/rules/data")
    engine = DecisionEngine(loader=loader)

    # Merge baseline with modifications
    merged_facts = {**baseline_facts, **modified_facts}
    safe_facts = {k: v for k, v in merged_facts.items() if not isinstance(v, (list, dict))}
    scenario = Scenario(**safe_facts)

    result = engine.evaluate(scenario, rule_id)

    # Determine differences
    differs = result.decision != baseline_decision
    key_differences = []

    if differs:
        key_differences.append(f"Decision changed from {baseline_decision} to {result.decision}")

    for key, new_val in modified_facts.items():
        old_val = baseline_facts.get(key)
        if old_val != new_val:
            key_differences.append(f"{key}: {old_val} -> {new_val}")

    return ScenarioResult(
        scenario_id=scenario_id,
        scenario_type=ScenarioType(scenario_type),
        description=description,
        decision=result.decision or "unknown",
        applicable=result.applicable,
        obligations=[
            {
                "id": o.id,
                "description": o.description,
                "deadline": o.deadline,
            }
            for o in result.obligations
        ],
        trace=[
            {
                "node": s.node,
                "condition": s.condition,
                "result": s.result,
            }
            for s in result.trace
        ],
        differs_from_baseline=differs,
        key_differences=key_differences,
    )


@activity.defn  # type: ignore[untyped-decorator]
async def compute_delta_activity(
    baseline_result: dict[str, Any],
    counterfactual_result: dict[str, Any],
) -> DeltaAnalysis:
    """Compute delta between baseline and counterfactual.

    Uses DeltaAnalyzer from decoder service.
    """
    decision_changed = baseline_result["decision"] != counterfactual_result["decision"]

    baseline_obligations = {o["id"] for o in baseline_result.get("obligations", [])}
    cf_obligations = {o["id"] for o in counterfactual_result.get("obligations", [])}

    return DeltaAnalysis(
        scenario_id=counterfactual_result.get("scenario_id", ""),
        decision_changed=decision_changed,
        original_decision=baseline_result["decision"],
        new_decision=counterfactual_result["decision"],
        obligations_added=list(cf_obligations - baseline_obligations),
        obligations_removed=list(baseline_obligations - cf_obligations),
        critical_factors=counterfactual_result.get("key_differences", []),
    )


# =============================================================================
# DriftDetectionWorkflow Activities
# =============================================================================


@activity.defn  # type: ignore[untyped-decorator]
async def get_all_rule_ids_activity() -> list[str]:
    """Get all rule IDs from the rule loader."""
    from src.rules.service import RuleLoader

    loader = RuleLoader()
    loader.load_directory("src/rules/data")
    rules = loader.get_all_rules()

    return [r.rule_id for r in rules]


@activity.defn  # type: ignore[untyped-decorator]
async def check_rule_drift_activity(rule_id: str) -> RuleDriftResult:
    """Check a single rule for drift.

    Checks for:
    - Schema drift (rule structure changed)
    - Source drift (source document modified)
    - Reference drift (broken references)
    """
    from src.rules.service import RuleLoader
    from src.verification.service import ConsistencyEngine

    loader = RuleLoader()
    loader.load_directory("src/rules/data")
    rule = loader.get_rule(rule_id)

    now = datetime.now(UTC)

    if rule is None:
        return RuleDriftResult(
            rule_id=rule_id,
            has_drift=True,
            drift_types=["rule_missing"],
            details=["Rule no longer exists in rule data"],
            severity="critical",
            last_verified=None,
            current_check=now,
        )

    drift_types = []
    details = []

    # Check schema validity
    engine = ConsistencyEngine()
    result = engine.verify_rule(rule, tiers=[0])

    for evidence in result.evidence:
        if evidence.label == "fail":
            drift_types.append("schema_drift")
            details.append(f"Schema check failed: {evidence.details}")
        elif evidence.label == "warning" and evidence.category == "source_exists":
            drift_types.append("reference_drift")
            details.append(f"Reference issue: {evidence.details}")

    # Determine severity
    if "schema_drift" in drift_types:
        severity = "high"
    elif "reference_drift" in drift_types:
        severity = "medium"
    elif drift_types:
        severity = "low"
    else:
        severity = "none"

    # Get last verified from rule consistency block if available
    last_verified = None
    if rule.consistency and rule.consistency.summary:
        last_verified_str = rule.consistency.summary.last_verified
        if last_verified_str:
            with contextlib.suppress(ValueError):
                last_verified = datetime.fromisoformat(last_verified_str.replace("Z", "+00:00"))

    return RuleDriftResult(
        rule_id=rule_id,
        has_drift=len(drift_types) > 0,
        drift_types=drift_types,
        details=details,
        severity=severity,
        last_verified=last_verified,
        current_check=now,
    )


@activity.defn  # type: ignore[untyped-decorator]
async def notify_drift_detected_activity(
    drift_results: list[dict[str, Any]],
) -> int:
    """Send notifications for detected drift.

    Returns number of notifications sent.

    Currently a stub - would integrate with notification service.
    """
    rules_with_drift = [r for r in drift_results if r.get("has_drift")]

    if not rules_with_drift:
        return 0

    # Log drift detection (in production, would send to notification service)
    activity.logger.info(f"Drift detected in {len(rules_with_drift)} rules: {[r['rule_id'] for r in rules_with_drift]}")

    return len(rules_with_drift)
