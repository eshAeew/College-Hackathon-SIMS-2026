"""Dashboard aggregation API endpoints (Stage 20)."""
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.schemas.dashboard import (
    EndpointInspector,
    GlobalDashboard,
    ProjectDashboard,
    ResultDetailView,
)
from app.models.schemas.response import StandardResponse
from app.services.dashboard_service import DashboardService

router = APIRouter(tags=["Dashboard & Web Interface"])


@router.get(
    "/dashboard",
    response_model=StandardResponse[GlobalDashboard],
    summary="Global Dashboard",
    description=(
        "KPI cards (total executions, pass rate, average latency, active failures), the "
        "recent test-run feed, and the critical-issues alert banner across all projects."
    )
)
def global_dashboard(
    recent_limit: int = Query(default=10, ge=1, le=50, description="Feed size"),
    db: Session = Depends(get_db)
):
    """Return the aggregated global dashboard view-model."""
    data = DashboardService.global_dashboard(db, recent_limit=recent_limit)
    return StandardResponse(
        success=True,
        data=data,
        message=(
            f"{data.total_projects} project(s), {data.total_executions} execution(s), "
            f"{data.global_pass_rate_pct:.1f}% pass rate"
        )
    )


@router.get(
    "/dashboard/projects/{project_id}",
    response_model=StandardResponse[ProjectDashboard],
    summary="Project Dashboard",
    description="Endpoint health table, recent runs, and critical issues for one project."
)
def project_dashboard(
    project_id: int = Path(..., ge=1, description="Project primary key"),
    recent_limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db)
):
    """Return the project drill-down view-model."""
    data = DashboardService.project_dashboard(db, project_id, recent_limit=recent_limit)
    if data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project #{project_id} not found."
        )
    return StandardResponse(
        success=True,
        data=data,
        message=(
            f"'{data.project_name}': {data.total_endpoints} endpoint(s), "
            f"{data.pass_rate_pct:.1f}% pass rate"
        )
    )


@router.get(
    "/dashboard/endpoints/{endpoint_id}",
    response_model=StandardResponse[EndpointInspector],
    summary="Endpoint Inspector",
    description="Request configuration, assertion rules, and recent historical results."
)
def endpoint_inspector(
    endpoint_id: int = Path(..., ge=1, description="Endpoint primary key"),
    recent_limit: int = Query(default=15, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Return the endpoint inspector view-model."""
    data = DashboardService.endpoint_inspector(db, endpoint_id, recent_limit=recent_limit)
    if data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Endpoint #{endpoint_id} not found."
        )
    return StandardResponse(
        success=True,
        data=data,
        message=f"[{data.method}] {data.path}: {len(data.test_cases)} test case(s)"
    )


@router.get(
    "/dashboard/results/{result_id}",
    response_model=StandardResponse[ResultDetailView],
    summary="Test Result Detail",
    description=(
        "Full diagnostic view for one execution: status, timing, packaged failure evidence, "
        "and the AI (or heuristic) remediation card."
    )
)
def result_detail(
    result_id: int = Path(..., ge=1, description="TestResult primary key"),
    include_recommendation: bool = Query(default=True, description="Attach the remediation card"),
    db: Session = Depends(get_db)
):
    """Return the result detail view-model with evidence and recommendation."""
    data = DashboardService.result_detail(
        db, result_id, include_recommendation=include_recommendation
    )
    if data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"TestResult #{result_id} not found."
        )
    return StandardResponse(
        success=True,
        data=data,
        message=f"'{data.test_name}' -> {data.status}"
    )
