"""
Temporal workflow definitions for compliance operations.

Workflow patterns:
- ComplianceCheckWorkflow: Fan-out/fan-in for parallel jurisdiction evaluation
- RuleVerificationWorkflow: Sequential saga with early termination
- CounterfactualAnalysisWorkflow: Baseline + parallel scenario analysis
- DriftDetectionWorkflow: Scheduled periodic execution
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from .schemas import (
        ComplianceCheckInput,
        ComplianceCheckOutput,
        ComplianceCheckProgress,
        CompliancePathway,
        CounterfactualInput,
        CounterfactualOutput,
        CounterfactualProgress,
        DeltaAnalysis,
        DriftDetectionInput,
        DriftDetectionOutput,
        DriftDetectionProgress,
        JurisdictionResult,
        JurisdictionStatus,
        RuleDriftResult,
        RuleVerificationInput,
        RuleVerificationOutput,
        RuleVerificationProgress,
        ScenarioResult,
        TierResult,
        VerificationTier,
        WorkflowStatus,
    )


# Default retry policy for activities
DEFAULT_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(minutes=1),
    maximum_attempts=3,
)

# Activity timeouts
SHORT_TIMEOUT = timedelta(seconds=30)
MEDIUM_TIMEOUT = timedelta(minutes=2)
LONG_TIMEOUT = timedelta(minutes=10)


# =============================================================================
# ComplianceCheckWorkflow
# =============================================================================


@workflow.defn
class ComplianceCheckWorkflow:
    """
    Fan-out/fan-in workflow for multi-jurisdiction compliance checks.

    Pattern:
    1. Resolve applicable jurisdictions
    2. Query equivalences (optional)
    3. Evaluate each jurisdiction in parallel (fan-out)
    4. Aggregate results (fan-in)
    5. Detect conflicts
    6. Synthesize compliance pathway

    Queries:
    - progress: Get current progress
    - result: Get current (partial) result
    """

    def __init__(self) -> None:
        self._workflow_id: str = ""
        self._status = WorkflowStatus.PENDING
        self._started_at: datetime | None = None
        self._completed_at: datetime | None = None
        self._current_phase = "initializing"
        self._total_jurisdictions = 0
        self._completed_jurisdictions = 0
        self._jurisdiction_results: list[JurisdictionResult] = []
        self._equivalences: list[dict] = []
        self._conflicts: list[dict] = []
        self._pathway: CompliancePathway | None = None
        self._obligations: list[dict] = []
        self._error: str | None = None

    @workflow.run
    async def run(self, input: ComplianceCheckInput) -> ComplianceCheckOutput:
        """Execute the compliance check workflow."""
        self._workflow_id = workflow.info().workflow_id
        self._started_at = datetime.now(UTC)
        self._status = WorkflowStatus.RUNNING

        try:
            # Phase 1: Resolve jurisdictions
            self._current_phase = "resolving"
            jurisdictions = await workflow.execute_activity(
                "resolve_jurisdictions_activity",
                args=[
                    input.issuer_jurisdiction,
                    input.target_jurisdictions,
                    input.instrument_type,
                ],
                start_to_close_timeout=SHORT_TIMEOUT,
                retry_policy=DEFAULT_RETRY_POLICY,
            )
            self._total_jurisdictions = len(jurisdictions)

            # Phase 2: Get equivalences (parallel with evaluations)
            equivalence_task = None
            if input.include_equivalences:
                equivalence_task = workflow.execute_activity(
                    "get_equivalences_activity",
                    args=[input.issuer_jurisdiction, input.target_jurisdictions],
                    start_to_close_timeout=SHORT_TIMEOUT,
                    retry_policy=DEFAULT_RETRY_POLICY,
                )

            # Phase 3: Evaluate jurisdictions in parallel (fan-out)
            self._current_phase = "evaluating"
            evaluation_tasks = [
                workflow.execute_activity(
                    "evaluate_jurisdiction_activity",
                    args=[
                        j["jurisdiction"],
                        j["regime_id"],
                        input.facts,
                        j["role"],
                    ],
                    start_to_close_timeout=MEDIUM_TIMEOUT,
                    retry_policy=DEFAULT_RETRY_POLICY,
                )
                for j in jurisdictions
            ]

            # Wait for all evaluations (fan-in)
            evaluation_results = await asyncio.gather(*evaluation_tasks)

            for result in evaluation_results:
                self._jurisdiction_results.append(result)
                self._completed_jurisdictions += 1

            # Wait for equivalences if requested
            if equivalence_task:
                self._equivalences = await equivalence_task

            # Phase 4: Detect conflicts
            if input.detect_conflicts:
                self._current_phase = "detecting_conflicts"
                # Convert JurisdictionResult to dict for activity
                results_as_dicts = [
                    {
                        "jurisdiction": r.jurisdiction,
                        "regime_id": r.regime_id,
                        "role": r.role,
                        "status": r.status.value,
                        "decisions": r.decisions,
                        "obligations": r.obligations,
                    }
                    for r in self._jurisdiction_results
                ]
                self._conflicts = await workflow.execute_activity(
                    "detect_conflicts_activity",
                    args=[results_as_dicts],
                    start_to_close_timeout=SHORT_TIMEOUT,
                    retry_policy=DEFAULT_RETRY_POLICY,
                )

            # Phase 5: Synthesize pathway
            self._current_phase = "synthesizing"
            results_as_dicts = [
                {
                    "jurisdiction": r.jurisdiction,
                    "regime_id": r.regime_id,
                    "role": r.role,
                    "status": r.status.value,
                    "decisions": r.decisions,
                    "obligations": r.obligations,
                }
                for r in self._jurisdiction_results
            ]
            equivalences_as_dicts = [
                {
                    "id": e.id if hasattr(e, "id") else e.get("id"),
                    "from": e.from_jurisdiction if hasattr(e, "from_jurisdiction") else e.get("from_jurisdiction"),
                    "to": e.to_jurisdiction if hasattr(e, "to_jurisdiction") else e.get("to_jurisdiction"),
                    "scope": e.scope if hasattr(e, "scope") else e.get("scope"),
                    "status": e.status if hasattr(e, "status") else e.get("status"),
                }
                for e in self._equivalences
            ]
            conflicts_as_dicts = [
                {
                    "conflict_id": c.conflict_id if hasattr(c, "conflict_id") else c.get("conflict_id"),
                    "jurisdictions": c.jurisdictions if hasattr(c, "jurisdictions") else c.get("jurisdictions"),
                    "description": c.description if hasattr(c, "description") else c.get("description"),
                    "severity": c.severity if hasattr(c, "severity") else c.get("severity"),
                }
                for c in self._conflicts
            ]

            self._pathway = await workflow.execute_activity(
                "synthesize_pathway_activity",
                args=[results_as_dicts, conflicts_as_dicts, equivalences_as_dicts],
                start_to_close_timeout=SHORT_TIMEOUT,
                retry_policy=DEFAULT_RETRY_POLICY,
            )

            # Phase 6: Aggregate obligations
            self._obligations = await workflow.execute_activity(
                "aggregate_obligations_activity",
                args=[results_as_dicts],
                start_to_close_timeout=SHORT_TIMEOUT,
                retry_policy=DEFAULT_RETRY_POLICY,
            )

            # Determine overall status
            overall_status = self._compute_overall_status()

            self._status = WorkflowStatus.COMPLETED
            self._completed_at = datetime.now(UTC)
            self._current_phase = "completed"

            return ComplianceCheckOutput(
                workflow_id=self._workflow_id,
                status=self._status,
                started_at=self._started_at,
                completed_at=self._completed_at,
                issuer_jurisdiction=input.issuer_jurisdiction,
                target_jurisdictions=input.target_jurisdictions,
                jurisdiction_results=self._jurisdiction_results,
                equivalences=self._equivalences,
                conflicts=self._conflicts,
                pathway=self._pathway,
                aggregated_obligations=self._obligations,
                overall_status=overall_status,
            )

        except Exception as e:
            self._status = WorkflowStatus.FAILED
            self._completed_at = datetime.now(UTC)
            self._error = str(e)

            return ComplianceCheckOutput(
                workflow_id=self._workflow_id,
                status=self._status,
                started_at=self._started_at,
                completed_at=self._completed_at,
                issuer_jurisdiction=input.issuer_jurisdiction,
                target_jurisdictions=input.target_jurisdictions,
                jurisdiction_results=self._jurisdiction_results,
                equivalences=self._equivalences,
                conflicts=self._conflicts,
                pathway=self._pathway,
                aggregated_obligations=self._obligations,
                overall_status=JurisdictionStatus.BLOCKED,
                error=self._error,
            )

    def _compute_overall_status(self) -> JurisdictionStatus:
        """Compute overall compliance status from individual results."""
        if not self._jurisdiction_results:
            return JurisdictionStatus.NO_APPLICABLE_RULES

        statuses = [r.status for r in self._jurisdiction_results]

        if JurisdictionStatus.BLOCKED in statuses:
            return JurisdictionStatus.BLOCKED
        if JurisdictionStatus.REQUIRES_ACTION in statuses:
            return JurisdictionStatus.REQUIRES_ACTION
        if all(s == JurisdictionStatus.COMPLIANT for s in statuses):
            return JurisdictionStatus.COMPLIANT
        return JurisdictionStatus.REQUIRES_ACTION

    @workflow.query
    def progress(self) -> ComplianceCheckProgress:
        """Query current workflow progress."""
        phase_progress = 0.0
        if self._total_jurisdictions > 0:
            phase_progress = self._completed_jurisdictions / self._total_jurisdictions

        return ComplianceCheckProgress(
            workflow_id=self._workflow_id,
            status=self._status,
            total_jurisdictions=self._total_jurisdictions,
            completed_jurisdictions=self._completed_jurisdictions,
            current_phase=self._current_phase,
            phase_progress=phase_progress,
        )


# =============================================================================
# RuleVerificationWorkflow
# =============================================================================


@workflow.defn
class RuleVerificationWorkflow:
    """
    Sequential saga workflow for rule verification across tiers.

    Pattern:
    1. Load rule
    2. Execute tiers 0-4 sequentially
    3. Stop early on failure (if fail_fast)
    4. Support skip signals for individual tiers

    Queries:
    - progress: Get current progress

    Signals:
    - skip_tier: Signal to skip a specific tier
    """

    def __init__(self) -> None:
        self._workflow_id: str = ""
        self._status = WorkflowStatus.PENDING
        self._started_at: datetime | None = None
        self._completed_at: datetime | None = None
        self._rule_id: str = ""
        self._current_tier: VerificationTier | None = None
        self._tier_results: list[TierResult] = []
        self._tiers_completed: list[VerificationTier] = []
        self._tiers_remaining: list[VerificationTier] = []
        self._skip_tiers: set[VerificationTier] = set()
        self._stopped_early = False
        self._stop_reason: str | None = None
        self._error: str | None = None

    @workflow.signal
    def skip_tier(self, tier: int) -> None:
        """Signal to skip a verification tier."""
        self._skip_tiers.add(VerificationTier(tier))

    @workflow.run
    async def run(self, input: RuleVerificationInput) -> RuleVerificationOutput:
        """Execute the rule verification workflow."""
        self._workflow_id = workflow.info().workflow_id
        self._started_at = datetime.now(UTC)
        self._status = WorkflowStatus.RUNNING
        self._rule_id = input.rule_id

        # Initialize skip tiers from input
        for tier in input.skip_tiers:
            self._skip_tiers.add(tier)

        # Build list of tiers to execute
        all_tiers = [
            VerificationTier.SCHEMA,
            VerificationTier.LEXICAL,
            VerificationTier.SEMANTIC,
            VerificationTier.NLI,
            VerificationTier.CROSS_RULE,
        ]
        self._tiers_remaining = [t for t in all_tiers if t.value <= input.max_tier.value and t not in self._skip_tiers]

        try:
            # Phase 1: Load rule (verify it exists)
            await workflow.execute_activity(
                "load_rule_activity",
                args=[input.rule_id],
                start_to_close_timeout=SHORT_TIMEOUT,
                retry_policy=DEFAULT_RETRY_POLICY,
            )

            # Phase 2: Execute tiers sequentially
            tier_activities = {
                VerificationTier.SCHEMA: "verify_tier_0_activity",
                VerificationTier.LEXICAL: "verify_tier_1_activity",
                VerificationTier.SEMANTIC: "verify_tier_2_activity",
                VerificationTier.NLI: "verify_tier_3_activity",
                VerificationTier.CROSS_RULE: "verify_tier_4_activity",
            }

            for tier in list(self._tiers_remaining):
                # Check if tier was signaled to skip
                if tier in self._skip_tiers:
                    self._tiers_remaining.remove(tier)
                    continue

                self._current_tier = tier
                activity_name = tier_activities[tier]

                # Execute tier verification
                # Tiers 1, 2, 3 accept source_text for semantic analysis
                if tier in (VerificationTier.LEXICAL, VerificationTier.SEMANTIC, VerificationTier.NLI):
                    result = await workflow.execute_activity(
                        activity_name,
                        args=[input.rule_id, input.source_text],
                        start_to_close_timeout=MEDIUM_TIMEOUT,
                        retry_policy=DEFAULT_RETRY_POLICY,
                    )
                else:
                    # Tiers 0 and 4 don't use source_text
                    result = await workflow.execute_activity(
                        activity_name,
                        args=[input.rule_id],
                        start_to_close_timeout=MEDIUM_TIMEOUT,
                        retry_policy=DEFAULT_RETRY_POLICY,
                    )

                self._tier_results.append(result)
                self._tiers_completed.append(tier)
                self._tiers_remaining.remove(tier)

                # Check for early termination
                if input.fail_fast and not result.passed:
                    self._stopped_early = True
                    self._stop_reason = f"Tier {tier.value} ({result.tier_name}) failed"
                    break

            # Compute final results
            highest_passed = None
            for result in reversed(self._tier_results):
                if result.passed:
                    highest_passed = result.tier
                    break

            total_score = sum(r.score for r in self._tier_results)
            avg_score = total_score / len(self._tier_results) if self._tier_results else 0.0
            overall_passed = all(r.passed for r in self._tier_results)

            self._status = WorkflowStatus.COMPLETED
            self._completed_at = datetime.now(UTC)
            self._current_tier = None

            return RuleVerificationOutput(
                workflow_id=self._workflow_id,
                status=self._status,
                started_at=self._started_at,
                completed_at=self._completed_at,
                rule_id=input.rule_id,
                tier_results=self._tier_results,
                highest_tier_passed=highest_passed,
                overall_score=avg_score,
                overall_passed=overall_passed,
                stopped_early=self._stopped_early,
                stop_reason=self._stop_reason,
            )

        except Exception as e:
            self._status = WorkflowStatus.FAILED
            self._completed_at = datetime.now(UTC)
            self._error = str(e)

            return RuleVerificationOutput(
                workflow_id=self._workflow_id,
                status=self._status,
                started_at=self._started_at,
                completed_at=self._completed_at,
                rule_id=input.rule_id,
                tier_results=self._tier_results,
                highest_tier_passed=None,
                overall_score=0.0,
                overall_passed=False,
                stopped_early=True,
                stop_reason=self._error,
                error=self._error,
            )

    @workflow.query
    def progress(self) -> RuleVerificationProgress:
        """Query current workflow progress."""
        return RuleVerificationProgress(
            workflow_id=self._workflow_id,
            status=self._status,
            rule_id=self._rule_id,
            current_tier=self._current_tier,
            tiers_completed=self._tiers_completed,
            tiers_remaining=self._tiers_remaining,
        )


# =============================================================================
# CounterfactualAnalysisWorkflow
# =============================================================================


@workflow.defn
class CounterfactualAnalysisWorkflow:
    """
    Baseline + parallel scenario analysis workflow.

    Pattern:
    1. Evaluate baseline scenario
    2. Evaluate all counterfactual scenarios in parallel
    3. Compute deltas between baseline and each scenario
    4. Generate summary

    Queries:
    - progress: Get current progress
    """

    def __init__(self) -> None:
        self._workflow_id: str = ""
        self._status = WorkflowStatus.PENDING
        self._started_at: datetime | None = None
        self._completed_at: datetime | None = None
        self._total_scenarios = 0
        self._completed_scenarios = 0
        self._current_scenario: str | None = None
        self._baseline_result: ScenarioResult | None = None
        self._scenario_results: list[ScenarioResult] = []
        self._delta_analyses: list[DeltaAnalysis] = []
        self._error: str | None = None

    @workflow.run
    async def run(self, input: CounterfactualInput) -> CounterfactualOutput:
        """Execute the counterfactual analysis workflow."""
        self._workflow_id = workflow.info().workflow_id
        self._started_at = datetime.now(UTC)
        self._status = WorkflowStatus.RUNNING
        self._total_scenarios = len(input.scenarios)

        try:
            # Phase 1: Evaluate baseline
            self._current_scenario = "baseline"
            self._baseline_result = await workflow.execute_activity(
                "evaluate_baseline_activity",
                args=[input.rule_id, input.baseline_facts],
                start_to_close_timeout=MEDIUM_TIMEOUT,
                retry_policy=DEFAULT_RETRY_POLICY,
            )

            # Phase 2: Evaluate counterfactuals in parallel
            self._current_scenario = "counterfactuals"
            counterfactual_tasks = [
                workflow.execute_activity(
                    "analyze_counterfactual_activity",
                    args=[
                        input.rule_id,
                        input.baseline_facts,
                        scenario.scenario_id,
                        scenario.scenario_type.value,
                        scenario.description,
                        scenario.modified_facts,
                        self._baseline_result.decision,
                    ],
                    start_to_close_timeout=MEDIUM_TIMEOUT,
                    retry_policy=DEFAULT_RETRY_POLICY,
                )
                for scenario in input.scenarios
            ]

            self._scenario_results = list(await asyncio.gather(*counterfactual_tasks))
            self._completed_scenarios = len(self._scenario_results)

            # Phase 3: Compute deltas
            if input.include_delta_analysis:
                self._current_scenario = "delta_analysis"
                baseline_dict = {
                    "decision": self._baseline_result.decision,
                    "obligations": self._baseline_result.obligations,
                }

                delta_tasks = [
                    workflow.execute_activity(
                        "compute_delta_activity",
                        args=[
                            baseline_dict,
                            {
                                "scenario_id": sr.scenario_id,
                                "decision": sr.decision,
                                "obligations": sr.obligations,
                                "key_differences": sr.key_differences,
                            },
                        ],
                        start_to_close_timeout=SHORT_TIMEOUT,
                        retry_policy=DEFAULT_RETRY_POLICY,
                    )
                    for sr in self._scenario_results
                ]

                self._delta_analyses = list(await asyncio.gather(*delta_tasks))

            # Generate summary
            scenarios_with_change = sum(1 for sr in self._scenario_results if sr.differs_from_baseline)
            summary = (
                f"Analyzed {len(self._scenario_results)} counterfactual scenarios. "
                f"{scenarios_with_change} resulted in different decisions from baseline "
                f"({self._baseline_result.decision})."
            )

            self._status = WorkflowStatus.COMPLETED
            self._completed_at = datetime.now(UTC)
            self._current_scenario = None

            return CounterfactualOutput(
                workflow_id=self._workflow_id,
                status=self._status,
                started_at=self._started_at,
                completed_at=self._completed_at,
                rule_id=input.rule_id,
                baseline_result=self._baseline_result,
                scenario_results=self._scenario_results,
                delta_analyses=self._delta_analyses,
                summary=summary,
            )

        except Exception as e:
            self._status = WorkflowStatus.FAILED
            self._completed_at = datetime.now(UTC)
            self._error = str(e)

            return CounterfactualOutput(
                workflow_id=self._workflow_id,
                status=self._status,
                started_at=self._started_at,
                completed_at=self._completed_at,
                rule_id=input.rule_id,
                baseline_result=self._baseline_result
                or ScenarioResult(
                    scenario_id="baseline",
                    scenario_type=input.scenarios[0].scenario_type if input.scenarios else "threshold",
                    description="Baseline (failed)",
                    decision="error",
                    applicable=False,
                    obligations=[],
                    trace=[],
                    differs_from_baseline=False,
                    key_differences=[],
                ),
                scenario_results=self._scenario_results,
                delta_analyses=self._delta_analyses,
                summary=f"Analysis failed: {self._error}",
                error=self._error,
            )

    @workflow.query
    def progress(self) -> CounterfactualProgress:
        """Query current workflow progress."""
        return CounterfactualProgress(
            workflow_id=self._workflow_id,
            status=self._status,
            total_scenarios=self._total_scenarios,
            completed_scenarios=self._completed_scenarios,
            current_scenario=self._current_scenario,
        )


# =============================================================================
# DriftDetectionWorkflow
# =============================================================================


@workflow.defn
class DriftDetectionWorkflow:
    """
    Scheduled workflow for detecting rule drift.

    Pattern:
    1. Get all rule IDs (or use provided list)
    2. Check each rule for drift in parallel batches
    3. Aggregate results
    4. Send notifications if drift detected

    Can be scheduled via cron for periodic execution.

    Queries:
    - progress: Get current progress
    """

    def __init__(self) -> None:
        self._workflow_id: str = ""
        self._status = WorkflowStatus.PENDING
        self._started_at: datetime | None = None
        self._completed_at: datetime | None = None
        self._total_rules = 0
        self._checked_rules = 0
        self._drift_detected = 0
        self._drift_results: list[RuleDriftResult] = []
        self._notifications_sent = 0
        self._error: str | None = None

    @workflow.run
    async def run(self, input: DriftDetectionInput) -> DriftDetectionOutput:
        """Execute the drift detection workflow."""
        self._workflow_id = workflow.info().workflow_id
        self._started_at = datetime.now(UTC)
        self._status = WorkflowStatus.RUNNING

        try:
            # Phase 1: Get rule IDs
            if input.rule_ids:
                rule_ids = input.rule_ids
            else:
                rule_ids = await workflow.execute_activity(
                    "get_all_rule_ids_activity",
                    start_to_close_timeout=MEDIUM_TIMEOUT,
                    retry_policy=DEFAULT_RETRY_POLICY,
                )

            self._total_rules = len(rule_ids)

            # Phase 2: Check rules for drift in parallel batches
            # Process in batches of 10 to avoid overwhelming the system
            batch_size = 10
            for i in range(0, len(rule_ids), batch_size):
                batch = rule_ids[i : i + batch_size]

                check_tasks = [
                    workflow.execute_activity(
                        "check_rule_drift_activity",
                        args=[rule_id],
                        start_to_close_timeout=MEDIUM_TIMEOUT,
                        retry_policy=DEFAULT_RETRY_POLICY,
                    )
                    for rule_id in batch
                ]

                batch_results = await asyncio.gather(*check_tasks)

                for result in batch_results:
                    self._drift_results.append(result)
                    self._checked_rules += 1
                    if result.has_drift:
                        self._drift_detected += 1

            # Phase 3: Send notifications
            if input.notify_on_drift and self._drift_detected > 0:
                drift_results_dicts = [
                    {
                        "rule_id": r.rule_id,
                        "has_drift": r.has_drift,
                        "drift_types": r.drift_types,
                        "details": r.details,
                        "severity": r.severity,
                    }
                    for r in self._drift_results
                    if r.has_drift
                ]

                self._notifications_sent = await workflow.execute_activity(
                    "notify_drift_detected_activity",
                    args=[drift_results_dicts],
                    start_to_close_timeout=SHORT_TIMEOUT,
                    retry_policy=DEFAULT_RETRY_POLICY,
                )

            self._status = WorkflowStatus.COMPLETED
            self._completed_at = datetime.now(UTC)

            return DriftDetectionOutput(
                workflow_id=self._workflow_id,
                status=self._status,
                started_at=self._started_at,
                completed_at=self._completed_at,
                rules_checked=self._checked_rules,
                rules_with_drift=self._drift_detected,
                drift_results=self._drift_results,
                notifications_sent=self._notifications_sent,
            )

        except Exception as e:
            self._status = WorkflowStatus.FAILED
            self._completed_at = datetime.now(UTC)
            self._error = str(e)

            return DriftDetectionOutput(
                workflow_id=self._workflow_id,
                status=self._status,
                started_at=self._started_at,
                completed_at=self._completed_at,
                rules_checked=self._checked_rules,
                rules_with_drift=self._drift_detected,
                drift_results=self._drift_results,
                notifications_sent=self._notifications_sent,
                error=self._error,
            )

    @workflow.query
    def progress(self) -> DriftDetectionProgress:
        """Query current workflow progress."""
        return DriftDetectionProgress(
            workflow_id=self._workflow_id,
            status=self._status,
            total_rules=self._total_rules,
            checked_rules=self._checked_rules,
            drift_detected=self._drift_detected,
        )
