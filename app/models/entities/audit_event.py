"""AuditEvent SQLAlchemy entity model for compliance and platform audit trails."""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON
from app.core.database import Base


class AuditEvent(Base):
    """Immutable audit event capturing platform operations and security events."""
    __tablename__ = "audit_events"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    event_type = Column(String(60), nullable=False, index=True)  # e.g. TEST_RUN_STARTED, SAFETY_OVERRIDE
    severity = Column(String(20), default="INFO", nullable=False, index=True)  # INFO, WARNING, ERROR, CRITICAL
    actor = Column(String(100), default="system", nullable=False)  # system, user_api, worker, cli
    target_type = Column(String(50), nullable=True, index=True)  # project, endpoint, test_run, circuit_breaker
    target_id = Column(String(100), nullable=True)
    request_id = Column(String(100), nullable=True, index=True)
    details = Column(JSON, nullable=True)  # Context payload, parameters, error traces

    def __repr__(self):
        return f"<AuditEvent id={self.id} event={self.event_type} severity={self.severity} req={self.request_id}>"
