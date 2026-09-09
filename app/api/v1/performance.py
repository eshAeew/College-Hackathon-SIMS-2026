"""API Router for Performance Analysis & SLA Benchmarking (Stage 10)."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.schemas.performance import (
    AnalyzeLatencyBatchRequest,
    DirectBenchmarkRequest,
    EndpointBenchmarkRequest,
    PerformanceReport,
)
from app.models.schemas.response import StandardResponse
from app.services.performance_service import PerformanceService

router = APIRouter(prefix="/performance", tags=["Performance & SLA Analysis"])


@router.post(
    "/benchmark-direct",
    response_model=StandardResponse[PerformanceReport],
    summary="Benchmark Direct HTTP Target",
    description="Dispatches N repetitions against an arbitrary URL, computes sub-millisecond percentiles (P50, P90, P95, P99), and grades SLA threshold compliance."
)
async def benchmark_direct(request: DirectBenchmarkRequest):
    """Execute live performance benchmark and SLA analysis for ad-hoc requests."""
    try:
        report = await PerformanceService.benchmark_direct(request)
        return StandardResponse(
            success=True,
            data=report,
            message=f"Benchmark completed ({report.total_requests} runs) - Rating: {report.sla_result.rating.value} (Compliance: {report.sla_result.compliance_percentage}%)"
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Performance benchmark failed: {str(exc)}"
        )


@router.post(
    "/endpoints/{endpoint_id}/benchmark",
    response_model=StandardResponse[PerformanceReport],
    summary="Benchmark Workspace Endpoint",
    description="Executes a multi-run performance benchmark against a registered database endpoint and evaluates SLA compliance."
)
async def benchmark_endpoint(
    endpoint_id: int,
    request: EndpointBenchmarkRequest,
    db: Session = Depends(get_db)
):
    """Execute live performance benchmark and SLA analysis for a stored endpoint."""
    try:
        report = await PerformanceService.benchmark_endpoint(
            endpoint_id=endpoint_id,
            req=request,
            db=db
        )
        return StandardResponse(
            success=True,
            data=report,
            message=f"Endpoint #{endpoint_id} Benchmark completed - Rating: {report.sla_result.rating.value} (Compliance: {report.sla_result.compliance_percentage}%)"
        )
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(val_err)
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Endpoint performance benchmark failed: {str(exc)}"
        )


@router.post(
    "/analyze",
    response_model=StandardResponse[PerformanceReport],
    summary="Analyze Latency Batch & SLA Rules",
    description="Calculates percentiles (P50, P90, P95, P99), jitter, standard deviation, and SLA threshold violations from pre-collected latency arrays."
)
async def analyze_latency_batch(request: AnalyzeLatencyBatchRequest):
    """Evaluate pre-recorded latency values against an SLA policy."""
    try:
        report = PerformanceService.analyze_batch(request)
        return StandardResponse(
            success=True,
            data=report,
            message=f"Analyzed {report.total_requests} samples - Rating: {report.sla_result.rating.value} (Compliance: {report.sla_result.compliance_percentage}%)"
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to analyze latency batch: {str(exc)}"
        )