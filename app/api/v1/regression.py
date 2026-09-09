"""FastAPI REST router for Regression Testing Engine and Delta Comparator."""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.schemas.regression import (
    DirectRegressionComparisonRequest,
    ProjectRegressionReport,
)
from app.models.schemas.response import StandardResponse
from app.services.regression_service import RegressionService

logger = logging.getLogger("app.api.v1.regression")
router = APIRouter(tags=["Regression Testing Engine"])


@router.post(
    "/regression/compare",
    response_model=StandardResponse[ProjectRegressionReport],
    summary="Ad-Hoc Regression Delta Comparison",
    description="Compares two sets of test execution results directly without database records."
)
def compare_direct_batches(
    req: DirectRegressionComparisonRequest
):
    """Direct comparison of two arbitrary execution lists."""
    report = RegressionService.compare_direct_batches(req)
    return StandardResponse(
        success=True,
        data=report,
        message=f"Comparison complete: {report.summary.total_regressions} regression(s) detected (Verdict: {report.summary.verdict.value})"
    )


@router.get(
    "/runs/{run_id}/regression",
    response_model=StandardResponse[ProjectRegressionReport],
    summary="Evaluate Run Regressions against Baseline",
    description="Compares the specified Test Run against an explicit or auto-detected baseline run."
)
def evaluate_run_regression(
    run_id: int,
    baseline_run_id: Optional[int] = Query(None, description="Optional explicit baseline run ID"),
    latency_threshold_pct: float = Query(50.0, ge=5.0, le=1000.0, description="Latency degradation alert threshold %"),
    db: Session = Depends(get_db)
):
    """Compare a test run with a baseline."""
    try:
        report = RegressionService.compare_runs_by_id(
            current_run_id=run_id,
            db=db,
            baseline_run_id=baseline_run_id,
            latency_threshold_pct=latency_threshold_pct
        )
        return StandardResponse(
            success=True,
            data=report,
            message=f"Evaluated Run #{run_id} against Baseline: {report.summary.total_regressions} regression(s) detected"
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get(
    "/projects/{project_id}/regressions/latest",
    response_model=StandardResponse[ProjectRegressionReport],
    summary="Latest Project Regression Report",
    description="Auto-detects the latest run in a project and compares it with its preceding baseline."
)
def get_latest_project_regression(
    project_id: int,
    latency_threshold_pct: float = Query(50.0, ge=5.0, le=1000.0, description="Latency degradation alert threshold %"),
    db: Session = Depends(get_db)
):
    """Retrieve regression report for the latest run of a project."""
    try:
        report = RegressionService.get_latest_project_regression(
            project_id=project_id,
            db=db,
            latency_threshold_pct=latency_threshold_pct
        )
        return StandardResponse(
            success=True,
            data=report,
            message=f"Retrieved regression analysis for latest run of Project #{project_id}"
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
