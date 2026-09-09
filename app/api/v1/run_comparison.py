"""Run Comparison & Diff API endpoints (Stage 21)."""
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.schemas.response import StandardResponse
from app.models.schemas.run_comparison import DeltaVisualization, RunComparisonReport
from app.services.run_comparison_service import RunComparisonService

router = APIRouter(tags=["Run Comparison & Diff"])


@router.get(
    "/projects/{project_id}/compare-runs",
    response_model=StandardResponse[RunComparisonReport],
    summary="Compare Two Runs Side by Side",
    description=(
        "Contrasts a baseline run against a current run: pass-rate and latency deltas, "
        "per-test status changes (broken, fixed, slower, faster, added, removed), and an "
        "overall net quality delta."
    )
)
def compare_runs(
    project_id: int = Path(..., ge=1, description="Owning project"),
    run_a: int = Query(..., ge=1, description="Baseline run id"),
    run_b: int = Query(..., ge=1, description="Current run id"),
    db: Session = Depends(get_db)
):
    """Return the structured comparison between two runs."""
    report = RunComparisonService.compare_runs(db, run_a, run_b, project_id=project_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run #{run_a} or Run #{run_b} not found."
        )
    return StandardResponse(success=True, data=report, message=report.headline)


@router.get(
    "/projects/{project_id}/compare-runs/visualize",
    response_model=StandardResponse[DeltaVisualization],
    summary="Delta Visualization View-Model",
    description=(
        "Returns the badge strip, regression and improvement lists, latency shift, and "
        "pass-rate series used to render the visual diff."
    )
)
def visualize_comparison(
    project_id: int = Path(..., ge=1, description="Owning project"),
    run_a: int = Query(..., ge=1, description="Baseline run id"),
    run_b: int = Query(..., ge=1, description="Current run id"),
    db: Session = Depends(get_db)
):
    """Return the rendered delta view-model for two runs."""
    view = RunComparisonService.visualize(db, run_a, run_b)
    if view is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run #{run_a} or Run #{run_b} not found."
        )
    return StandardResponse(success=True, data=view, message=view.headline)


@router.get(
    "/projects/{project_id}/compare-runs/latest",
    response_model=StandardResponse[RunComparisonReport],
    summary="Compare the Two Most Recent Runs",
    description="Automatically diffs the latest run against the one before it."
)
def compare_latest_runs(
    project_id: int = Path(..., ge=1, description="Owning project"),
    db: Session = Depends(get_db)
):
    """Compare a project's two most recent runs without naming ids."""
    pair = RunComparisonService.latest_two_run_ids(db, project_id)
    if pair is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project #{project_id} needs at least two runs to compare."
        )
    baseline_id, current_id = pair
    report = RunComparisonService.compare_runs(db, baseline_id, current_id, project_id=project_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comparison could not be built for the latest runs."
        )
    return StandardResponse(success=True, data=report, message=report.headline)
