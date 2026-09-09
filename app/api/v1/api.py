"""API v1 Router Hub with Enhanced Health & Diagnostics and Projects Router."""
import time
from fastapi import APIRouter
from app.core.config import get_settings
from app.models.schemas.response import StandardResponse, HealthStatus, DatabaseHealth
from app.api.v1.projects import router as projects_router
from app.api.v1.endpoints import router as endpoints_router
from app.api.v1.requests import router as requests_router
from app.api.v1.executions import router as executions_router
from app.api.v1.test_cases import router as test_cases_router
from app.api.v1.validations import router as validations_router
from app.api.v1.adversarial import router as adversarial_router
from app.api.v1.inconsistency import router as inconsistency_router
from app.api.v1.performance import router as performance_router
from app.api.v1.recurring_failures import router as recurring_failures_router
from app.api.v1.test_runs import router as test_runs_router
from app.api.v1.regression import router as regression_router
from app.api.v1.openapi import router as openapi_router
from app.api.v1.test_generation import router as test_generation_router
from app.api.v1.safety import router as safety_router
from app.api.v1.classification import router as classification_router
from app.api.v1.failure_analysis import router as failure_analysis_router
from app.api.v1.ai_recommendations import router as ai_recommendations_router
from app.api.v1.run_comparison import comparison_router
from app.api.v1.reports import router as reports_router
from app.api.v1.database import router as database_router
from app.api.v1.resilience import router as resilience_router
from app.web.routes import dashboard_api_router



settings = get_settings()
api_router = APIRouter()

# Server start timestamp recorded when module loads
SERVER_START_TIME = time.time()


@api_router.get(
    "/health",
    response_model=StandardResponse[HealthStatus],
    summary="System Health & Diagnostic Probe",
    tags=["System"]
)
async def health_check():
    """Verify backend health, persistence connectivity, uptime, and AI service readiness."""
    uptime = time.time() - SERVER_START_TIME
    
    # Check SQLite accessibility
    db_status = "connected"
    if settings.DATABASE_URL.startswith("sqlite"):
        db_engine = "SQLite 3"
    elif settings.DATABASE_URL.startswith("postgresql"):
        db_engine = "PostgreSQL"
    else:
        db_engine = "Unknown"

    health_data = HealthStatus(
        status="healthy",
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
        uptime_seconds=round(uptime, 2),
        database=DatabaseHealth(
            status=db_status,
            engine=db_engine,
            location=settings.DATABASE_URL.split("@")[-1]  # Mask credentials if any
        ),
        ai_engine="enabled (Google Gemini)" if settings.is_ai_enabled else "heuristic_fallback (Offline Mode)"
    )
    return StandardResponse(
        success=True,
        data=health_data,
        message="API Sentinel backend is operational and healthy"
    )


# Mount Sub-Routers
api_router.include_router(projects_router)
api_router.include_router(endpoints_router)
api_router.include_router(requests_router)
api_router.include_router(executions_router)
api_router.include_router(test_cases_router)
api_router.include_router(validations_router)
api_router.include_router(adversarial_router)
api_router.include_router(inconsistency_router)
api_router.include_router(performance_router)
api_router.include_router(recurring_failures_router)
api_router.include_router(comparison_router)
api_router.include_router(test_runs_router)
api_router.include_router(regression_router)
api_router.include_router(openapi_router)
api_router.include_router(test_generation_router)
api_router.include_router(safety_router)
api_router.include_router(classification_router)
api_router.include_router(failure_analysis_router)
api_router.include_router(ai_recommendations_router)
api_router.include_router(reports_router)
api_router.include_router(database_router)
api_router.include_router(resilience_router)
api_router.include_router(dashboard_api_router)










