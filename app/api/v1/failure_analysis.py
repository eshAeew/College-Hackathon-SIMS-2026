"""Failure Analysis Engine API endpoints (Stage 18)."""
from fastapi import APIRouter, Depends, HTTPException, Path, status
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

router = APIRouter(tags=["Failure Analysis Engine"])


@router.post(
    "/failure-analysis/package",
    response_model=StandardResponse[FailureEvidence],
    status_code=status.HTTP_200_OK,
    summary="Package Failure Evidence",
    description=(
        "Transforms a raw execution snapshot into a self-contained diagnostic evidence "
        "bundle: masked request/response detail, a cURL reproduction command, rule-based "
        "root-cause categorization, severity, and historical recurrence context."
    )
)
def package_failure_evidence(req: PackageEvidenceRequest):
    """Build a standardized FailureEvidence bundle from an ad-hoc execution snapshot."""
    evidence = FailureAnalysisService.package_adhoc(req)
    return StandardResponse(
        success=True,
        data=evidence,
        message=(
            f"Packaged evidence {evidence.evidence_id}: "
            f"{evidence.root_cause.category.value} ({evidence.severity.value})"
        )
    )


@router.post(
    "/failure-analysis/categorize",
    response_model=StandardResponse[RootCauseAssessment],
    status_code=status.HTTP_200_OK,
    summary="Categorize Failure Root Cause",
    description="Applies the deterministic failure taxonomy to raw execution signals."
)
def categorize_failure(req: CategorizeFailureRequest):
    """Assign a root-cause category, confidence, and remediation hint."""
    assessment = FailureAnalysisService.categorize(req)
    return StandardResponse(
        success=True,
        data=assessment,
        message=f"Categorized as {assessment.category.value} ({assessment.confidence_pct}% confidence)"
    )


@router.get(
    "/results/{result_id}/evidence",
    response_model=StandardResponse[FailureEvidence],
    summary="Evidence Bundle for a Stored Result",
    description="Packages a persisted TestResult row into a diagnostic evidence bundle."
)
def get_result_evidence(
    result_id: int = Path(..., ge=1, description="TestResult primary key"),
    db: Session = Depends(get_db)
):
    """Return the evidence bundle for one stored execution result."""
    evidence = FailureAnalysisService.package_from_result(db, result_id)
    if evidence is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"TestResult #{result_id} not found."
        )
    return StandardResponse(
        success=True,
        data=evidence,
        message=f"Evidence {evidence.evidence_id} for '{evidence.test_name}'"
    )


@router.get(
    "/runs/{run_id}/failure-analysis",
    response_model=StandardResponse[RunFailureAnalysisReport],
    summary="Run-Wide Failure Analysis",
    description=(
        "Packages every failing result in a run and summarizes the category and "
        "severity distribution."
    )
)
def analyze_run_failures(
    run_id: int = Path(..., ge=1, description="TestRun primary key"),
    db: Session = Depends(get_db)
):
    """Return packaged evidence for all failures recorded in a run."""
    report = FailureAnalysisService.analyze_run(db, run_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"TestRun #{run_id} not found."
        )
    return StandardResponse(
        success=True,
        data=report,
        message=f"Analyzed {report.total_failures} failure(s) across {report.total_results} result(s)"
    )
