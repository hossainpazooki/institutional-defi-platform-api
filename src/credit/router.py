"""Routes for credit decisioning pipeline."""

from fastapi import APIRouter, HTTPException

from .schemas import (
    ClassificationResult,
    CreditApplication,
    DocumentUpload,
    HITLDecision,
    PipelineStatus,
    SynthesisOutput,
)
from .service import CreditPipelineService, HITLService

router = APIRouter(prefix="/credit", tags=["Credit Decisioning"])
_pipeline = CreditPipelineService()
_hitl = HITLService()


@router.post("/applications", response_model=CreditApplication)
async def create_application(
    borrower_name: str,
    deal_amount_usd: float,
    industry: str,
    borrower_type: str,
    document_ids: list[str] | None = None,
) -> CreditApplication:
    """Submit a new credit application."""
    return _pipeline.create_application(
        borrower_name=borrower_name,
        deal_amount_usd=deal_amount_usd,
        document_ids=document_ids or [],
        industry=industry,
        borrower_type=borrower_type,
    )


@router.post("/documents/upload", response_model=ClassificationResult)
async def upload_document(doc: DocumentUpload) -> ClassificationResult:
    """Upload a document for classification and indexing."""
    return _pipeline.upload_document(doc)


@router.post("/applications/{app_id}/analyze", response_model=SynthesisOutput)
async def analyze_application(app_id: str) -> SynthesisOutput:
    """Run the full credit analysis pipeline for an application."""
    try:
        return await _pipeline.run_analysis(app_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/applications/{app_id}/status", response_model=PipelineStatus)
async def get_status(app_id: str) -> PipelineStatus:
    """Get pipeline status for an application."""
    try:
        return _pipeline.get_status(app_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/applications/{app_id}/result", response_model=SynthesisOutput)
async def get_result(app_id: str) -> SynthesisOutput:
    """Get analysis result for an application."""
    result = _pipeline.get_result(app_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"No result for application {app_id}")
    return result


@router.post("/applications/{app_id}/review")
async def submit_review(app_id: str, decision: HITLDecision) -> dict:
    """Submit a human-in-the-loop review decision."""
    return _hitl.submit_review(app_id, decision)


@router.get("/queue")
async def get_queue() -> list[dict]:
    """Get the HITL review queue."""
    return _hitl.get_queue()
