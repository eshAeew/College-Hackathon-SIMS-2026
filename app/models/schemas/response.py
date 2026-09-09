"""Standardized API Response Envelopes."""
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


class HealthStatus(BaseModel):
    """System health check payload."""
    status: str = Field(default="healthy", description="System health status")
    version: str = Field(..., description="API Sentinel version")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Server UTC time")
    database: str = Field(default="connected", description="Database connection state")
    ai_engine: str = Field(default="ready", description="AI Diagnostic engine state")
