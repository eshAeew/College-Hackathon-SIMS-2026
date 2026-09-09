"""API Sentinel — FastAPI Main Entry Point."""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.openapi.docs import get_redoc_html

from app.core.config import get_settings
from app.core.database import init_db
from app.core.logging import setup_logging
from app.core.middleware import RequestCorrelationMiddleware
from app.core.http_client import init_async_client, close_async_client
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
    # Initialize SQLite database schema
    init_db()
    # Initialize shared HTTP connection pool
    await init_async_client()
    yield
    # Cleanly close HTTP connection pool
    await close_async_client()
    logger.info(f"Shutting down {settings.PROJECT_NAME} cleanly...")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=settings.DESCRIPTION,
    docs_url="/docs",
    redoc_url=None,  # Handled via custom endpoint below to support OpenAPI 3.1.0
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
    logger.warning(f"Validation failure on {request.method} {request.url.path}")
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


from app.web.routes import web_router

# Mount Web Dashboard UI router (handles / and /dashboard)
app.include_router(web_router)

# Mount API v1 router
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/health", tags=["System"], summary="Liveness Health Probe")
async def top_level_health():
    """Top-level health check probe forwarding to standard v1 health diagnostic."""
    from app.api.v1.api import health_check
    return await health_check()


@app.get("/redoc", include_in_schema=False)
async def custom_redoc_html():
    """Custom ReDoc page utilizing modern Redocly bundle compatible with OpenAPI 3.1."""
    return get_redoc_html(
        openapi_url=app.openapi_url or "/openapi.json",
        title=f"{app.title} - ReDoc",
        redoc_js_url="https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js",
    )

