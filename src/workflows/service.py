"""
Temporal client utilities for starting and managing workflows.

Provides high-level functions for:
- Starting workflows
- Querying workflow status and progress
- Signaling running workflows
- Getting workflow results

Usage:
    from src.workflows.service import WorkflowClient

    async with WorkflowClient() as client:
        workflow_id = await client.start_compliance_check(input)
        progress = await client.get_compliance_check_progress(workflow_id)
        result = await client.get_compliance_check_result(workflow_id)
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

try:
    import temporalio.client
    from temporalio.client import Client
    from temporalio.service import RPCError

    _TEMPORAL_AVAILABLE = True
except ImportError:
    _TEMPORAL_AVAILABLE = False

from .config import WorkflowConfig
from .schemas import (
    ComplianceCheckInput,
    ComplianceCheckOutput,
    ComplianceCheckProgress,
    CounterfactualInput,
    CounterfactualOutput,
    CounterfactualProgress,
    CreditDecisionParams,
    CreditDecisionProgress,
    CreditDecisionResult,
    DriftDetectionInput,
    DriftDetectionOutput,
    DriftDetectionProgress,
    DriftScheduleConfig,
    RuleVerificationInput,
    RuleVerificationOutput,
    RuleVerificationProgress,
    VerificationTier,
    WorkflowInfo,
    WorkflowStatus,
)

if _TEMPORAL_AVAILABLE:
    from .credit_decision import CreditDecisionWorkflow
    from .workflows import (
        ComplianceCheckWorkflow,
        CounterfactualAnalysisWorkflow,
        DriftDetectionWorkflow,
        RuleVerificationWorkflow,
    )

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


def generate_workflow_id(prefix: str) -> str:
    """Generate a unique workflow ID with a prefix."""
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class WorkflowClient:
    """High-level client for managing compliance workflows.

    Provides typed methods for starting workflows and querying their status.
    """

    def __init__(
        self,
        client: Client | None = None,
        host: str | None = None,
        namespace: str | None = None,
        task_queue: str | None = None,
    ) -> None:
        """Initialize the workflow client.

        Args:
            client: Pre-existing Temporal client (optional)
            host: Temporal server address
            namespace: Temporal namespace
            task_queue: Default task queue
        """
        config = WorkflowConfig()
        self._client = client
        self._host = host or config.host
        self._namespace = namespace or config.namespace
        self._task_queue = task_queue or config.task_queue
        self._owns_client = client is None

    async def connect(self) -> None:
        """Connect to Temporal server."""
        if not _TEMPORAL_AVAILABLE:
            raise RuntimeError(
                "temporalio is not installed. Install with: pip install -e '.[temporal]'"
            )
        if self._client is None:
            self._client = await Client.connect(
                self._host,
                namespace=self._namespace,
            )

    async def close(self) -> None:
        """Close the client connection."""
        # Temporal Python SDK doesn't require explicit close
        pass

    async def __aenter__(self) -> WorkflowClient:
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    @property
    def client(self) -> Client:
        """Get the underlying Temporal client."""
        if self._client is None:
            raise RuntimeError("Client not connected. Call connect() first or use async with.")
        return self._client

    # =========================================================================
    # ComplianceCheckWorkflow
    # =========================================================================

    async def start_compliance_check(
        self,
        input: ComplianceCheckInput,
        workflow_id: str | None = None,
    ) -> str:
        """Start a compliance check workflow.

        Args:
            input: Compliance check input parameters
            workflow_id: Optional custom workflow ID

        Returns:
            Workflow ID
        """
        workflow_id = workflow_id or generate_workflow_id("compliance-check")

        await self.client.start_workflow(
            ComplianceCheckWorkflow.run,
            input,
            id=workflow_id,
            task_queue=self._task_queue,
        )

        return workflow_id

    async def get_compliance_check_progress(
        self,
        workflow_id: str,
    ) -> ComplianceCheckProgress:
        """Query compliance check workflow progress.

        Args:
            workflow_id: Workflow ID

        Returns:
            Current progress
        """
        handle = self.client.get_workflow_handle(workflow_id)
        return await handle.query(ComplianceCheckWorkflow.progress)

    async def get_compliance_check_result(
        self,
        workflow_id: str,
        timeout_seconds: float | None = None,
    ) -> ComplianceCheckOutput:
        """Get compliance check workflow result.

        Waits for workflow completion if still running.

        Args:
            workflow_id: Workflow ID
            timeout_seconds: Optional timeout

        Returns:
            Workflow result
        """
        handle = self.client.get_workflow_handle(workflow_id)
        return await handle.result()

    # =========================================================================
    # RuleVerificationWorkflow
    # =========================================================================

    async def start_rule_verification(
        self,
        input: RuleVerificationInput,
        workflow_id: str | None = None,
    ) -> str:
        """Start a rule verification workflow.

        Args:
            input: Rule verification input parameters
            workflow_id: Optional custom workflow ID

        Returns:
            Workflow ID
        """
        workflow_id = workflow_id or generate_workflow_id("verification")

        await self.client.start_workflow(
            RuleVerificationWorkflow.run,
            input,
            id=workflow_id,
            task_queue=self._task_queue,
        )

        return workflow_id

    async def get_verification_progress(
        self,
        workflow_id: str,
    ) -> RuleVerificationProgress:
        """Query rule verification workflow progress.

        Args:
            workflow_id: Workflow ID

        Returns:
            Current progress
        """
        handle = self.client.get_workflow_handle(workflow_id)
        return await handle.query(RuleVerificationWorkflow.progress)

    async def get_verification_result(
        self,
        workflow_id: str,
    ) -> RuleVerificationOutput:
        """Get rule verification workflow result.

        Args:
            workflow_id: Workflow ID

        Returns:
            Workflow result
        """
        handle = self.client.get_workflow_handle(workflow_id)
        return await handle.result()

    async def skip_verification_tier(
        self,
        workflow_id: str,
        tier: VerificationTier,
    ) -> None:
        """Signal a running verification workflow to skip a tier.

        Args:
            workflow_id: Workflow ID
            tier: Tier to skip
        """
        handle = self.client.get_workflow_handle(workflow_id)
        await handle.signal(RuleVerificationWorkflow.skip_tier, tier.value)

    # =========================================================================
    # CounterfactualAnalysisWorkflow
    # =========================================================================

    async def start_counterfactual_analysis(
        self,
        input: CounterfactualInput,
        workflow_id: str | None = None,
    ) -> str:
        """Start a counterfactual analysis workflow.

        Args:
            input: Counterfactual analysis input parameters
            workflow_id: Optional custom workflow ID

        Returns:
            Workflow ID
        """
        workflow_id = workflow_id or generate_workflow_id("counterfactual")

        await self.client.start_workflow(
            CounterfactualAnalysisWorkflow.run,
            input,
            id=workflow_id,
            task_queue=self._task_queue,
        )

        return workflow_id

    async def get_counterfactual_progress(
        self,
        workflow_id: str,
    ) -> CounterfactualProgress:
        """Query counterfactual analysis workflow progress.

        Args:
            workflow_id: Workflow ID

        Returns:
            Current progress
        """
        handle = self.client.get_workflow_handle(workflow_id)
        return await handle.query(CounterfactualAnalysisWorkflow.progress)

    async def get_counterfactual_result(
        self,
        workflow_id: str,
    ) -> CounterfactualOutput:
        """Get counterfactual analysis workflow result.

        Args:
            workflow_id: Workflow ID

        Returns:
            Workflow result
        """
        handle = self.client.get_workflow_handle(workflow_id)
        return await handle.result()

    # =========================================================================
    # CreditDecisionWorkflow
    # =========================================================================

    async def start_credit_decision(
        self,
        input: CreditDecisionParams,
        workflow_id: str | None = None,
    ) -> str:
        """Start a credit decision workflow.

        Args:
            input: Credit decision input parameters
            workflow_id: Optional custom workflow ID

        Returns:
            Workflow ID
        """
        workflow_id = workflow_id or generate_workflow_id("credit-decision")

        await self.client.start_workflow(
            CreditDecisionWorkflow.run,
            input,
            id=workflow_id,
            task_queue=self._task_queue,
        )

        return workflow_id

    async def get_credit_decision_progress(
        self,
        workflow_id: str,
    ) -> CreditDecisionProgress:
        """Query credit decision workflow progress.

        Args:
            workflow_id: Workflow ID

        Returns:
            Current progress
        """
        handle = self.client.get_workflow_handle(workflow_id)
        return await handle.query(CreditDecisionWorkflow.progress)

    async def get_credit_decision_result(
        self,
        workflow_id: str,
    ) -> CreditDecisionResult:
        """Get credit decision workflow result.

        Args:
            workflow_id: Workflow ID

        Returns:
            Workflow result
        """
        handle = self.client.get_workflow_handle(workflow_id)
        return await handle.result()

    # =========================================================================
    # DriftDetectionWorkflow
    # =========================================================================

    async def start_drift_detection(
        self,
        input: DriftDetectionInput,
        workflow_id: str | None = None,
    ) -> str:
        """Start a drift detection workflow.

        Args:
            input: Drift detection input parameters
            workflow_id: Optional custom workflow ID

        Returns:
            Workflow ID
        """
        workflow_id = workflow_id or generate_workflow_id("drift-detection")

        await self.client.start_workflow(
            DriftDetectionWorkflow.run,
            input,
            id=workflow_id,
            task_queue=self._task_queue,
        )

        return workflow_id

    async def get_drift_detection_progress(
        self,
        workflow_id: str,
    ) -> DriftDetectionProgress:
        """Query drift detection workflow progress.

        Args:
            workflow_id: Workflow ID

        Returns:
            Current progress
        """
        handle = self.client.get_workflow_handle(workflow_id)
        return await handle.query(DriftDetectionWorkflow.progress)

    async def get_drift_detection_result(
        self,
        workflow_id: str,
    ) -> DriftDetectionOutput:
        """Get drift detection workflow result.

        Args:
            workflow_id: Workflow ID

        Returns:
            Workflow result
        """
        handle = self.client.get_workflow_handle(workflow_id)
        return await handle.result()

    async def schedule_drift_detection(
        self,
        config: DriftScheduleConfig,
    ) -> str:
        """Schedule recurring drift detection.

        Args:
            config: Schedule configuration

        Returns:
            Schedule ID
        """
        # Use Temporal schedules for cron-based execution
        await self.client.create_schedule(
            config.schedule_id,
            schedule=temporalio.client.Schedule(
                action=temporalio.client.ScheduleActionStartWorkflow(
                    DriftDetectionWorkflow.run,
                    config.input,
                    id=f"drift-detection-scheduled-{config.schedule_id}",
                    task_queue=self._task_queue,
                ),
                spec=temporalio.client.ScheduleSpec(
                    cron_expressions=[config.cron_expression],
                ),
                state=temporalio.client.ScheduleState(
                    paused=not config.enabled,
                ),
            ),
        )

        return config.schedule_id

    # =========================================================================
    # Generic Workflow Operations
    # =========================================================================

    async def get_workflow_status(
        self,
        workflow_id: str,
    ) -> WorkflowInfo:
        """Get basic workflow information.

        Args:
            workflow_id: Workflow ID

        Returns:
            Workflow info
        """
        handle = self.client.get_workflow_handle(workflow_id)

        try:
            describe = await handle.describe()

            # Map Temporal status to our WorkflowStatus
            status_map = {
                "RUNNING": WorkflowStatus.RUNNING,
                "COMPLETED": WorkflowStatus.COMPLETED,
                "FAILED": WorkflowStatus.FAILED,
                "CANCELED": WorkflowStatus.CANCELLED,
                "TERMINATED": WorkflowStatus.CANCELLED,
                "TIMED_OUT": WorkflowStatus.TIMED_OUT,
            }

            status_str = str(describe.status).split(".")[-1]
            status = status_map.get(status_str, WorkflowStatus.PENDING)

            return WorkflowInfo(
                workflow_id=workflow_id,
                workflow_type=describe.workflow_type,
                status=status,
                started_at=describe.start_time,
                completed_at=describe.close_time,
                run_id=describe.run_id,
                task_queue=self._task_queue,
            )

        except RPCError as e:
            # Workflow not found
            raise ValueError(f"Workflow not found: {workflow_id}") from e

    async def cancel_workflow(
        self,
        workflow_id: str,
    ) -> None:
        """Cancel a running workflow.

        Args:
            workflow_id: Workflow ID
        """
        handle = self.client.get_workflow_handle(workflow_id)
        await handle.cancel()

    async def terminate_workflow(
        self,
        workflow_id: str,
        reason: str = "Terminated by user",
    ) -> None:
        """Terminate a running workflow immediately.

        Args:
            workflow_id: Workflow ID
            reason: Termination reason
        """
        handle = self.client.get_workflow_handle(workflow_id)
        await handle.terminate(reason=reason)


# Module-level client for convenience
_default_client: WorkflowClient | None = None


async def get_client() -> WorkflowClient:
    """Get or create the default workflow client.

    Returns:
        Connected workflow client
    """
    global _default_client

    if _default_client is None:
        _default_client = WorkflowClient()
        await _default_client.connect()

    return _default_client


@asynccontextmanager
async def workflow_client() -> AsyncGenerator[WorkflowClient, None]:
    """Context manager for workflow client.

    Usage:
        async with workflow_client() as client:
            await client.start_compliance_check(input)
    """
    client = WorkflowClient()
    await client.connect()
    try:
        yield client
    finally:
        await client.close()
