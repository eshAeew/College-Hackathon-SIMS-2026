"""Inconsistent Behavior & Flakiness Detection API Endpoints."""
from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.schemas.response import StandardResponse
from app.models.schemas.inconsistent_behavior import (
    MultiExecutionRequest,
    EndpointMultiExecutionRequest,
    AnalyzeBatchRequest,
    FlakinessReport,
)
from app.services.inconsistency_service import InconsistencyService

router = APIRouter(prefix="/inconsistency", tags=["Inconsistent Behavior & Flakiness Detection"])


@router.post(
    "/execute-direct",
    response_model=StandardResponse[FlakinessReport],
    status_code=status.HTTP_200_OK,
    summary="Multi-Run Repetitive Execution on Direct Request",
    description="Executes an ad-hoc HTTP request N times (sequential or concurrent) to compute latency variance (P95, P99, Jitter), status code entropy, payload drift, and flakiness score."
)
async def execute_direct_multi_run_endpoint(
    req: MultiExecutionRequest
) -> StandardResponse[FlakinessReport]:
    """Execute repetitive multi-run analysis on ad-hoc request."""
    report = await InconsistencyService.run_direct_multi_execution(req)
    return StandardResponse(
        success=(not report.is_flaky),
        data=report,
        message=report.summary
    )


@router.post(
    "/endpoints/{endpoint_id}/execute",
    response_model=StandardResponse[FlakinessReport],
    status_code=status.HTTP_200_OK,
    summary="Multi-Run Repetitive Execution on Stored Endpoint",
    description="Executes a stored workspace endpoint N times to uncover non-deterministic status switching, response payload drift, or latency jitter."
)
async def execute_endpoint_multi_run_endpoint(
    endpoint_id: int = Path(..., description="Target Endpoint ID", ge=1),
    req: EndpointMultiExecutionRequest = ...,
    db: Session = Depends(get_db)
) -> StandardResponse[FlakinessReport]:
    """Execute repetitive multi-run analysis on stored endpoint."""
    report = await InconsistencyService.run_endpoint_multi_execution(endpoint_id, req, db)
    return StandardResponse(
        success=(not report.is_flaky),
        data=report,
        message=report.summary
    )


@router.post(
    "/analyze",
    response_model=StandardResponse[FlakinessReport],
    status_code=status.HTTP_200_OK,
    summary="Analyze Existing Batch of Iteration Results",
    description="Calculates statistical latency percentiles (P95, P99), Shannon entropy, and flakiness risk score from externally collected execution iteration results."
)
async def analyze_batch_endpoint(
    req: AnalyzeBatchRequest
) -> StandardResponse[FlakinessReport]:
    """Analyze provided batch of iteration records."""
    report = InconsistencyService.analyze_batch(req)
    return StandardResponse(
        success=(not report.is_flaky),
        data=report,
        message=report.summary
    )
