"""REST API endpoints for Circuit Breakers, Resilience Monitoring, and Error Telemetry."""
import logging
from fastapi import APIRouter, HTTPException, status

from app.models.schemas.resilience import (
    CircuitBreakerListResponse,
    CircuitBreakerResetResponse,
    PlatformErrorSummaryResponse,
)
from app.services.resilience_service import ResilienceService

logger = logging.getLogger("app.api.resilience")
router = APIRouter(prefix="/resilience", tags=["Resilience & Error Handling"])


@router.get(
    "/circuit-breakers",
    response_model=CircuitBreakerListResponse,
    summary="List all target host circuit breakers and operational states"
)
def list_circuit_breakers():
    """Return live status of circuit breakers for all monitored API target hosts."""
    try:
        return ResilienceService.get_circuit_breakers()
    except Exception as e:
        logger.error(f"Failed to query circuit breakers: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query circuit breakers: {str(e)}"
        )


@router.post(
    "/circuit-breakers/{host}/reset",
    response_model=CircuitBreakerResetResponse,
    summary="Manually reset circuit breaker for a host back to CLOSED"
)
def reset_host_circuit_breaker(host: str):
    """Force circuit breaker for specified host back to healthy CLOSED state."""
    try:
        return ResilienceService.reset_circuit_breaker(host)
    except Exception as e:
        logger.error(f"Failed to reset circuit breaker for host '{host}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset circuit breaker: {str(e)}"
        )


@router.post(
    "/circuit-breakers/reset-all",
    summary="Reset all circuit breakers back to CLOSED"
)
def reset_all_circuit_breakers():
    """Reset all active circuit breakers across all monitored hosts."""
    try:
        count = ResilienceService.reset_all_circuit_breakers()
        return {"success": True, "reset_count": count, "message": f"Reset {count} circuit breakers to CLOSED."}
    except Exception as e:
        logger.error(f"Failed to reset all circuit breakers: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset all circuit breakers: {str(e)}"
        )


@router.get(
    "/error-summary",
    response_model=PlatformErrorSummaryResponse,
    summary="Retrieve platform error categories, counts, and AI fallback metrics"
)
def get_error_summary():
    """Return aggregated platform error statistics and resilience diagnostic telemetry."""
    try:
        return ResilienceService.get_error_summary()
    except Exception as e:
        logger.error(f"Failed to query error summary: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query error summary: {str(e)}"
        )
