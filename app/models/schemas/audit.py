"""Pydantic schemas and DTOs for Audit Trails, Traces, and Telemetry."""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AuditSeverity(str, Enum):
    """Severity levels for audit events."""
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class AuditEventType(str, Enum):
    """Standardized audit event taxonomy."""
    PROJECT_CREATED = "PROJECT_CREATED"
    PROJECT_DELETED = "PROJECT_DELETED"
    ENDPOINT_CREATED = "ENDPOINT_CREATED"
    ENDPOINT_MUTATED = "ENDPOINT_MUTATED"
    ENDPOINT_DELETED = "ENDPOINT_DELETED"
    TEST_CASE_CREATED = "TEST_CASE_CREATED"
    TEST_CASE_MODIFIED = "TEST_CASE_MODIFIED"
    TEST_RUN_STARTED = "TEST_RUN_STARTED"
    TEST_RUN_COMPLETED = "TEST_RUN_COMPLETED"
    TEST_RUN_CANCELLED = "TEST_RUN_CANCELLED"
    SAFETY_OVERRIDE = "SAFETY_OVERRIDE"
    AI_ANALYSIS_REQUESTED = "AI_ANALYSIS_REQUESTED"
    CIRCUIT_BREAKER_STATE_CHANGE = "CIRCUIT_BREAKER_STATE_CHANGE"
    CIRCUIT_BREAKER_RESET = "CIRCUIT_BREAKER_RESET"
    DATABASE_MAINTENANCE = "DATABASE_MAINTENANCE"
    DATABASE_PURGE = "DATABASE_PURGE"
    SECURITY_AUDIT = "SECURITY_AUDIT"
    SYSTEM_CONFIG_CHANGE = "SYSTEM_CONFIG_CHANGE"
    CUSTOM = "CUSTOM"


class AuditEventCreate(BaseModel):
    """Request payload to record a new audit event."""
    event_type: str = Field(..., description="Audit event type identifier")
    severity: AuditSeverity = Field(default=AuditSeverity.INFO, description="Event severity rating")
    actor: str = Field(default="system", description="Identity or sub-system triggering the event")
    target_type: Optional[str] = Field(None, description="Target entity category (project, endpoint, test_run)")
    target_id: Optional[str] = Field(None, description="Identifier of the target entity")
    request_id: Optional[str] = Field(None, description="Associated correlation or request ID")
    details: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Structured event payload context")


class AuditEventRead(BaseModel):
    """Response DTO for an audit event record."""
    id: int
    timestamp: datetime
    event_type: str
    severity: str
    actor: str
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    request_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class AuditLogListResponse(BaseModel):
    """Paginated list response for audit log events."""
    total: int
    limit: int
    offset: int
    events: List[AuditEventRead]


class SeverityCount(BaseModel):
    """Count of events per severity level."""
    INFO: int = 0
    WARNING: int = 0
    ERROR: int = 0
    CRITICAL: int = 0


class AuditSummaryStats(BaseModel):
    """Aggregated KPI metrics for system auditability."""
    total_events: int
    severity_breakdown: SeverityCount
    top_event_types: Dict[str, int]
    recent_critical_events: int
    oldest_event_timestamp: Optional[str] = None
    latest_event_timestamp: Optional[str] = None
    generated_at: str


class LiveLogItem(BaseModel):
    """Individual live in-memory log buffer record."""
    timestamp: str
    level: str
    logger: str
    message: str
    request_id: str
    module: Optional[str] = None
    line: Optional[int] = None


class LiveLogListResponse(BaseModel):
    """Response DTO for live in-memory log records."""
    total_buffered: int
    matched_count: int
    logs: List[LiveLogItem]


class TraceSpanDTO(BaseModel):
    """Detailed DTO representing an execution span in a distributed trace."""
    span_id: str
    trace_id: str
    name: str
    parent_span_id: Optional[str] = None
    start_time: float
    end_time: Optional[float] = None
    duration_ms: Optional[float] = None
    status: str = "OK"  # OK, ERROR
    metadata: Dict[str, Any] = Field(default_factory=dict)
    children: List["TraceSpanDTO"] = Field(default_factory=list)


class TraceTimelineResponse(BaseModel):
    """Full execution trace timeline with nested spans."""
    trace_id: str
    root_span_name: str
    total_duration_ms: float
    span_count: int
    status: str
    root_span: TraceSpanDTO
    created_at: str
