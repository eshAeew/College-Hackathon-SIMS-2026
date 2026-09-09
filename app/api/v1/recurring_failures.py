"""API Router for Recurring Failure Detection & Pattern Clustering (Stage 11)."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.schemas.recurring_failure import (
    AnalyzeHistoricalFailuresRequest,
    EndpointFailureRecurrence,
    ProjectRecurringFailureReport,
)
from app.models.schemas.response import StandardResponse
from app.services.recurring_failure_service import RecurringFailureService

router = APIRouter(prefix="/recurring-failures", tags=["Recurring Failure Detection"])


@router.post(
    "/analyze",
    response_model=StandardResponse[ProjectRecurringFailureReport],
    summary="Cluster & Analyze Historical Failure Samples",
    description="Aggregates raw execution samples across endpoints, calculates persistence ratings ('Chronic', 'Intermittent', 'New'), and clusters common root-cause fingerprints."
)
async def analyze_failure_samples(request: AnalyzeHistoricalFailuresRequest):
    """Analyze historical execution samples for failure streaks and root-cause clusters."""
    try:
        report = RecurringFailureService.analyze_batch_samples(request)
        return StandardResponse(
            success=True,
            data=report,
            message=f"Analyzed {report.total_analyzed_runs} runs across {report.total_endpoints} endpoint(s) - Found {len(report.failure_clusters)} failure cluster(s)"
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failure analysis failed: {str(exc)}"
        )


@router.get(
    "/projects/{project_id}",
    response_model=StandardResponse[ProjectRecurringFailureReport],
    summary="Get Project Recurring Failures & Clusters",
    description="Fetches comprehensive failure frequency metrics, chronic flapping endpoints, and root-cause clusters for a project workspace."
)
async def get_project_recurring_failures(
    project_id: int,
    window_size: int = Query(10, ge=2, le=100, description="Analysis window size in runs"),
    db: Session = Depends(get_db)
):
    """Retrieve recurring failure metrics for a project."""
    try:
        report = RecurringFailureService.analyze_project_recurrence(
            project_id=project_id,
            db=db,
            window_size=window_size
        )
        return StandardResponse(
            success=True,
            data=report,
            message=f"Retrieved recurring failure analysis for Project #{project_id}"
        )
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(val_err)
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch project recurring failures: {str(exc)}"
        )


@router.get(
    "/endpoints/{endpoint_id}",
    response_model=StandardResponse[EndpointFailureRecurrence],
    summary="Get Endpoint Failure Recurrence & Streak",
    description="Retrieves consecutive failure streak, flapping status, and persistence rating for a single endpoint."
)
async def get_endpoint_recurring_failures(
    endpoint_id: int,
    window_size: int = Query(10, ge=2, le=100, description="Analysis window size"),
    db: Session = Depends(get_db)
):
    """Retrieve failure recurrence metrics for an individual endpoint."""
    try:
        result = RecurringFailureService.analyze_endpoint_recurrence(
            endpoint_id=endpoint_id,
            db=db,
            window_size=window_size
        )
        return StandardResponse(
            success=True,
            data=result,
            message=f"Retrieved recurrence metrics for Endpoint #{endpoint_id} - Rating: {result.persistence_rating.value}"
        )
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(val_err)
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch endpoint recurring failures: {str(exc)}"
        )