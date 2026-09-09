"""API Sentinel — FastAPI Main Entry Point."""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.middleware import RequestCorrelationMiddleware
from app.api.v1.api import api_router
from app.models.schemas.response import ErrorResponse, ErrorDetail

settings = get_settings()

# Initialize structured logging
setup_logging(log_level=settings.LOG_LEVEL, json_format=not settings.DEBUG)
logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle hook (startup and shutdown)."""
    logger.info(
        f"Starting {settings.PROJECT_NAME} v{settings.VERSION} "
        f"[Env: {settings.ENVIRONMENT}, Debug: {settings.DEBUG}]"
    )
    yield
    logger.info(f"Shutting down {settings.PROJECT_NAME} cleanly...")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=settings.DESCRIPTION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan
)

# 1. Request Correlation & Latency Logging Middleware
app.add_middleware(RequestCorrelationMiddleware)

# 2. CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Format request validation errors into standard JSON error envelope."""
    logger.warning(f"Validation failure on {request.method} {request.url.path}: {exc.errors()}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=ErrorResponse(
            success=False,
            error=ErrorDetail(
                code="VALIDATION_ERROR",
                message="Request payload or parameter validation failed",
                details=exc.errors()
            )
        ).model_dump(mode="json")
    )


@app.get("/", tags=["System"], summary="Root Health & Identity")
async def root():
    """Root endpoint verifying API Sentinel identity."""
    return {
        "name": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "status": "active",
        "documentation": "/docs",
        "api_v1": settings.API_V1_PREFIX
    }


# Mount API v1 router
app.include_router(api_router, prefix=settings.API_V1_PREFIX)
