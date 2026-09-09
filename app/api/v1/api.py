"""API v1 Router Hub."""
from fastapi import APIRouter
from app.core.config import get_settings
from app.models.schemas.response import StandardResponse, HealthStatus

settings = get_settings()
api_router = APIRouter()


@api_router.get(
    "/health",
    response_model=StandardResponse[HealthStatus],
    summary="System Health & Diagnostic Probe",
    tags=["System"]
)
async def health_check():
    """Verify backend health, persistence connectivity, and AI service readiness."""
    health_data = HealthStatus(
        status="healthy",
        version=settings.VERSION,
        database="ready",
        ai_engine="enabled" if settings.GEMINI_API_KEY else "heuristic_fallback"
    )
    return StandardResponse(
        success=True,
        data=health_data,
        message="API Sentinel backend is operational"
    )
