"""
FastAPI router for workflow endpoints.

Provides REST API for:
- Starting workflows
- Querying workflow status and progress
- Getting workflow results
- Signaling running workflows
- Managing scheduled workflows
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.models import CustomBaseModel

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
)
from .service import WorkflowClient, get_client

router = APIRouter(prefix="/workflows", tags=["Workflows"])


# Dependency for getting workflow client
async def get_workflow_client() -> WorkflowClient:
    """Dependency to get the workflow client."""
    return await get_client()


# =============================================================================
# Response Models
# =============================================================================


class WorkflowStartResponse(CustomBaseModel):
    """Response when starting a workflow."""

    workflow_id: str
    message: str


class SkipTierRequest(CustomBaseModel):
    """Request to skip a verification tier."""

    tier: VerificationTier


# =============================================================================
# ComplianceCheckWorkflow Endpoints
# =============================================================================


@router.post("/compliance-check/start", response_model=WorkflowStartResponse)
async def start_compliance_check(
    input: ComplianceCheckInput,
    client: WorkflowClient = Depends(get_workflow_client),
) -> WorkflowStartResponse:
    """Start a new compliance check workflow.

    Initiates parallel evaluation of multiple jurisdictions with conflict
    detection and pathway synthesis.
    """
    try:
        workflow_id = await client.start_compliance_check(input)
        return WorkflowStartResponse(
            workflow_id=workflow_id,
            message="Compliance check workflow started",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/compliance-check/{workflow_id}/status", response_model=WorkflowInfo)
async def get_compliance_check_status(
    workflow_id: str,
    client: WorkflowClient = Depends(get_workflow_client),
) -> WorkflowInfo:
    """Get compliance check workflow status."""
    try:
        return await client.get_workflow_status(workflow_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/compliance-check/{workflow_id}/progress", response_model=ComplianceCheckProgress)
async def get_compliance_check_progress(
    workflow_id: str,
    client: WorkflowClient = Depends(get_workflow_client),
) -> ComplianceCheckProgress:
    """Get compliance check workflow progress.

    Returns current phase and completion percentage.
    """
    try:
        return await client.get_compliance_check_progress(workflow_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/compliance-check/{workflow_id}/result", response_model=ComplianceCheckOutput)
async def get_compliance_check_result(
    workflow_id: str,
    client: WorkflowClient = Depends(get_workflow_client),
) -> ComplianceCheckOutput:
    """Get compliance check workflow result.

    Waits for workflow completion if still running.
    """
    try:
        return await client.get_compliance_check_result(workflow_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# =============================================================================
# RuleVerificationWorkflow Endpoints
# =============================================================================


@router.post("/verification/start", response_model=WorkflowStartResponse)
async def start_verification(
    input: RuleVerificationInput,
    client: WorkflowClient = Depends(get_workflow_client),
) -> WorkflowStartResponse:
    """Start a new rule verification workflow.

    Executes verification tiers 0-4 sequentially with early termination on failure.
    """
    try:
        workflow_id = await client.start_rule_verification(input)
        return WorkflowStartResponse(
            workflow_id=workflow_id,
            message="Rule verification workflow started",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/verification/{workflow_id}/status", response_model=WorkflowInfo)
async def get_verification_status(
    workflow_id: str,
    client: WorkflowClient = Depends(get_workflow_client),
) -> WorkflowInfo:
    """Get rule verification workflow status."""
    try:
        return await client.get_workflow_status(workflow_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/verification/{workflow_id}/progress", response_model=RuleVerificationProgress)
async def get_verification_progress(
    workflow_id: str,
    client: WorkflowClient = Depends(get_workflow_client),
) -> RuleVerificationProgress:
    """Get rule verification workflow progress.

    Returns current tier and completion status.
    """
    try:
        return await client.get_verification_progress(workflow_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/verification/{workflow_id}/result", response_model=RuleVerificationOutput)
async def get_verification_result(
    workflow_id: str,
    client: WorkflowClient = Depends(get_workflow_client),
) -> RuleVerificationOutput:
    """Get rule verification workflow result.

    Waits for workflow completion if still running.
    """
    try:
        return await client.get_verification_result(workflow_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/verification/{workflow_id}/skip-tier")
async def skip_verification_tier(
    workflow_id: str,
    request: SkipTierRequest,
    client: WorkflowClient = Depends(get_workflow_client),
) -> dict:
    """Signal a running verification workflow to skip a tier.

    Must be called before the tier starts execution.
    """
    try:
        await client.skip_verification_tier(workflow_id, request.tier)
        return {"message": f"Signal sent to skip tier {request.tier.value}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# =============================================================================
# CounterfactualAnalysisWorkflow Endpoints
# =============================================================================


@router.post("/counterfactual/start", response_model=WorkflowStartResponse)
async def start_counterfactual(
    input: CounterfactualInput,
    client: WorkflowClient = Depends(get_workflow_client),
) -> WorkflowStartResponse:
    """Start a new counterfactual analysis workflow.

    Evaluates baseline scenario and multiple counterfactual scenarios in parallel.
    """
    try:
        workflow_id = await client.start_counterfactual_analysis(input)
        return WorkflowStartResponse(
            workflow_id=workflow_id,
            message="Counterfactual analysis workflow started",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/counterfactual/{workflow_id}/status", response_model=WorkflowInfo)
async def get_counterfactual_status(
    workflow_id: str,
    client: WorkflowClient = Depends(get_workflow_client),
) -> WorkflowInfo:
    """Get counterfactual analysis workflow status."""
    try:
        return await client.get_workflow_status(workflow_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/counterfactual/{workflow_id}/progress", response_model=CounterfactualProgress)
async def get_counterfactual_progress(
    workflow_id: str,
    client: WorkflowClient = Depends(get_workflow_client),
) -> CounterfactualProgress:
    """Get counterfactual analysis workflow progress.

    Returns number of scenarios completed.
    """
    try:
        return await client.get_counterfactual_progress(workflow_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/counterfactual/{workflow_id}/result", response_model=CounterfactualOutput)
async def get_counterfactual_result(
    workflow_id: str,
    client: WorkflowClient = Depends(get_workflow_client),
) -> CounterfactualOutput:
    """Get counterfactual analysis workflow result.

    Waits for workflow completion if still running.
    """
    try:
        return await client.get_counterfactual_result(workflow_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# =============================================================================
# DriftDetectionWorkflow Endpoints
# =============================================================================


@router.post("/drift-detection/start", response_model=WorkflowStartResponse)
async def start_drift_detection(
    input: DriftDetectionInput,
    client: WorkflowClient = Depends(get_workflow_client),
) -> WorkflowStartResponse:
    """Start a one-time drift detection workflow.

    Checks all rules (or specified subset) for schema, source, and reference drift.
    """
    try:
        workflow_id = await client.start_drift_detection(input)
        return WorkflowStartResponse(
            workflow_id=workflow_id,
            message="Drift detection workflow started",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/drift-detection/{workflow_id}/status", response_model=WorkflowInfo)
async def get_drift_detection_status(
    workflow_id: str,
    client: WorkflowClient = Depends(get_workflow_client),
) -> WorkflowInfo:
    """Get drift detection workflow status."""
    try:
        return await client.get_workflow_status(workflow_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/drift-detection/{workflow_id}/progress", response_model=DriftDetectionProgress)
async def get_drift_detection_progress(
    workflow_id: str,
    client: WorkflowClient = Depends(get_workflow_client),
) -> DriftDetectionProgress:
    """Get drift detection workflow progress.

    Returns number of rules checked and drift detected.
    """
    try:
        return await client.get_drift_detection_progress(workflow_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/drift-detection/{workflow_id}/result", response_model=DriftDetectionOutput)
async def get_drift_detection_result(
    workflow_id: str,
    client: WorkflowClient = Depends(get_workflow_client),
) -> DriftDetectionOutput:
    """Get drift detection workflow result.

    Waits for workflow completion if still running.
    """
    try:
        return await client.get_drift_detection_result(workflow_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/drift-detection/schedule", response_model=WorkflowStartResponse)
async def schedule_drift_detection(
    config: DriftScheduleConfig,
    client: WorkflowClient = Depends(get_workflow_client),
) -> WorkflowStartResponse:
    """Schedule recurring drift detection.

    Creates a Temporal schedule that runs drift detection on a cron schedule.
    """
    try:
        schedule_id = await client.schedule_drift_detection(config)
        return WorkflowStartResponse(
            workflow_id=schedule_id,
            message=f"Drift detection scheduled with cron: {config.cron_expression}",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# =============================================================================
# CreditDecisionWorkflow Endpoints
# =============================================================================


@router.post("/credit-decision/start", response_model=WorkflowStartResponse)
async def start_credit_decision(
    input: CreditDecisionParams,
    client: WorkflowClient = Depends(get_workflow_client),
) -> WorkflowStartResponse:
    """Start a new credit decision workflow.

    Runs document classification, parallel agent analysis, synthesis, and routing.
    """
    try:
        workflow_id = await client.start_credit_decision(input)
        return WorkflowStartResponse(
            workflow_id=workflow_id,
            message="Credit decision workflow started",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/credit-decision/{workflow_id}/status", response_model=WorkflowInfo)
async def get_credit_decision_status(
    workflow_id: str,
    client: WorkflowClient = Depends(get_workflow_client),
) -> WorkflowInfo:
    """Get credit decision workflow status."""
    try:
        return await client.get_workflow_status(workflow_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/credit-decision/{workflow_id}/progress", response_model=CreditDecisionProgress)
async def get_credit_decision_progress(
    workflow_id: str,
    client: WorkflowClient = Depends(get_workflow_client),
) -> CreditDecisionProgress:
    """Get credit decision workflow progress.

    Returns current phase and completion percentage.
    """
    try:
        return await client.get_credit_decision_progress(workflow_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/credit-decision/{workflow_id}/result", response_model=CreditDecisionResult)
async def get_credit_decision_result(
    workflow_id: str,
    client: WorkflowClient = Depends(get_workflow_client),
) -> CreditDecisionResult:
    """Get credit decision workflow result.

    Waits for workflow completion if still running.
    """
    try:
        return await client.get_credit_decision_result(workflow_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# =============================================================================
# Generic Workflow Operations
# =============================================================================


@router.post("/{workflow_id}/cancel")
async def cancel_workflow(
    workflow_id: str,
    client: WorkflowClient = Depends(get_workflow_client),
) -> dict:
    """Cancel a running workflow.

    Sends a cancellation request to the workflow. The workflow may perform
    cleanup before terminating.
    """
    try:
        await client.cancel_workflow(workflow_id)
        return {"message": f"Cancellation requested for workflow {workflow_id}"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/{workflow_id}/terminate")
async def terminate_workflow(
    workflow_id: str,
    reason: str = "Terminated by user",
    client: WorkflowClient = Depends(get_workflow_client),
) -> dict:
    """Terminate a running workflow immediately.

    Forces immediate termination without cleanup.
    """
    try:
        await client.terminate_workflow(workflow_id, reason)
        return {"message": f"Workflow {workflow_id} terminated"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
