"""TestRun entity model for orchestrating test execution suites."""
import json
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base


class TestRun(Base):
    """Database entity representing an executed or queued test suite run."""
    __tablename__ = "test_runs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(150), nullable=False, index=True)
    status = Column(String(30), default="QUEUED", nullable=False, index=True)  # QUEUED, RUNNING, COMPLETED, CANCELLED, FAILED
    environment = Column(String(50), default="development", nullable=False)
    
    concurrency = Column(Integer, default=5, nullable=False)
    total_tests = Column(Integer, default=0, nullable=False)
    passed_tests = Column(Integer, default=0, nullable=False)
    failed_tests = Column(Integer, default=0, nullable=False)
    warning_tests = Column(Integer, default=0, nullable=False)
    error_tests = Column(Integer, default=0, nullable=False)
    
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    duration_ms = Column(Float, default=0.0, nullable=False)
    cancellation_reason = Column(Text, nullable=True)
    run_metadata_json = Column(Text, default="{}", nullable=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    project = relationship("Project", back_populates="test_runs")
    test_results = relationship("TestResult", back_populates="test_run", cascade="all, delete-orphan", order_by="TestResult.id")

    @property
    def run_metadata(self) -> dict:
        """Parse metadata JSON string into dictionary."""
        try:
            return json.loads(self.run_metadata_json) if self.run_metadata_json else {}
        except Exception:
            return {}

    @run_metadata.setter
    def run_metadata(self, value: dict) -> None:
        """Serialize metadata dictionary into JSON string."""
        self.run_metadata_json = json.dumps(value or {})
