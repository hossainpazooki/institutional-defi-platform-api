"""
Temporal worker configuration and startup.

The worker listens for tasks from Temporal and executes activities and workflows.

Usage:
    # Run as standalone worker
    python -m src.workflows.worker

    # Or import and use in application
    from src.workflows.worker import create_worker, run_worker
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from temporalio.client import Client
from temporalio.worker import Worker

from .activities import (
    aggregate_obligations_activity,
    analyze_counterfactual_activity,
    check_rule_drift_activity,
    compute_delta_activity,
    detect_conflicts_activity,
    # CounterfactualAnalysisWorkflow activities
    evaluate_baseline_activity,
    evaluate_jurisdiction_activity,
    # DriftDetectionWorkflow activities
    get_all_rule_ids_activity,
    get_equivalences_activity,
    # RuleVerificationWorkflow activities
    load_rule_activity,
    notify_drift_detected_activity,
    # ComplianceCheckWorkflow activities
    resolve_jurisdictions_activity,
    synthesize_pathway_activity,
    verify_tier_0_activity,
    verify_tier_1_activity,
    verify_tier_2_activity,
    verify_tier_3_activity,
    verify_tier_4_activity,
)
from .config import WorkflowConfig
from .workflows import (
    ComplianceCheckWorkflow,
    CounterfactualAnalysisWorkflow,
    DriftDetectionWorkflow,
    RuleVerificationWorkflow,
)

logger = logging.getLogger(__name__)


# All activities registered with the worker
ACTIVITIES = [
    # ComplianceCheckWorkflow
    resolve_jurisdictions_activity,
    get_equivalences_activity,
    evaluate_jurisdiction_activity,
    detect_conflicts_activity,
    synthesize_pathway_activity,
    aggregate_obligations_activity,
    # RuleVerificationWorkflow
    load_rule_activity,
    verify_tier_0_activity,
    verify_tier_1_activity,
    verify_tier_2_activity,
    verify_tier_3_activity,
    verify_tier_4_activity,
    # CounterfactualAnalysisWorkflow
    evaluate_baseline_activity,
    analyze_counterfactual_activity,
    compute_delta_activity,
    # DriftDetectionWorkflow
    get_all_rule_ids_activity,
    check_rule_drift_activity,
    notify_drift_detected_activity,
]


# All workflows registered with the worker
WORKFLOWS = [
    ComplianceCheckWorkflow,
    RuleVerificationWorkflow,
    CounterfactualAnalysisWorkflow,
    DriftDetectionWorkflow,
]


async def create_client(
    host: str | None = None,
    namespace: str | None = None,
) -> Client:
    """Create a Temporal client connection.

    Args:
        host: Temporal server address (default: localhost:7233)
        namespace: Temporal namespace (default: default)

    Returns:
        Connected Temporal client
    """
    config = WorkflowConfig()
    host = host or config.host
    namespace = namespace or config.namespace

    logger.info(f"Connecting to Temporal at {host} (namespace: {namespace})")

    client = await Client.connect(host, namespace=namespace)
    return client


async def create_worker(
    client: Client,
    task_queue: str | None = None,
    **kwargs: Any,
) -> Worker:
    """Create a Temporal worker with all workflows and activities registered.

    Args:
        client: Temporal client connection
        task_queue: Task queue name (default: compliance-workflows)
        **kwargs: Additional worker configuration

    Returns:
        Configured Temporal worker
    """
    from temporalio.worker.workflow_sandbox import (
        SandboxedWorkflowRunner,
        SandboxRestrictions,
    )

    config = WorkflowConfig()
    task_queue = task_queue or config.task_queue

    # Configure sandbox to pass through modules that use non-deterministic datetime
    # These modules are only used in activities, not in workflow code
    sandbox_runner = SandboxedWorkflowRunner(
        restrictions=SandboxRestrictions.default.with_passthrough_modules(
            "src",
            "pydantic",
        ),
    )

    worker = Worker(
        client,
        task_queue=task_queue,
        workflows=WORKFLOWS,
        activities=ACTIVITIES,
        workflow_runner=sandbox_runner,
        **kwargs,
    )

    logger.info(f"Created worker for task queue: {task_queue}")
    logger.info(f"Registered {len(WORKFLOWS)} workflows: {[w.__name__ for w in WORKFLOWS]}")
    logger.info(f"Registered {len(ACTIVITIES)} activities")

    return worker


async def run_worker(
    host: str | None = None,
    namespace: str | None = None,
    task_queue: str | None = None,
) -> None:
    """Run a standalone Temporal worker.

    This function blocks until the worker is shut down.

    Args:
        host: Temporal server address
        namespace: Temporal namespace
        task_queue: Task queue name
    """
    client = await create_client(host=host, namespace=namespace)
    worker = await create_worker(client, task_queue=task_queue)

    logger.info("Starting worker...")
    await worker.run()


def main() -> None:
    """Entry point for running worker as standalone process."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    config = WorkflowConfig()
    logger.info("Starting Temporal worker process")
    logger.info(f"Task queue: {config.task_queue}")
    logger.info(f"Temporal host: {config.host}")

    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
