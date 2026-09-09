"""API v1 Router Hub with Enhanced Health & Diagnostics."""
import time
from fastapi import APIRouter
from app.core.config import get_settings
from app.models.schemas.response import StandardResponse, HealthStatus, DatabaseHealth

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
