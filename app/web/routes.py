"""FastAPI router serving the Web UI and Dashboard Aggregator APIs (Stage 20)."""
import logging
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models.schemas.dashboard import DashboardOverviewResponse, ProjectDetailView
from app.models.schemas.response import StandardResponse
from app.services.dashboard_service import DashboardService

logger = logging.getLogger("app.web.routes")
settings = get_settings()

web_router = APIRouter(tags=["Web Dashboard"])
dashboard_api_router = APIRouter(prefix="/dashboard", tags=["Dashboard Aggregator"])

TEMPLATE_PATH = Path(__file__).parent / "templates" / "dashboard.html"
WELCOME_TEMPLATE_PATH = Path(__file__).parent / "templates" / "welcome.html"


def _render_template(path: Path, label: str) -> HTMLResponse:
    """Read a UI template from disk, or fail loudly if it was not deployed."""
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{label} HTML template not found on server."
        )
    return HTMLResponse(content=path.read_text(encoding="utf-8"), status_code=200)


@web_router.get("/", summary="Serve Welcome Landing Page or Root Identity")
async def render_root(request: Request):
    """Serve the landing page to browsers; machine clients get the service identity."""
    if "text/html" in request.headers.get("accept", ""):
        return _render_template(WELCOME_TEMPLATE_PATH, "Welcome")

    return JSONResponse(
        status_code=200,
        content={
            "name": settings.PROJECT_NAME,
            "version": settings.VERSION,
            "environment": settings.ENVIRONMENT,
            "status": "active",
            "landing_page": "/",
            "dashboard": "/dashboard",
            "documentation": "/docs",
            "redoc": "/redoc",
            "api_v1": settings.API_V1_PREFIX
        }
    )


@web_router.get("/welcome", response_class=HTMLResponse, summary="Serve Welcome Landing Page")
async def render_welcome(request: Request):
    """Render the ThreeUI Sylva Living Green landing page for API Sentinel."""
    return _render_template(WELCOME_TEMPLATE_PATH, "Welcome")


@web_router.get("/dashboard", response_class=HTMLResponse, summary="Serve Web Dashboard UI")
async def render_dashboard(request: Request):
    """Render the Living Green telemetry cockpit."""
    return _render_template(TEMPLATE_PATH, "Dashboard")


@dashboard_api_router.get(
    "/overview",
    response_model=StandardResponse[DashboardOverviewResponse],
    summary="Get Global Dashboard Telemetry Overview",
    description="Aggregates KPI metrics, recent test runs, active critical issues, and projects."
)
def get_dashboard_overview(db: Session = Depends(get_db)):
    """Fetch global dashboard telemetry bundle."""
    overview = DashboardService.get_global_overview(db)
    return StandardResponse(
        success=True,
        data=overview,
        message="Dashboard overview telemetry aggregated successfully."
    )


@dashboard_api_router.get(
    "/projects/{project_id}",
    response_model=StandardResponse[ProjectDetailView],
    summary="Get Project Detail Dashboard View",
    description="Fetches project metadata, endpoints, and recent runs for drill-down views."
)
def get_project_dashboard_view(project_id: int, db: Session = Depends(get_db)):
    """Fetch project detail dashboard bundle."""
    view = DashboardService.get_project_detail(db, project_id)
    if not view:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project #{project_id} not found."
        )
    return StandardResponse(
        success=True,
        data=view,
        message=f"Retrieved dashboard view for Project #{project_id}."
    )
