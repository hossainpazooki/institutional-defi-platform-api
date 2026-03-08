"""Credit pipeline orchestration and HITL routing."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from .schemas import (
    ClassificationResult,
    CreditApplication,
    DocumentUpload,
    HITLDecision,
    PipelineStatus,
    SynthesisOutput,
)

logger = logging.getLogger(__name__)

# In-memory stores for demo
_applications: dict[str, CreditApplication] = {}
_documents: dict[str, DocumentUpload] = {}
_classifications: dict[str, ClassificationResult] = {}
_results: dict[str, SynthesisOutput] = {}
_queue: list[dict[str, Any]] = []
_decisions: dict[str, HITLDecision] = {}
_statuses: dict[str, PipelineStatus] = {}

# Document type heuristics for mock classification
_DOC_TYPE_KEYWORDS: dict[str, list[str]] = {
    "cim": ["confidential information memorandum", "cim", "investment summary", "executive summary"],
    "financial_statement": ["balance sheet", "income statement", "cash flow", "10-k", "annual report"],
    "legal_opinion": ["legal opinion", "counsel", "enforceability", "opinion letter"],
    "covenant_package": ["covenant", "financial maintenance", "leverage ratio", "debt service"],
    "tax_certificate": ["tax certificate", "tax opinion", "withholding", "tax compliance"],
}


class CreditPipelineService:
    """Orchestrates the credit decisioning pipeline."""

    def create_application(
        self,
        borrower_name: str,
        deal_amount_usd: float,
        document_ids: list[str],
        industry: str,
        borrower_type: str,
    ) -> CreditApplication:
        """Create a new credit application."""
        app = CreditApplication(
            borrower_name=borrower_name,
            deal_amount_usd=deal_amount_usd,
            document_ids=document_ids,
            industry=industry,
            borrower_type=borrower_type,
        )
        _applications[app.app_id] = app
        _statuses[app.app_id] = PipelineStatus(
            app_id=app.app_id,
            phase="submitted",
            phases_completed=["submitted"],
            phases_remaining=["document_classification", "agent_analysis", "synthesis", "decision"],
            started_at=datetime.now(UTC),
        )
        return app

    def upload_document(self, doc: DocumentUpload) -> ClassificationResult:
        """Upload and classify a document."""
        _documents[doc.document_id] = doc
        classification = self.classify_document(doc.document_id, doc.raw_text)
        _classifications[doc.document_id] = classification
        return classification

    def classify_document(self, doc_id: str, raw_text: str) -> ClassificationResult:
        """Classify a document by type using keyword heuristics."""
        text_lower = raw_text.lower()
        best_type = "other"
        best_score = 0.0
        extracted: dict[str, Any] = {}

        for doc_type, keywords in _DOC_TYPE_KEYWORDS.items():
            matches = sum(1 for kw in keywords if kw in text_lower)
            score = matches / len(keywords) if keywords else 0.0
            if score > best_score:
                best_score = score
                best_type = doc_type

        confidence = min(0.95, max(0.3, best_score + 0.4))

        if best_type == "financial_statement":
            extracted = {"period": "FY2025", "currency": "USD", "auditor": "Big Four"}
        elif best_type == "cim":
            extracted = {"deal_name": "Project Alpha", "sponsor": "PE Fund I"}
        elif best_type == "covenant_package":
            extracted = {"max_leverage": "4.0x", "min_dscr": "1.25x"}

        return ClassificationResult(
            document_id=doc_id,
            predicted_type=best_type,  # type: ignore[arg-type]
            confidence=confidence,
            extracted_fields=extracted,
        )

    async def run_analysis(self, app_id: str) -> SynthesisOutput:
        """Fan-out to 3 agents, fan-in at synthesis, then route."""
        app = _applications.get(app_id)
        if not app:
            raise ValueError(f"Application {app_id} not found")

        status = _statuses.get(app_id)
        if status:
            status.phase = "agent_analysis"
            status.phases_completed.append("document_classification")
            status.phases_remaining = [p for p in status.phases_remaining if p != "document_classification"]

        from .agents import (
            get_agents,
            mock_financial_output,
            mock_legal_output,
            mock_market_output,
            mock_synthesis,
        )

        financial_agent, legal_agent, market_agent, synthesis_agent = get_agents()

        if financial_agent is not None:
            # Use real PydanticAI agents
            try:
                fin_result = await financial_agent.run(
                    f"Analyze credit for {app.borrower_name}, deal ${app.deal_amount_usd:,.0f}, "
                    f"industry {app.industry}, type {app.borrower_type}"
                )
                financial_out = fin_result.data

                leg_result = await legal_agent.run(
                    f"Review legal docs for {app.borrower_name}, docs: {app.document_ids}"
                )
                legal_out = leg_result.data

                mkt_result = await market_agent.run(
                    f"Market analysis for {app.industry} sector, borrower {app.borrower_name}"
                )
                market_out = mkt_result.data

                syn_result = await synthesis_agent.run(
                    f"Synthesize credit decision: financial={financial_out.model_dump()}, "
                    f"legal={legal_out.model_dump()}, market={market_out.model_dump()}"
                )
                synthesis = syn_result.data
            except Exception:
                logger.exception("Agent execution failed, falling back to mock")
                financial_out = mock_financial_output(app.borrower_name)
                legal_out = mock_legal_output(app.document_ids)
                market_out = mock_market_output(app.industry)
                synthesis = mock_synthesis(financial_out, legal_out, market_out)
        else:
            financial_out = mock_financial_output(app.borrower_name)
            legal_out = mock_legal_output(app.document_ids)
            market_out = mock_market_output(app.industry)
            synthesis = mock_synthesis(financial_out, legal_out, market_out)

        synthesis = self.route_decision(synthesis, app.deal_amount_usd)

        _results[app_id] = synthesis
        app.status = "analyzed"

        if status:
            status.phase = "synthesis" if not synthesis.escalate else "pending_review"
            status.phases_completed.extend(["agent_analysis", "synthesis"])
            status.phases_remaining = [p for p in status.phases_remaining if p not in ("agent_analysis", "synthesis")]
            if synthesis.escalate:
                status.phases_remaining = ["hitl_review", "decision"]
            else:
                status.phases_remaining = ["decision"]
                status.completed_at = datetime.now(UTC)

        if synthesis.escalate:
            _queue.append(
                {
                    "app_id": app_id,
                    "borrower_name": app.borrower_name,
                    "deal_amount_usd": app.deal_amount_usd,
                    "recommendation": synthesis.recommendation,
                    "confidence": synthesis.confidence,
                    "escalation_reason": synthesis.escalation_reason,
                    "queued_at": datetime.now(UTC).isoformat(),
                }
            )

        return synthesis

    def route_decision(self, synthesis: SynthesisOutput, deal_amount: float) -> SynthesisOutput:
        """Route decision: escalate if confidence < 0.75 or deal > $100M."""
        escalate = synthesis.confidence < 0.75 or deal_amount > 100_000_000
        reasons = []
        if synthesis.confidence < 0.75:
            reasons.append(f"low confidence ({synthesis.confidence:.0%})")
        if deal_amount > 100_000_000:
            reasons.append(f"large deal (${deal_amount:,.0f})")

        if escalate:
            synthesis.escalate = True
            synthesis.escalation_reason = "; ".join(reasons)
            synthesis.recommendation = "refer"

        return synthesis

    def get_status(self, app_id: str) -> PipelineStatus:
        """Get pipeline status for an application."""
        status = _statuses.get(app_id)
        if not status:
            raise ValueError(f"Application {app_id} not found")
        return status

    def get_result(self, app_id: str) -> SynthesisOutput | None:
        """Get analysis result for an application."""
        return _results.get(app_id)


class HITLService:
    """HITL review queue management."""

    def get_queue(self) -> list[dict[str, Any]]:
        """Get all items in the review queue."""
        return list(_queue)

    def submit_review(self, app_id: str, decision: HITLDecision) -> dict[str, str]:
        """Submit a human review decision."""
        _decisions[app_id] = decision

        app = _applications.get(app_id)
        if app:
            app.status = f"reviewed:{decision.decision}"

        status = _statuses.get(app_id)
        if status:
            status.phase = "decision"
            status.phases_completed.append("hitl_review")
            status.phases_remaining = []
            status.completed_at = datetime.now(UTC)

        # Remove from queue
        _queue[:] = [item for item in _queue if item["app_id"] != app_id]

        return {
            "app_id": app_id,
            "decision": decision.decision,
            "reviewer_id": decision.reviewer_id,
            "status": "accepted",
        }

    def get_decision(self, app_id: str) -> HITLDecision | None:
        """Get the HITL decision for an application."""
        return _decisions.get(app_id)
