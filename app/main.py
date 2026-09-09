"""API Sentinel — FastAPI Main Entry Point."""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from app.core.config import get_settings
from app.api.v1.api import api_router
from app.models.schemas.response import ErrorResponse, ErrorDetail

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle hook (startup and shutdown)."""
    # Startup actions
    print(f"[{settings.PROJECT_NAME} v{settings.VERSION}] Starting up in {'DEBUG' if settings.DEBUG else 'PRODUCTION'} mode...")
    yield
    # Shutdown actions
    print(f"[{settings.PROJECT_NAME}] Shutting down cleanly...")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=settings.DESCRIPTION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan
)

# CORS Middleware
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
        "status": "active",
        "documentation": "/docs",
        "api_v1": settings.API_V1_PREFIX
    }


# Mount API v1 router
app.include_router(api_router, prefix=settings.API_V1_PREFIX)
