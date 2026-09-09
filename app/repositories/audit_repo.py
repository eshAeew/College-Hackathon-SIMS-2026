from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.entities.audit_event import AuditEvent
from app.models.schemas.audit import AuditSummaryStats, SeverityCount
from app.repositories.base import BaseRepository


class AuditRepository(BaseRepository[AuditEvent]):
    """Specialized repository for querying and aggregating audit logs."""

    def __init__(self, db: Session):
        super().__init__(AuditEvent, db)

    def record_event(
        self,
        event_type: str,
        severity: str = "INFO",
        actor: str = "system",
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        request_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> AuditEvent:
        """Create and persist a new immutable audit event."""
        event = AuditEvent(
            event_type=event_type,
            severity=severity,
            actor=actor,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            request_id=request_id,
            details=details or {},
        )
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event

    def get_filtered(
        self,
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
    ) -> List[AuditEvent]:
        """Query audit events with multi-criteria filtering and pagination."""
        query = self.db.query(AuditEvent)

        if event_type:
            query = query.filter(AuditEvent.event_type == event_type)
        if severity:
            query = query.filter(AuditEvent.severity == severity.upper())
        if actor:
            query = query.filter(AuditEvent.actor == actor)
        if target_type:
            query = query.filter(AuditEvent.target_type == target_type)
        if target_id:
            query = query.filter(AuditEvent.target_id == str(target_id))
        if request_id:
            query = query.filter(AuditEvent.request_id == request_id)
        if start_time:
            query = query.filter(AuditEvent.timestamp >= start_time)
        if end_time:
            query = query.filter(AuditEvent.timestamp <= end_time)

        return query.order_by(AuditEvent.timestamp.desc()).offset(offset).limit(limit).all()

    def count_filtered(
        self,
        event_type: Optional[str] = None,
        severity: Optional[str] = None,
        actor: Optional[str] = None,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        request_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> int:
        """Count total matching records for pagination metadata."""
        query = self.db.query(func.count(AuditEvent.id))

        if event_type:
            query = query.filter(AuditEvent.event_type == event_type)
        if severity:
            query = query.filter(AuditEvent.severity == severity.upper())
        if actor:
            query = query.filter(AuditEvent.actor == actor)
        if target_type:
            query = query.filter(AuditEvent.target_type == target_type)
        if target_id:
            query = query.filter(AuditEvent.target_id == str(target_id))
        if request_id:
            query = query.filter(AuditEvent.request_id == request_id)
        if start_time:
            query = query.filter(AuditEvent.timestamp >= start_time)
        if end_time:
            query = query.filter(AuditEvent.timestamp <= end_time)

        return query.scalar() or 0

    def get_summary_stats(self) -> AuditSummaryStats:
        """Aggregate high-level audit metrics and severity distributions."""
        total = self.db.query(func.count(AuditEvent.id)).scalar() or 0

        # Severity breakdown
        sev_counts = dict(
            self.db.query(AuditEvent.severity, func.count(AuditEvent.id))
            .group_by(AuditEvent.severity)
            .all()
        )
        severity_breakdown = SeverityCount(
            INFO=sev_counts.get("INFO", 0),
            WARNING=sev_counts.get("WARNING", 0),
            ERROR=sev_counts.get("ERROR", 0),
            CRITICAL=sev_counts.get("CRITICAL", 0),
        )

        # Top event types
        top_types = dict(
            self.db.query(AuditEvent.event_type, func.count(AuditEvent.id))
            .group_by(AuditEvent.event_type)
            .order_by(func.count(AuditEvent.id).desc())
            .limit(10)
            .all()
        )

        # Recent critical count
        crit_count = sev_counts.get("CRITICAL", 0)

        # Timestamps
        min_max = self.db.query(
            func.min(AuditEvent.timestamp),
            func.max(AuditEvent.timestamp)
        ).first()

        oldest_ts = min_max[0].isoformat() if min_max and min_max[0] else None
        latest_ts = min_max[1].isoformat() if min_max and min_max[1] else None

        return AuditSummaryStats(
            total_events=total,
            severity_breakdown=severity_breakdown,
            top_event_types=top_types,
            recent_critical_events=crit_count,
            oldest_event_timestamp=oldest_ts,
            latest_event_timestamp=latest_ts,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
