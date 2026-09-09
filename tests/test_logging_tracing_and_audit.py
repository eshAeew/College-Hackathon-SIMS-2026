"""Comprehensive unit and integration tests for Stage 25: Logging, Tracing & Auditability."""
import json
import logging
import time
import unittest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core.database import Base, get_db
from app.core.logging import (
    JSONLogFormatter,
    ConsoleLogFormatter,
    InMemoryLogBuffer,
    get_log_buffer,
    request_id_ctx_var,
)
from app.core.tracer import Tracer, TraceSpan
from app.models.entities.audit_event import AuditEvent
from app.models.schemas.audit import AuditEventCreate, AuditSeverity
from app.repositories.audit_repo import AuditRepository
from app.services.audit_service import AuditService

# Use isolated in-memory database for testing
SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    """Override database session for testing."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


class TestLoggingTracingAndAudit(unittest.TestCase):
    """Test suite covering structured log formatters, in-memory log buffer, tracer spans, DAL, and REST APIs."""

    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=test_engine)
        app.dependency_overrides[get_db] = override_get_db

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=test_engine)

    def setUp(self):
        self.client = TestClient(app)
        self.db = TestingSessionLocal()
        Tracer().clear()
        get_log_buffer().clear()

    def tearDown(self):
        self.db.query(AuditEvent).delete()
        self.db.commit()
        self.db.close()
        Tracer().clear()
        get_log_buffer().clear()

    def test_json_and_console_log_formatters(self):
        """Test that JSONLogFormatter produces valid JSON and ConsoleLogFormatter includes correlation ID."""
        record = logging.LogRecord(
            name="app.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=42,
            msg="User %s logged in successfully",
            args=("alice",),
            exc_info=None,
        )

        token = request_id_ctx_var.set("req-12345678-abcd")
        try:
            # JSON Formatter
            json_fmt = JSONLogFormatter()
            json_str = json_fmt.format(record)
            parsed = json.loads(json_str)
            self.assertEqual(parsed["level"], "INFO")
            self.assertEqual(parsed["logger"], "app.test")
            self.assertEqual(parsed["message"], "User alice logged in successfully")
            self.assertEqual(parsed["request_id"], "req-12345678-abcd")
            self.assertIn("timestamp", parsed)

            # Console Formatter
            console_fmt = ConsoleLogFormatter()
            console_str = console_fmt.format(record)
            self.assertIn("[req-1234]", console_str)
            self.assertIn("User alice logged in successfully", console_str)
        finally:
            request_id_ctx_var.reset(token)

    def test_in_memory_log_buffer(self):
        """Test in-memory log buffer appending, filtering, search, and clearing."""
        buf = get_log_buffer()
        buf.clear()

        buf.append({"timestamp": "2026-09-09T10:00:00Z", "level": "INFO", "logger": "app.core", "message": "Startup complete", "request_id": "-"})
        buf.append({"timestamp": "2026-09-09T10:00:01Z", "level": "WARNING", "logger": "app.security", "message": "High latency detected", "request_id": "r1"})
        buf.append({"timestamp": "2026-09-09T10:00:02Z", "level": "ERROR", "logger": "app.database", "message": "Connection timeout to replica", "request_id": "r2"})

        self.assertEqual(buf.count(), 3)

        # Filter by level
        warns = buf.get_logs(level="WARNING")
        self.assertEqual(len(warns), 1)
        self.assertEqual(warns[0]["message"], "High latency detected")

        # Filter by search
        errs = buf.get_logs(search="replica")
        self.assertEqual(len(errs), 1)
        self.assertEqual(errs[0]["level"], "ERROR")

        # Clear
        cleared = buf.clear()
        self.assertEqual(cleared, 3)
        self.assertEqual(buf.count(), 0)

    def test_tracer_and_span_hierarchy(self):
        """Test distributed tracer recording nested execution spans and timeline assembly."""
        tracer = Tracer()
        trace_id = "trace-tx-9999"

        with tracer.span("execute_test_run", trace_id=trace_id, metadata={"project_id": 1}) as root_span:
            time.sleep(0.01)
            with tracer.span("build_request", metadata={"endpoint": "/orders"}):
                time.sleep(0.005)
            with tracer.span("http_dispatch", metadata={"status_code": 200}):
                time.sleep(0.005)

        trace_data = tracer.get_trace(trace_id)
        self.assertIsNotNone(trace_data)
        self.assertEqual(trace_data["trace_id"], trace_id)
        self.assertEqual(trace_data["root_span_name"], "execute_test_run")
        self.assertEqual(trace_data["span_count"], 3)
        self.assertGreater(trace_data["total_duration_ms"], 0.0)

        # Check nested children
        children = trace_data["root_span"]["children"]
        self.assertEqual(len(children), 2)
        self.assertEqual(children[0]["name"], "build_request")
        self.assertEqual(children[1]["name"], "http_dispatch")

    def test_audit_repository_crud_and_filters(self):
        """Test AuditRepository event creation, filtering by type/severity/actor, and pagination."""
        repo = AuditRepository(self.db)

        # Record events
        repo.record_event(
            event_type="TEST_RUN_STARTED",
            severity="INFO",
            actor="worker_1",
            target_type="test_run",
            target_id="101",
            request_id="req-aaa",
            details={"test_count": 5},
        )
        repo.record_event(
            event_type="SAFETY_OVERRIDE",
            severity="CRITICAL",
            actor="admin_user",
            target_type="project",
            target_id="1",
            request_id="req-bbb",
            details={"reason": "Emergency rollback"},
        )
        repo.record_event(
            event_type="ENDPOINT_MUTATED",
            severity="WARNING",
            actor="developer",
            target_type="endpoint",
            target_id="42",
            request_id="req-ccc",
            details={"path": "/v2/users"},
        )

        # Filter by severity
        crit_events = repo.get_filtered(severity="CRITICAL")
        self.assertEqual(len(crit_events), 1)
        self.assertEqual(crit_events[0].event_type, "SAFETY_OVERRIDE")

        # Filter by actor
        worker_events = repo.get_filtered(actor="worker_1")
        self.assertEqual(len(worker_events), 1)
        self.assertEqual(worker_events[0].target_id, "101")

        # Count filtered
        total_count = repo.count_filtered()
        self.assertEqual(total_count, 3)

    def test_audit_summary_stats(self):
        """Test AuditRepository.get_summary_stats aggregation."""
        repo = AuditRepository(self.db)
        repo.record_event(event_type="TEST_RUN_STARTED", severity="INFO")
        repo.record_event(event_type="TEST_RUN_COMPLETED", severity="INFO")
        repo.record_event(event_type="CIRCUIT_BREAKER_TRIPPED", severity="CRITICAL")

        stats = repo.get_summary_stats()
        self.assertEqual(stats.total_events, 3)
        self.assertEqual(stats.severity_breakdown.INFO, 2)
        self.assertEqual(stats.severity_breakdown.CRITICAL, 1)
        self.assertEqual(stats.recent_critical_events, 1)
        self.assertIn("TEST_RUN_STARTED", stats.top_event_types)

    def test_audit_service_export_csv(self):
        """Test AuditService CSV export formatting."""
        repo = AuditRepository(self.db)
        repo.record_event(
            event_type="PROJECT_CREATED",
            severity="INFO",
            actor="system",
            target_type="project",
            target_id="5",
            details={"name": "Alpha"},
        )

        csv_text = AuditService.export_audit_csv(self.db)
        self.assertIn("ID,Timestamp,Event Type,Severity,Actor", csv_text)
        self.assertIn("PROJECT_CREATED", csv_text)
        self.assertIn("Alpha", csv_text)

    def test_rest_api_audit_endpoints(self):
        """Test REST endpoints: GET /api/v1/audit/events, POST /api/v1/audit/events, GET /summary."""
        # 1. POST record event
        payload = {
            "event_type": "AI_ANALYSIS_REQUESTED",
            "severity": "INFO",
            "actor": "user_ui",
            "target_type": "test_result",
            "target_id": "88",
            "request_id": "corr-777",
            "details": {"model": "gemini-1.5-flash"},
        }
        res_post = self.client.post("/api/v1/audit/events", json=payload)
        self.assertEqual(res_post.status_code, 201)
        data = res_post.json()
        self.assertEqual(data["event_type"], "AI_ANALYSIS_REQUESTED")
        self.assertEqual(data["actor"], "user_ui")

        # 2. GET events
        res_get = self.client.get("/api/v1/audit/events?event_type=AI_ANALYSIS_REQUESTED")
        self.assertEqual(res_get.status_code, 200)
        events_data = res_get.json()
        self.assertEqual(events_data["total"], 1)
        self.assertEqual(events_data["events"][0]["target_id"], "88")

        # 3. GET summary
        res_sum = self.client.get("/api/v1/audit/summary")
        self.assertEqual(res_sum.status_code, 200)
        sum_data = res_sum.json()
        self.assertEqual(sum_data["total_events"], 1)

        # 4. GET export CSV
        res_export_csv = self.client.get("/api/v1/audit/export?format=csv")
        self.assertEqual(res_export_csv.status_code, 200)
        self.assertEqual(res_export_csv.headers["content-type"], "text/csv; charset=utf-8")
        self.assertIn("AI_ANALYSIS_REQUESTED", res_export_csv.text)

    def test_rest_api_trace_and_live_logs(self):
        """Test GET /api/v1/audit/traces/{id}, GET /live-logs, and POST /live-logs/clear."""
        # Setup trace
        tracer = Tracer()
        with tracer.span("root_handler", trace_id="trace-api-test"):
            pass

        # 1. Query trace
        res_trace = self.client.get("/api/v1/audit/traces/trace-api-test")
        self.assertEqual(res_trace.status_code, 200)
        self.assertEqual(res_trace.json()["root_span_name"], "root_handler")

        # 404 for missing trace
        res_missing = self.client.get("/api/v1/audit/traces/nonexistent-trace")
        self.assertEqual(res_missing.status_code, 404)

        # 2. Query live logs
        buf = get_log_buffer()
        buf.append({"timestamp": "2026-09-09T12:00:00Z", "level": "INFO", "logger": "test", "message": "Live diagnostic message", "request_id": "req-1"})

        res_logs = self.client.get("/api/v1/audit/live-logs?search=diagnostic")
        self.assertEqual(res_logs.status_code, 200)
        log_data = res_logs.json()
        self.assertGreaterEqual(log_data["matched_count"], 1)

        # 3. Clear live logs
        res_clear = self.client.post("/api/v1/audit/live-logs/clear")
        self.assertEqual(res_clear.status_code, 200)
        self.assertEqual(res_clear.json()["status"], "cleared")


if __name__ == "__main__":
    unittest.main()
