"""Tests for Structured Logging, Request-ID Correlation Middleware, and Health Check."""
import json
import logging
import unittest
import uuid
from fastapi.testclient import TestClient
from app.main import app
from app.core.logging import JSONLogFormatter, request_id_ctx_var


class TestLoggingAndHealth(unittest.TestCase):
    """Test suite for logging formatters, correlation middleware, and health diagnostics."""

    def setUp(self):
        self.client = TestClient(app)

    def test_request_id_generated_automatically(self):
        """Verify X-Request-ID and X-Response-Time-Ms are injected in response headers."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("x-request-id", response.headers)
        self.assertIn("x-response-time-ms", response.headers)
        # Verify valid UUID structure
        req_id = response.headers["x-request-id"]
        self.assertTrue(len(req_id) > 10)

    def test_custom_request_id_preserved(self):
        """Verify client-supplied X-Request-ID is preserved and reflected."""
        custom_id = f"custom-trace-{uuid.uuid4().hex[:8]}"
        response = self.client.get("/", headers={"X-Request-ID": custom_id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("x-request-id"), custom_id)

    def test_detailed_health_check_payload(self):
        """Verify /api/v1/health returns full diagnostics (uptime, database, ai_engine)."""
        response = self.client.get("/api/v1/health")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        
        self.assertTrue(payload["success"])
        data = payload["data"]
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["version"], "0.1.0")
        self.assertIn("uptime_seconds", data)
        self.assertTrue(data["uptime_seconds"] >= 0)
        self.assertEqual(data["database"]["status"], "connected")
        self.assertIn("engine", data["database"])
        self.assertIn("ai_engine", data)

    def test_json_log_formatter(self):
        """Verify JSONLogFormatter produces valid parseable JSON with context."""
        formatter = JSONLogFormatter()
        token = request_id_ctx_var.set("test-trace-1234")
        try:
            record = logging.LogRecord(
                name="test_logger",
                level=logging.INFO,
                pathname="test_path.py",
                lineno=42,
                msg="Sample diagnostic message",
                args=(),
                exc_info=None
            )
            formatted = formatter.format(record)
            log_json = json.loads(formatted)
            
            self.assertEqual(log_json["level"], "INFO")
            self.assertEqual(log_json["message"], "Sample diagnostic message")
            self.assertEqual(log_json["request_id"], "test-trace-1234")
            self.assertIn("timestamp", log_json)
        finally:
            request_id_ctx_var.reset(token)


if __name__ == "__main__":
    unittest.main()
