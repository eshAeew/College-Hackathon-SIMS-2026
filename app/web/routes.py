"""Server-rendered web interface for API Sentinel (Stage 20).

Thin presentation layer: every figure shown here comes from DashboardService or
RunComparisonService, so the UI never computes its own verdicts.
"""
import logging
from pathlib import Path as FilePath

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models.entities.project import Project
from app.services.ai_recommendation_service import AIRecommendationService
from app.services.dashboard_service import DashboardService
from app.services.run_comparison_service import RunComparisonService

logger = logging.getLogger("app.web")
settings = get_settings()

TEMPLATES_DIR = FilePath(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(tags=["Web Interface"], include_in_schema=False)


@router.get("/ui", response_class=HTMLResponse, name="ui_dashboard")
def ui_dashboard(request: Request, db: Session = Depends(get_db)):
    """Global dashboard: KPI cards, recent runs, critical issues."""
    data = DashboardService.global_dashboard(db)
    projects = db.query(Project).order_by(Project.updated_at.desc()).all()
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "title": "Dashboard",
            "data": data,
            "projects": projects,
            "ai": AIRecommendationService.engine_status(),
            "version": settings.VERSION,
        },
    )


@router.get("/ui/projects/{project_id}", response_class=HTMLResponse, name="ui_project")
def ui_project(request: Request, project_id: int, db: Session = Depends(get_db)):
    """Project detail: endpoint health table, run feed, critical issues."""
    data = DashboardService.project_dashboard(db, project_id)
    if data is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Project #{project_id} not found.")
    return templates.TemplateResponse(
        request=request,
        name="project.html",
        context={"title": data.project_name, "data": data, "version": settings.VERSION},
    )


@router.get("/ui/endpoints/{endpoint_id}", response_class=HTMLResponse, name="ui_endpoint")
def ui_endpoint(request: Request, endpoint_id: int, db: Session = Depends(get_db)):
    """Endpoint inspector: contract, test cases, recent results."""
    data = DashboardService.endpoint_inspector(db, endpoint_id)
    if data is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Endpoint #{endpoint_id} not found.")
    return templates.TemplateResponse(
        request=request,
        name="endpoint.html",
        context={"title": data.name, "data": data, "version": settings.VERSION},
    )


@router.get("/ui/results/{result_id}", response_class=HTMLResponse, name="ui_result")
def ui_result(request: Request, result_id: int, db: Session = Depends(get_db)):
    """Result detail: evidence bundle plus the remediation card."""
    data = DashboardService.result_detail(db, result_id, include_recommendation=True)
    if data is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"TestResult #{result_id} not found.")
    return templates.TemplateResponse(
        request=request,
        name="result.html",
        context={"title": data.test_name, "data": data, "version": settings.VERSION},
    )


@router.get("/ui/projects/{project_id}/compare", response_class=HTMLResponse, name="ui_compare")
def ui_compare(
    request: Request,
    project_id: int,
    run_a: int = Query(default=0, description="Baseline run id (0 = auto)"),
    run_b: int = Query(default=0, description="Current run id (0 = auto)"),
    db: Session = Depends(get_db),
):
    """Side-by-side run comparison with the delta visualizer."""
    if not run_a or not run_b:
        pair = RunComparisonService.latest_two_run_ids(db, project_id)
        if pair is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                f"Project #{project_id} needs at least two runs to compare.",
            )
        run_a, run_b = pair

    view = RunComparisonService.visualize(db, run_a, run_b)
    report = RunComparisonService.compare_runs(db, run_a, run_b, project_id=project_id)
    if view is None or report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "One or both runs were not found.")

    return templates.TemplateResponse(
        request=request,
        name="compare.html",
        context={
            "title": "Run Comparison",
            "view": view,
            "report": report,
            "project_id": project_id,
            "version": settings.VERSION,
        },
    )
