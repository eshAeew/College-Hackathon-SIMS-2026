"""FastAPI router for Stage 21: Run Comparison & Diff Tool."""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.schemas.response import StandardResponse
from app.models.schemas.run_comparison import RunComparisonReport, RunComparisonRequest
from app.services.run_comparison_service import RunComparisonService

logger = logging.getLogger("app.api.v1.run_comparison")

comparison_router = APIRouter(tags=["Run Comparison & Diff"])


@comparison_router.get(
    "/runs/compare",
    response_model=StandardResponse[RunComparisonReport],
    summary="Compare Two Test Runs (Query Params)",
    description="Compares base_run_id vs target_run_id, returning side-by-side metrics and test deltas."
)
def compare_runs_get(
    base_run_id: int = Query(..., description="Previous / baseline TestRun ID"),
    target_run_id: int = Query(..., description="Current / target TestRun ID"),
    latency_threshold_pct: float = Query(25.0, ge=1.0, description="Percentage threshold for latency drift"),
    min_latency_delta_ms: float = Query(50.0, ge=0.0, description="Minimum absolute ms delta for latency drift"),
    db: Session = Depends(get_db)
):
    """Execute side-by-side run comparison via GET query parameters."""
    try:
        report = RunComparisonService.compare_runs(
            db=db,
            base_run_id=base_run_id,
            target_run_id=target_run_id,
            latency_threshold_pct=latency_threshold_pct,
            min_latency_delta_ms=min_latency_delta_ms
        )
        return StandardResponse(
            success=True,
            data=report,
            message=f"Comparison report generated for Run #{base_run_id} vs Run #{target_run_id}."
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc)
        )


@comparison_router.post(
    "/runs/compare",
    response_model=StandardResponse[RunComparisonReport],
    summary="Compare Two Test Runs (JSON Payload)",
    description="Compares two runs specified in request payload."
)
def compare_runs_post(
    req: RunComparisonRequest,
    db: Session = Depends(get_db)
):
    """Execute side-by-side run comparison via POST JSON body."""
    try:
        report = RunComparisonService.compare_runs(
            db=db,
            base_run_id=req.base_run_id,
            target_run_id=req.target_run_id,
            latency_threshold_pct=req.latency_threshold_pct,
            min_latency_delta_ms=req.min_latency_delta_ms
        )
        return StandardResponse(
            success=True,
            data=report,
            message=f"Comparison report generated for Run #{req.base_run_id} vs Run #{req.target_run_id}."
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc)
        )
