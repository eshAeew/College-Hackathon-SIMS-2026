"""FastAPI Router for Failure Analysis Engine (Stage 18)."""
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.schemas.failure_analysis import (
    CategorizeFailureRequest,
    FailureEvidence,
    PackageEvidenceRequest,
    RootCauseAssessment,
    RunFailureAnalysisReport,
)
from app.models.schemas.response import StandardResponse
from app.services.failure_analysis_service import FailureAnalysisService

logger = logging.getLogger("app.api.v1.failure_analysis")
router = APIRouter(prefix="", tags=["Failure Analysis Engine"])


@router.post(
    "/failure-analysis/package",
    response_model=StandardResponse[FailureEvidence],
    summary="Package ad-hoc failure evidence",
    description="Builds a sanitized, self-contained diagnostic evidence bundle from execution telemetry."
)
def package_evidence(req: PackageEvidenceRequest):
    """Package raw telemetry into a reproducible failure evidence bundle."""
    evidence = FailureAnalysisService.package_adhoc(req)
    return StandardResponse(
        success=True,
        data=evidence,
        message="Failure evidence packaged successfully with credential masking and reproduction details."
    )


@router.post(
    "/failure-analysis/categorize",
    response_model=StandardResponse[RootCauseAssessment],
    summary="Categorize failure root cause",
    description="Evaluates failure signals against the 13-category taxonomy with confidence scoring."
)
def categorize_failure(req: CategorizeFailureRequest):
    """Classify failure signals into root-cause category and troubleshooting recommendation."""
    assessment = FailureAnalysisService.categorize(req)
    return StandardResponse(
        success=True,
        data=assessment,
        message=f"Failure classified as {assessment.category.value} ({assessment.confidence_pct}% confidence)."
    )


@router.get(
    "/results/{result_id}/evidence",
    response_model=StandardResponse[FailureEvidence],
    summary="Get failure evidence for a TestResult",
    description="Builds a diagnostic evidence bundle from a persisted TestResult database row."
)
def get_result_evidence(result_id: int, db: Session = Depends(get_db)):
    """Retrieve full diagnostic evidence for a specific test result."""
    evidence = FailureAnalysisService.package_from_result(db, result_id)
    if not evidence:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"TestResult #{result_id} not found."
        )
    return StandardResponse(
        success=True,
        data=evidence,
        message="Test result failure evidence retrieved successfully."
    )


@router.get(
    "/runs/{run_id}/failure-analysis",
    response_model=StandardResponse[RunFailureAnalysisReport],
    summary="Get failure analysis for a TestRun",
    description="Aggregates and summarizes all failure evidence bundles across an entire test run."
)
def get_run_failure_analysis(run_id: int, db: Session = Depends(get_db)):
    """Summarize and package all failures encountered in a test run."""
    report = FailureAnalysisService.analyze_run(db, run_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"TestRun #{run_id} not found."
        )
    return StandardResponse(
        success=True,
        data=report,
        message=f"Analyzed {report.total_failures} failure(s) in TestRun #{run_id}."
    )
