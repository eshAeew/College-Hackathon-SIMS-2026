"""FastAPI REST router for the AI Recommendation Layer (Stage 19)."""
import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.schemas.ai_recommendation import (
    AIEngineStatus,
    FixRecommendation,
    SynthesizedPrompt,
)
from app.models.schemas.failure_analysis import FailureEvidence, PackageEvidenceRequest
from app.models.schemas.response import StandardResponse
from app.services.ai_recommendation_service import AIRecommendationService

logger = logging.getLogger("app.api.v1.ai_recommendations")
router = APIRouter(prefix="", tags=["AI Recommendation Layer"])


@router.get(
    "/ai/status",
    response_model=StandardResponse[AIEngineStatus],
    summary="Check AI Recommendation Engine Status",
    description="Returns whether Google Gemini is active or if the system is using the deterministic rule-based engine."
)
def get_ai_status():
    """Probe the active recommendation engine configuration and status."""
    status_info = AIRecommendationService.engine_status()
    return StandardResponse(
        success=True,
        data=status_info,
        message=f"Active recommendation engine: {status_info.active_engine.value}."
    )


@router.post(
    "/ai/synthesize-prompt",
    response_model=StandardResponse[SynthesizedPrompt],
    summary="Synthesize LLM Prompt from Evidence",
    description="Generates the structured system and user prompts with guardrails enforcing strict JSON response contracts."
)
def synthesize_llm_prompt(evidence: FailureEvidence):
    """Generate structured LLM prompt bundle from a FailureEvidence package."""
    prompt = AIRecommendationService.synthesize(evidence)
    return StandardResponse(
        success=True,
        data=prompt,
        message="Structured LLM prompt synthesized successfully with strict JSON contract."
    )


@router.post(
    "/ai/recommend",
    response_model=StandardResponse[FixRecommendation],
    summary="Generate Remediation Proposal from Evidence",
    description="Generates actionable root cause diagnosis, step-by-step fix instructions, and code snippets."
)
def generate_recommendation_from_evidence(
    evidence: FailureEvidence,
    persist: bool = Query(default=False, description="Persist recommendation to database"),
    db: Session = Depends(get_db)
):
    """Generate remediation proposal using Gemini LLM or deterministic fallback."""
    rec = AIRecommendationService.generate(evidence, db=db, persist=persist)
    return StandardResponse(
        success=True,
        data=rec,
        message=f"Remediation generated via {rec.source.value} ({rec.confidence_pct}% confidence)."
    )


@router.post(
    "/ai/recommend-from-snapshot",
    response_model=StandardResponse[FixRecommendation],
    summary="Package & Recommend in Single Step",
    description="Accepts raw telemetry, builds the evidence bundle, and outputs the remediation proposal."
)
def recommend_from_snapshot(
    req: PackageEvidenceRequest,
    persist: bool = Query(default=False, description="Persist recommendation to database"),
    db: Session = Depends(get_db)
):
    """Package raw telemetry snapshot and generate fix recommendation in one call."""
    rec = AIRecommendationService.generate_from_snapshot(req, db=db, persist=persist)
    return StandardResponse(
        success=True,
        data=rec,
        message=f"Remediation card generated via {rec.source.value}."
    )


@router.post(
    "/results/{result_id}/recommendation",
    response_model=StandardResponse[FixRecommendation],
    summary="Generate & Attach Recommendation to TestResult",
    description="Extracts evidence from a persisted TestResult and generates/stores its remediation card."
)
def recommend_for_test_result(
    result_id: int,
    persist: bool = Query(default=True, description="Persist recommendation to database"),
    db: Session = Depends(get_db)
):
    """Generate remediation proposal for a specific persisted test result."""
    rec = AIRecommendationService.recommend_for_result(db, result_id, persist=persist)
    if not rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"TestResult #{result_id} not found."
        )
    return StandardResponse(
        success=True,
        data=rec,
        message=f"Remediation proposal generated for TestResult #{result_id}."
    )


@router.get(
    "/results/{result_id}/recommendations",
    response_model=StandardResponse[List[dict]],
    summary="List Stored Recommendations for TestResult",
    description="Retrieves all historical remediation proposals saved for a specific test result."
)
def get_recommendations_for_test_result(result_id: int, db: Session = Depends(get_db)):
    """List all persisted remediation proposals for a test result."""
    records = AIRecommendationService.for_result(db, result_id)
    serialized = [
        {
            "id": r.id,
            "test_result_id": r.test_result_id,
            "evidence_id": r.evidence_id,
            "root_cause_category": r.root_cause_category,
            "likely_cause": r.likely_cause,
            "severity": r.severity,
            "suggested_fix": r.suggested_fix,
            "code_snippet": r.code_snippet,
            "confidence_pct": r.confidence_pct,
            "source": r.source,
            "model_name": r.model_name,
            "references": r.references,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in records
    ]
    return StandardResponse(
        success=True,
        data=serialized,
        message=f"Retrieved {len(serialized)} stored recommendation(s)."
    )
