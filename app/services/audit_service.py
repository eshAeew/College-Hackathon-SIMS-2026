"""Service layer for Audit Logging, Tracing Timeline retrieval, and Live Log Telemetry."""
import csv
import io
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.core.logging import get_log_buffer
from app.core.tracer import Tracer
from app.models.schemas.audit import (
    AuditEventCreate,
    AuditEventRead,
    AuditLogListResponse,
    AuditSummaryStats,
    LiveLogItem,
    LiveLogListResponse,
    TraceTimelineResponse,
)
from app.repositories.audit_repo import AuditRepository

logger = logging.getLogger("app.services.audit")


class AuditService:
    """Service handling platform audit trails, execution tracing, and live telemetry."""

    @classmethod
    def record_event(
        cls,
        db: Session,
        event_in: AuditEventCreate,
    ) -> AuditEventRead:
        """Record and persist an audit event."""
        repo = AuditRepository(db)
        event = repo.record_event(
            event_type=event_in.event_type,
            severity=event_in.severity.value,
            actor=event_in.actor,
            target_type=event_in.target_type,
            target_id=event_in.target_id,
            request_id=event_in.request_id,
            details=event_in.details,
        )
        return AuditEventRead.model_validate(event)

    @classmethod
    def query_audit_logs(
        cls,
        db: Session,
        event_type: Optional[str] = None,
        severity: Optional[str] = None,
        actor: Optional[str] = None,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        request_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> AuditLogListResponse:
        """Query audit events with filtering and pagination."""
        repo = AuditRepository(db)
        events = repo.get_filtered(
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
        total = repo.count_filtered(
            event_type=event_type,
            severity=severity,
            actor=actor,
            target_type=target_type,
            target_id=target_id,
            request_id=request_id,
            start_time=start_time,
            end_time=end_time,
        )
        return AuditLogListResponse(
            total=total,
            limit=limit,
            offset=offset,
            events=[AuditEventRead.model_validate(e) for e in events],
        )

    @classmethod
    def get_audit_summary(cls, db: Session) -> AuditSummaryStats:
        """Retrieve aggregated audit statistics and KPI metrics."""
        repo = AuditRepository(db)
        return repo.get_summary_stats()

    @classmethod
    def export_audit_csv(cls, db: Session, limit: int = 1000) -> str:
        """Export audit events as a formatted CSV string."""
        repo = AuditRepository(db)
        events = repo.get_filtered(limit=limit)

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["ID", "Timestamp", "Event Type", "Severity", "Actor", "Target Type", "Target ID", "Request ID", "Details"])

        for e in events:
            details_str = json.dumps(e.details) if e.details else ""
            writer.writerow([
                e.id,
                e.timestamp.isoformat() if e.timestamp else "",
                e.event_type,
                e.severity,
                e.actor,
                e.target_type or "",
                e.target_id or "",
                e.request_id or "",
                details_str,
            ])
        return output.getvalue()

    @classmethod
    def get_live_logs(
        cls,
        level: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 100,
    ) -> LiveLogListResponse:
        """Query buffered in-memory application logs with filtering."""
        buf = get_log_buffer()
        raw_logs = buf.get_logs(limit=limit, level=level, search=search)
        
        items = [
            LiveLogItem(
                timestamp=r.get("timestamp", ""),
                level=r.get("level", "INFO"),
                logger=r.get("logger", ""),
                message=r.get("message", ""),
                request_id=r.get("request_id", "-"),
                module=r.get("module"),
                line=r.get("line"),
            )
            for r in raw_logs
        ]
        return LiveLogListResponse(
            total_buffered=buf.count(),
            matched_count=len(items),
            logs=items,
        )

    @classmethod
    def clear_live_logs(cls) -> int:
        """Flush in-memory log buffer."""
        buf = get_log_buffer()
        return buf.clear()

    @classmethod
    def get_trace(cls, trace_id: str) -> Optional[TraceTimelineResponse]:
        """Retrieve execution trace timeline by trace_id."""
        tracer = Tracer()
        trace_data = tracer.get_trace(trace_id)
        if not trace_data:
            return None
        return TraceTimelineResponse.model_validate(trace_data)
