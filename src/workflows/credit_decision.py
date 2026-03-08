"""
Temporal workflow for credit decisioning pipeline.

Pattern: Fan-out/fan-in with parallel agent execution.
Phases:
1. classify_documents — LLM-based document type classification
2. financial_analysis — PydanticAI financial agent (parallel)
3. legal_analysis — PydanticAI legal agent (parallel with #2)
4. market_analysis — PydanticAI market agent (parallel with #2 and #3)
5. synthesis — Fan-in: combine agent outputs into recommendation
6. route_decision — Confidence/deal-size based routing + HITL escalation
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from .schemas import (
        CreditDecisionParams,
        CreditDecisionProgress,
        CreditDecisionResult,
        WorkflowStatus,
    )

PHASES = [
    "classify_documents",
    "financial_analysis",
    "legal_analysis",
    "market_analysis",
    "synthesis",
    "route_decision",
]

DEFAULT_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(minutes=1),
    maximum_attempts=3,
)

SHORT_TIMEOUT = timedelta(seconds=30)
MEDIUM_TIMEOUT = timedelta(minutes=2)
LONG_TIMEOUT = timedelta(minutes=10)


@workflow.defn
class CreditDecisionWorkflow:
    """
    Fan-out/fan-in workflow for credit decisioning.

    Phases:
    1. Classify uploaded documents
    2-4. Run financial, legal, market agents in parallel (fan-out)
    5. Synthesize results (fan-in)
    6. Route decision (escalate if needed)

    Queries:
    - progress: Get current progress
    """

    def __init__(self) -> None:
        self._workflow_id: str = ""
        self._status = WorkflowStatus.PENDING
        self._started_at: datetime | None = None
        self._completed_at: datetime | None = None
        self._current_phase = "initializing"
        self._phases_completed: list[str] = []
        self._financial_output: dict[str, Any] = {}
        self._legal_output: dict[str, Any] = {}
        self._market_output: dict[str, Any] = {}
        self._synthesis: dict[str, Any] = {}
        self._error: str | None = None

    @workflow.run  # type: ignore[untyped-decorator]
    async def run(self, params: CreditDecisionParams) -> CreditDecisionResult:
        """Execute the credit decision workflow."""
        self._workflow_id = workflow.info().workflow_id
        self._started_at = datetime.now(UTC)
        self._status = WorkflowStatus.RUNNING

        try:
            # Phase 1: Classify documents
            self._current_phase = "classify_documents"
            classifications = await workflow.execute_activity(
                "classify_documents_activity",
                args=[params.document_ids],
                start_to_close_timeout=SHORT_TIMEOUT,
                retry_policy=DEFAULT_RETRY_POLICY,
            )
            self._phases_completed.append("classify_documents")

            # Phase 2-4: Fan-out — run three agents in parallel
            self._current_phase = "agent_analysis"
            financial_task = workflow.execute_activity(
                "financial_analysis_activity",
                args=[
                    params.borrower_name,
                    params.deal_amount_usd,
                    params.industry,
                    params.borrower_type,
                ],
                start_to_close_timeout=LONG_TIMEOUT,
                retry_policy=DEFAULT_RETRY_POLICY,
            )
            legal_task = workflow.execute_activity(
                "legal_analysis_activity",
                args=[
                    params.borrower_name,
                    params.document_ids,
                    classifications,
                ],
                start_to_close_timeout=LONG_TIMEOUT,
                retry_policy=DEFAULT_RETRY_POLICY,
            )
            market_task = workflow.execute_activity(
                "market_analysis_activity",
                args=[
                    params.industry,
                    params.deal_amount_usd,
                    params.borrower_type,
                ],
                start_to_close_timeout=LONG_TIMEOUT,
                retry_policy=DEFAULT_RETRY_POLICY,
            )

            # Fan-in: wait for all three agents
            self._financial_output, self._legal_output, self._market_output = await asyncio.gather(
                financial_task, legal_task, market_task
            )
            self._phases_completed.extend(
                [
                    "financial_analysis",
                    "legal_analysis",
                    "market_analysis",
                ]
            )

            # Phase 5: Synthesis — combine agent outputs
            self._current_phase = "synthesis"
            self._synthesis = await workflow.execute_activity(
                "credit_synthesis_activity",
                args=[
                    self._financial_output,
                    self._legal_output,
                    self._market_output,
                    params.deal_amount_usd,
                ],
                start_to_close_timeout=LONG_TIMEOUT,
                retry_policy=DEFAULT_RETRY_POLICY,
            )
            self._phases_completed.append("synthesis")

            # Phase 6: Route decision
            self._current_phase = "route_decision"
            routing = await workflow.execute_activity(
                "route_credit_decision_activity",
                args=[
                    self._synthesis,
                    params.deal_amount_usd,
                    params.app_id,
                ],
                start_to_close_timeout=SHORT_TIMEOUT,
                retry_policy=DEFAULT_RETRY_POLICY,
            )
            self._phases_completed.append("route_decision")

            self._status = WorkflowStatus.COMPLETED
            self._completed_at = datetime.now(UTC)
            self._current_phase = "completed"

            return CreditDecisionResult(
                workflow_id=self._workflow_id,
                status=self._status,
                started_at=self._started_at,
                completed_at=self._completed_at,
                financial_output=self._financial_output,
                legal_output=self._legal_output,
                market_output=self._market_output,
                synthesis=self._synthesis,
                recommendation=self._synthesis.get("recommendation", ""),
                confidence=self._synthesis.get("confidence", 0.0),
                escalate=routing.get("escalate", False),
            )

        except Exception as e:
            self._status = WorkflowStatus.FAILED
            self._completed_at = datetime.now(UTC)
            self._error = str(e)

            return CreditDecisionResult(
                workflow_id=self._workflow_id,
                status=self._status,
                started_at=self._started_at,
                completed_at=self._completed_at,
                financial_output=self._financial_output,
                legal_output=self._legal_output,
                market_output=self._market_output,
                synthesis=self._synthesis,
                error=self._error,
            )

    @workflow.query  # type: ignore[untyped-decorator]
    def progress(self) -> CreditDecisionProgress:
        """Query current workflow progress."""
        remaining = [p for p in PHASES if p not in self._phases_completed]
        total = len(PHASES)
        done = len(self._phases_completed)
        phase_progress = done / total if total > 0 else 0.0

        return CreditDecisionProgress(
            workflow_id=self._workflow_id,
            status=self._status,
            current_phase=self._current_phase,
            phases_completed=self._phases_completed,
            phases_remaining=remaining,
            phase_progress=phase_progress,
        )
