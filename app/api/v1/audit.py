"""REST API endpoints for Audit Trails, Execution Tracing, and Live Log Telemetry."""
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.schemas.audit import (
    AuditEventCreate,
    AuditEventRead,
    AuditLogListResponse,
    AuditSummaryStats,
    LiveLogListResponse,
    TraceTimelineResponse,
)
from app.services.audit_service import AuditService

router = APIRouter(prefix="/audit", tags=["Audit & Telemetry"])


@router.get("/events", response_model=AuditLogListResponse, summary="Query Audit Logs")
def get_audit_events(
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    severity: Optional[str] = Query(None, description="Filter by severity (INFO, WARNING, ERROR, CRITICAL)"),
    actor: Optional[str] = Query(None, description="Filter by actor identifier"),
    target_type: Optional[str] = Query(None, description="Filter by target type (project, endpoint, test_run)"),
    target_id: Optional[str] = Query(None, description="Filter by target ID"),
    request_id: Optional[str] = Query(None, description="Filter by correlation/request ID"),
    start_time: Optional[datetime] = Query(None, description="Filter events after timestamp"),
    end_time: Optional[datetime] = Query(None, description="Filter events before timestamp"),
    limit: int = Query(50, ge=1, le=500, description="Page limit"),
    offset: int = Query(0, ge=0, description="Page offset"),
    db: Session = Depends(get_db),
):
    """Retrieve filtered, paginated audit log events."""
    return AuditService.query_audit_logs(
        db=db,
        event_type=event_type,
        severity=severity,
        actor=actor,
        target_type=target_type,
        target_id=target_id,
        request_id=request_id,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
        offset=offset,
    )


@router.post("/events", response_model=AuditEventRead, status_code=status.HTTP_201_CREATED, summary="Record Audit Event")
def record_audit_event(
    event_in: AuditEventCreate,
    db: Session = Depends(get_db),
):
    """Record a new platform audit event."""
    return AuditService.record_event(db=db, event_in=event_in)


@router.get("/summary", response_model=AuditSummaryStats, summary="Audit Summary KPIs")
def get_audit_summary(
    db: Session = Depends(get_db),
):
    """Retrieve aggregated audit KPIs, severity breakdowns, and activity metrics."""
    return AuditService.get_audit_summary(db=db)


@router.get("/export", summary="Export Audit Trail")
def export_audit_trail(
    format: str = Query("json", regex="^(json|csv)$", description="Export format (json or csv)"),
    limit: int = Query(500, ge=1, le=5000, description="Max records to export"),
    db: Session = Depends(get_db),
):
    """Export compliance audit trail in JSON or CSV format."""
    if format == "csv":
        csv_data = AuditService.export_audit_csv(db=db, limit=limit)
        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=sentinel-audit-trail.csv"},
        )
    
    logs = AuditService.query_audit_logs(db=db, limit=limit)
    return logs


@router.get("/traces/{trace_id}", response_model=TraceTimelineResponse, summary="Get Trace Timeline")
def get_trace_timeline(
    trace_id: str,
):
    """Retrieve distributed execution trace hierarchy by trace_id."""
    trace = AuditService.get_trace(trace_id)
    if not trace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trace with ID '{trace_id}' not found or has expired.",
        )
    return trace


@router.get("/live-logs", response_model=LiveLogListResponse, summary="Query Live In-Memory Logs")
def get_live_logs(
    level: Optional[str] = Query(None, description="Filter by log level (DEBUG, INFO, WARNING, ERROR)"),
    search: Optional[str] = Query(None, description="Filter by text match in log message"),
    limit: int = Query(100, ge=1, le=500, description="Max logs to return"),
):
    """Query recent in-memory log buffer records in real-time."""
    return AuditService.get_live_logs(level=level, search=search, limit=limit)


@router.post("/live-logs/clear", summary="Clear In-Memory Log Buffer")
def clear_live_logs():
    """Flush the in-memory application log buffer."""
    count = AuditService.clear_live_logs()
    return {"status": "cleared", "records_removed": count}
