"""AI Recommendation Layer API endpoints (Stage 19)."""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.schemas.ai_recommendation import (
    AIEngineStatus,
    AIRecommendationResponse,
    FixRecommendation,
    RecommendFromEvidenceRequest,
    RecommendFromSnapshotRequest,
    SynthesizedPrompt,
)
from app.models.schemas.failure_analysis import FailureEvidence
from app.models.schemas.response import StandardResponse
from app.services.ai_recommendation_service import AIRecommendationService

router = APIRouter(tags=["AI Recommendation Layer"])


@router.get(
    "/ai/status",
    response_model=StandardResponse[AIEngineStatus],
    summary="Active Recommendation Engine",
    description=(
        "Reports whether the Gemini LLM or the offline rule-based engine will answer the "
        "next recommendation request. The platform remains fully functional either way."
    )
)
def ai_engine_status():
    """Expose which diagnostic engine is currently active."""
    info = AIRecommendationService.engine_status()
    return StandardResponse(success=True, data=info, message=info.message)


@router.post(
    "/ai/synthesize-prompt",
    response_model=StandardResponse[SynthesizedPrompt],
    summary="Synthesize Diagnostic Prompt",
    description=(
        "Builds the exact system/user prompt pair that would be sent to the LLM for a "
        "packaged failure, including the enforced JSON response schema and a token estimate."
    )
)
def synthesize_prompt_endpoint(evidence: FailureEvidence):
    """Return the structured prompt for a failure evidence bundle."""
    prompt = AIRecommendationService.synthesize(evidence)
    return StandardResponse(
        success=True,
        data=prompt,
        message=f"Prompt synthesized (~{prompt.estimated_tokens} tokens)"
    )


@router.post(
    "/ai/recommend",
    response_model=StandardResponse[FixRecommendation],
    summary="Recommend Fix From Evidence",
    description="Generates a remediation card from an already-packaged evidence bundle."
)
def recommend_from_evidence_endpoint(
    req: RecommendFromEvidenceRequest,
    db: Session = Depends(get_db)
):
    """Explain a failure and propose a concrete fix."""
    card = AIRecommendationService.generate(
        req.evidence, db=db, persist=req.persist, test_result_id=req.test_result_id
    )
    return StandardResponse(
        success=True,
        data=card,
        message=f"{card.source.value} recommendation ({card.severity.value})"
    )


@router.post(
    "/ai/recommend-from-snapshot",
    response_model=StandardResponse[FixRecommendation],
    summary="Package Evidence and Recommend",
    description="Packages a raw execution snapshot into evidence and returns a remediation card."
)
def recommend_from_snapshot_endpoint(
    req: RecommendFromSnapshotRequest,
    db: Session = Depends(get_db)
):
    """One-call path from raw failure signals to an actionable fix."""
    card = AIRecommendationService.generate_from_snapshot(
        req, db=db, persist=req.persist, test_result_id=req.test_result_id
    )
    return StandardResponse(
        success=True,
        data=card,
        message=f"{card.source.value} recommendation ({card.severity.value})"
    )


@router.post(
    "/results/{result_id}/recommendation",
    response_model=StandardResponse[FixRecommendation],
    summary="Explain a Stored Failure",
    description="Packages a persisted TestResult and generates (and stores) its remediation card."
)
def recommend_for_result_endpoint(
    result_id: int = Path(..., ge=1, description="TestResult primary key"),
    persist: bool = Query(default=True, description="Store the generated recommendation"),
    db: Session = Depends(get_db)
):
    """Generate a remediation card for one stored execution result."""
    card = AIRecommendationService.recommend_for_result(db, result_id, persist=persist)
    if card is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"TestResult #{result_id} not found."
        )
    return StandardResponse(
        success=True,
        data=card,
        message=f"{card.source.value} recommendation ({card.severity.value})"
    )


@router.get(
    "/results/{result_id}/recommendations",
    response_model=StandardResponse[List[AIRecommendationResponse]],
    summary="Stored Recommendations for a Result",
    description="Lists previously generated recommendations attached to a test result."
)
def list_result_recommendations(
    result_id: int = Path(..., ge=1, description="TestResult primary key"),
    db: Session = Depends(get_db)
):
    """Return the recommendation history for one result."""
    rows = AIRecommendationService.for_result(db, result_id)
    data = [AIRecommendationResponse.model_validate(row) for row in rows]
    return StandardResponse(
        success=True,
        data=data,
        message=f"Retrieved {len(data)} stored recommendation(s)"
    )
