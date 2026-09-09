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
# A wildcard origin combined with credentials lets any site drive this API with the
# viewer's cookies, so credentials are disabled unless explicit origins are configured.
_cors_is_wildcard = "*" in settings.CORS_ORIGINS
if _cors_is_wildcard and settings.CORS_ALLOW_CREDENTIALS:
    logging.getLogger("app.main").warning(
        "CORS_ORIGINS is '*' - disabling allow_credentials. "
        "Set explicit origins to enable credentialed cross-origin requests."
    )
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS and not _cors_is_wildcard,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)


from app.core.exception_handlers import register_exception_handlers

# 3. Register Global Structured Exception Handlers
register_exception_handlers(app)


from pathlib import Path
from fastapi.staticfiles import StaticFiles
from app.web.routes import web_router
from app.demo_target.routes import demo_target_router

# Mount Static Assets
STATIC_DIR = Path(__file__).parent / "web" / "static"
INNER_GREEN_ASSETS_DIR = STATIC_DIR / "inner-green-assets"

if INNER_GREEN_ASSETS_DIR.exists():
    app.mount("/inner-green-assets", StaticFiles(directory=str(INNER_GREEN_ASSETS_DIR)), name="inner_green_assets")
    app.mount("/landing-pages/inner-green-assets", StaticFiles(directory=str(INNER_GREEN_ASSETS_DIR)), name="landing_pages_inner_green_assets")

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Mount Web Dashboard UI router (handles / and /dashboard and /welcome)
app.include_router(web_router)

# Mount API v1 router
app.include_router(api_router, prefix=settings.API_V1_PREFIX)

# Mount Intentionally Flawed Demo Target API router
app.include_router(demo_target_router)


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

