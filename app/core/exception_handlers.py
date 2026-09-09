"""Global exception handlers for FastAPI application with standardized JSON error envelopes."""
import logging
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

from app.core.exceptions import SentinelBaseException, CircuitBreakerOpenException
from app.models.schemas.response import ErrorDetail, ErrorResponse
from app.services.resilience_service import ResilienceService

logger = logging.getLogger("app.exceptions")


def register_exception_handlers(app: FastAPI) -> None:
    """Register all custom and standard exception handlers on the FastAPI app instance."""

    @app.exception_handler(SentinelBaseException)
    async def sentinel_exception_handler(request: Request, exc: SentinelBaseException):
        """Handle custom platform exceptions with unified code, details, and actionable hint."""
        logger.warning(
            f"SentinelException ({exc.code}) on {request.method} {request.url.path}: {exc.message}"
        )
        ResilienceService.record_error(exc.code, exc.message)
        
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                    "hint": exc.hint,
                }
            }
        )

    @app.exception_handler(CircuitBreakerOpenException)
    async def circuit_breaker_exception_handler(request: Request, exc: CircuitBreakerOpenException):
        """Handle tripped circuit breaker with HTTP 503 and Retry-After header."""
        logger.warning(f"Circuit Breaker blocked {request.method} {request.url.path}: {exc.message}")
        ResilienceService.record_error("CIRCUIT_BREAKER_BLOCKED", exc.message)
        
        headers = {}
        if exc.details and "cooldown_remaining_seconds" in exc.details:
            headers["Retry-After"] = str(int(exc.details["cooldown_remaining_seconds"]))

        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            headers=headers,
            content={
                "success": False,
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                    "hint": exc.hint,
                }
            }
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """Format request validation errors into standard JSON error envelope."""
        logger.warning(f"Validation failure on {request.method} {request.url.path}")
        ResilienceService.record_error("REQUEST_VALIDATION_ERROR", f"Validation failure on {request.url.path}")
        safe_errors = jsonable_encoder(exc.errors())
        
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ErrorResponse(
                success=False,
                error=ErrorDetail(
                    code="VALIDATION_ERROR",
                    message="Request payload or parameter validation failed",
                    details=safe_errors
                )
            ).model_dump(mode="json")
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        """Standardize FastAPI HTTPExceptions."""
        ResilienceService.record_error(f"HTTP_{exc.status_code}", str(exc.detail))
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "error": {
                    "code": f"HTTP_{exc.status_code}",
                    "message": exc.detail if isinstance(exc.detail, str) else "HTTP Exception",
                    "details": exc.detail if not isinstance(exc.detail, str) else None,
                    "hint": "Check request parameters and resource availability.",
                }
            }
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(request: Request, exc: IntegrityError):
        """Handle database integrity and foreign key constraint violations."""
        logger.error(f"Database integrity violation on {request.method} {request.url.path}: {exc}")
        ResilienceService.record_error("DATABASE_INTEGRITY_ERROR", str(exc.orig) if hasattr(exc, "orig") else str(exc))
        
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "success": False,
                "error": {
                    "code": "DATABASE_INTEGRITY_ERROR",
                    "message": "Database constraint violation (unique constraint or foreign key constraint failed).",
                    "details": str(exc.orig) if hasattr(exc, "orig") else "Integrity constraint failed",
                    "hint": "Ensure referenced entity exists and unique fields are distinct.",
                }
            }
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        """Catch-all unhandled exception handler guaranteeing zero leaked raw HTML or server traces."""
        logger.error(
            f"Unhandled platform error on {request.method} {request.url.path}: {str(exc)}",
            exc_info=True
        )
        ResilienceService.record_error("UNHANDLED_INTERNAL_ERROR", str(exc))
        
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An internal error occurred while processing the request.",
                    "details": str(exc),
                    "hint": "Inspect server logs with correlation ID for root-cause diagnosis.",
                }
            }
        )
