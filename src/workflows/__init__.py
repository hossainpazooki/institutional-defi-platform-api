"""
Temporal workflows for compliance operations.

This package provides fault-tolerant, long-running workflow orchestration using Temporal.

Workflows:
- ComplianceCheckWorkflow: Parallel multi-jurisdiction compliance evaluation
- RuleVerificationWorkflow: Sequential tier-based rule verification
- CounterfactualAnalysisWorkflow: Baseline + parallel scenario analysis
- DriftDetectionWorkflow: Scheduled rule drift detection

Usage:
    # Start a workflow via client
    from src.workflows import WorkflowClient, ComplianceCheckInput

    async with WorkflowClient() as client:
        workflow_id = await client.start_compliance_check(
            ComplianceCheckInput(
                issuer_jurisdiction="EU",
                target_jurisdictions=["UK", "SG"],
                facts={"instrument_type": "utility_token"},
            )
        )
        result = await client.get_compliance_check_result(workflow_id)

    # Run worker (standalone)
    python -m src.workflows.worker

    # Use in FastAPI app
    from src.workflows import router
    app.include_router(router)
"""

from .router import router
from .schemas import (
    # ComplianceCheck schemas
    ComplianceCheckInput,
    ComplianceCheckOutput,
    ComplianceCheckProgress,
    CompliancePathway,
    ConflictResult,
    # Counterfactual schemas
    CounterfactualInput,
    CounterfactualOutput,
    CounterfactualProgress,
    CounterfactualScenario,
    DeltaAnalysis,
    # DriftDetection schemas
    DriftDetectionInput,
    DriftDetectionOutput,
    DriftDetectionProgress,
    DriftScheduleConfig,
    EquivalenceResult,
    JurisdictionResult,
    JurisdictionStatus,
    RuleDriftResult,
    # RuleVerification schemas
    RuleVerificationInput,
    RuleVerificationOutput,
    RuleVerificationProgress,
    ScenarioResult,
    ScenarioType,
    TierResult,
    VerificationTier,
    # Workflow info
    WorkflowInfo,
    # Enums
    WorkflowStatus,
)
from .service import (
    WorkflowClient,
    get_client,
    workflow_client,
)
from .worker import (
    ACTIVITIES,
    WORKFLOWS,
    create_client,
    create_worker,
    run_worker,
)
from .workflows import (
    ComplianceCheckWorkflow,
    CounterfactualAnalysisWorkflow,
    DriftDetectionWorkflow,
    RuleVerificationWorkflow,
)

__all__ = [
    # Enums
    "WorkflowStatus",
    "VerificationTier",
    "JurisdictionStatus",
    "ScenarioType",
    # ComplianceCheck
    "ComplianceCheckInput",
    "ComplianceCheckOutput",
    "ComplianceCheckProgress",
    "ComplianceCheckWorkflow",
    "JurisdictionResult",
    "EquivalenceResult",
    "ConflictResult",
    "CompliancePathway",
    # RuleVerification
    "RuleVerificationInput",
    "RuleVerificationOutput",
    "RuleVerificationProgress",
    "RuleVerificationWorkflow",
    "TierResult",
    # Counterfactual
    "CounterfactualInput",
    "CounterfactualOutput",
    "CounterfactualProgress",
    "CounterfactualAnalysisWorkflow",
    "CounterfactualScenario",
    "ScenarioResult",
    "DeltaAnalysis",
    # DriftDetection
    "DriftDetectionInput",
    "DriftDetectionOutput",
    "DriftDetectionProgress",
    "DriftDetectionWorkflow",
    "RuleDriftResult",
    "DriftScheduleConfig",
    # Workflow info
    "WorkflowInfo",
    # Client
    "WorkflowClient",
    "get_client",
    "workflow_client",
    # Router
    "router",
    # Worker
    "create_client",
    "create_worker",
    "run_worker",
    "ACTIVITIES",
    "WORKFLOWS",
]
