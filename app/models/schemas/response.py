"""Standardized API Response Envelopes and Health Diagnostics."""
from typing import Generic, TypeVar, Optional, Any, Dict
from datetime import datetime, timezone
from pydantic import BaseModel, Field

T = TypeVar("T")


class StandardResponse(BaseModel, Generic[T]):
    """Standardized successful API response wrapper."""
    success: bool = Field(default=True, description="Indicates if the request succeeded")
    data: Optional[T] = Field(default=None, description="Response payload")
    message: str = Field(default="Operation completed successfully", description="Informational message")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="UTC timestamp")


class ErrorDetail(BaseModel):
    """Structured error detail model."""
    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error explanation")
    details: Optional[Any] = Field(default=None, description="Optional granular error metadata")


class ErrorResponse(BaseModel):
    """Standardized error response wrapper."""
    success: bool = Field(default=False, description="Always false for error responses")
    error: ErrorDetail = Field(..., description="Error detail container")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="UTC timestamp")


class DatabaseHealth(BaseModel):
    """Database connection status."""
    status: str = Field(default="connected", description="Database health status ('connected', 'degraded', 'error')")
    engine: str = Field(default="sqlite", description="Database engine type")
    location: str = Field(..., description="Database URI or file location")


class HealthStatus(BaseModel):
    """Comprehensive system health & diagnostic status."""
    status: str = Field(default="healthy", description="Overall system health status")
    version: str = Field(..., description="API Sentinel version")
    environment: str = Field(..., description="Active environment (development/production)")
    uptime_seconds: float = Field(..., description="Server uptime in seconds")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Server UTC time")
    database: DatabaseHealth = Field(..., description="Persistence layer health details")
    ai_engine: str = Field(default="heuristic_fallback", description="AI Diagnostic status (enabled/heuristic_fallback)")
