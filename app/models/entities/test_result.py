"""TestResult entity model for individual scenario execution records."""
import json
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base


class TestResult(Base):
    """Database entity representing an individual test case execution result in a TestRun."""
    __tablename__ = "test_results"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey("test_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    test_case_id = Column(Integer, ForeignKey("test_cases.id", ondelete="SET NULL"), nullable=True, index=True)
    endpoint_id = Column(Integer, ForeignKey("endpoints.id", ondelete="SET NULL"), nullable=True, index=True)

    status = Column(String(30), nullable=False, index=True)  # PASS, FAIL, WARNING, ERROR, SKIPPED, CANCELLED
    test_name = Column(String(150), nullable=False)
    http_method = Column(String(10), nullable=False)
    url = Column(String(500), nullable=False)
    
    response_code = Column(Integer, nullable=True)
    response_time_ms = Column(Float, nullable=True)
    response_body_snippet = Column(Text, nullable=True)
    response_headers_json = Column(Text, default="{}", nullable=False)
    
    failure_type = Column(String(50), nullable=True)
    failure_evidence_json = Column(Text, default="{}", nullable=False)

    executed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    test_run = relationship("TestRun", back_populates="test_results")
    test_case = relationship("TestCase")
    endpoint = relationship("Endpoint")

    @property
    def response_headers(self) -> dict:
        """Parse response headers JSON string into dictionary."""
        try:
            return json.loads(self.response_headers_json) if self.response_headers_json else {}
        except Exception:
            return {}

    @response_headers.setter
    def response_headers(self, value: dict) -> None:
        """Serialize response headers dictionary into JSON string."""
        self.response_headers_json = json.dumps(value or {})

    @property
    def failure_evidence(self) -> dict:
        """Parse failure evidence JSON string into dictionary."""
        try:
            return json.loads(self.failure_evidence_json) if self.failure_evidence_json else {}
        except Exception:
            return {}

    @failure_evidence.setter
    def failure_evidence(self, value: dict) -> None:
        """Serialize failure evidence dictionary into JSON string."""
        self.failure_evidence_json = json.dumps(value or {})
