"""Pydantic schemas and DTOs for Circuit Breakers and Resilience Telemetry."""
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from app.core.circuit_breaker import CircuitState


class CircuitBreakerStatus(BaseModel):
    """Telemetry for an individual target host circuit breaker."""
    host: str = Field(..., description="Target host or domain")
    state: CircuitState = Field(..., description="Operational state: CLOSED, OPEN, HALF_OPEN")
    failure_count: int = Field(0, description="Total recorded failures")
    success_count: int = Field(0, description="Total recorded successes")
    consecutive_failures: int = Field(0, description="Current consecutive failure streak")
    cooldown_remaining_seconds: Optional[float] = Field(None, description="Seconds remaining before transition to HALF_OPEN")
    last_failure_time: Optional[str] = Field(None, description="ISO timestamp of last failure")
    last_state_change: str = Field(..., description="ISO timestamp of last state transition")


class CircuitBreakerListResponse(BaseModel):
    """List of all monitored host circuit breakers."""
    total_breakers: int = Field(..., description="Total monitored target hosts")
    open_count: int = Field(..., description="Number of currently tripped (OPEN) circuit breakers")
    half_open_count: int = Field(..., description="Number of currently trial (HALF_OPEN) circuit breakers")
    closed_count: int = Field(..., description="Number of healthy (CLOSED) circuit breakers")
    breakers: List[CircuitBreakerStatus] = Field(default_factory=list)


class CircuitBreakerResetResponse(BaseModel):
    """Outcome metadata for manual circuit breaker reset."""
    success: bool = Field(..., description="Whether the reset succeeded")
    host: str = Field(..., description="Target host that was reset")
    new_state: CircuitState = Field(CircuitState.CLOSED, description="New circuit state (CLOSED)")
    reset_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ErrorCategoryStat(BaseModel):
    """Breakdown of handled platform errors by category."""
    category: str = Field(..., description="Error category (e.g. NETWORK_TIMEOUT, VALIDATION_ERROR, AI_FALLBACK)")
    count: int = Field(..., description="Total occurrences")
    last_occurred_at: Optional[str] = Field(None, description="Timestamp of latest occurrence")
    latest_message: Optional[str] = Field(None, description="Sample error message from latest occurrence")


class PlatformErrorSummaryResponse(BaseModel):
    """Aggregated platform error handling and resilience statistics."""
    total_errors_handled: int = Field(..., description="Total errors caught and safely processed without crashing")
    active_open_circuit_breakers: int = Field(..., description="Number of currently blocked target hosts")
    ai_fallback_invocations: int = Field(0, description="Number of times rule-based heuristics safely handled AI failures")
    categories: List[ErrorCategoryStat] = Field(default_factory=list)
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
