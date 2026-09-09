"""Comprehensive unit and integration tests for Stage 24: Error Handling & Resilience."""
import unittest
import time
from fastapi.testclient import TestClient

from app.main import app
from app.core.exceptions import (
    SentinelBaseException,
    EntityNotFoundException,
    ContractValidationException,
    ExecutionTimeoutException,
    NetworkConnectivityException,
    SafetyViolationException,
    CircuitBreakerOpenException,
    ParserException,
)
from app.core.circuit_breaker import CircuitBreaker, CircuitBreakerRegistry, CircuitState
from app.utils.safe_parsers import safe_json_loads, safe_xml_loads, safe_yaml_loads, safe_decode_payload
from app.services.resilience_service import ResilienceService


class TestResilienceAndErrorHandling(unittest.TestCase):
    """Test suite covering CircuitBreaker, Safe Parsers, Exception Handlers, and Resilience APIs."""

    def setUp(self):
        self.client = TestClient(app)
        CircuitBreakerRegistry().clear()

    def tearDown(self):
        CircuitBreakerRegistry().clear()

    def test_circuit_breaker_lifecycle(self):
        """Test CircuitBreaker state transitions: CLOSED -> 5 failures -> OPEN -> timeout -> HALF_OPEN -> success -> CLOSED."""
        breaker = CircuitBreaker(host="api.flaky-service.com", failure_threshold=3, recovery_timeout_seconds=0.1, half_open_max_trials=1)
        self.assertEqual(breaker.state, CircuitState.CLOSED)
        self.assertTrue(breaker.can_execute())

        # 1. Record 2 failures (under threshold of 3)
        breaker.record_failure(Exception("500 Server Error"))
        breaker.record_failure(Exception("500 Server Error"))
        self.assertEqual(breaker.state, CircuitState.CLOSED)
        self.assertTrue(breaker.can_execute())

        # 2. Record 3rd failure -> Trip to OPEN
        breaker.record_failure(Exception("504 Gateway Timeout"))
        self.assertEqual(breaker.state, CircuitState.OPEN)
        self.assertFalse(breaker.can_execute())

        # 3. Check and raise exception
        with self.assertRaises(CircuitBreakerOpenException):
            breaker.check_and_raise()

        # 4. Wait for recovery cooldown (0.1s)
        time.sleep(0.15)
        self.assertTrue(breaker.can_execute())
        self.assertEqual(breaker.state, CircuitState.HALF_OPEN)

        # 5. Record success in HALF_OPEN -> Recovers to CLOSED
        breaker.record_success()
        self.assertEqual(breaker.state, CircuitState.CLOSED)
        self.assertEqual(breaker.consecutive_failures, 0)
        self.assertTrue(breaker.can_execute())

    def test_circuit_breaker_half_open_failure_re_trips(self):
        """Test that failure in HALF_OPEN immediately re-trips back to OPEN."""
        breaker = CircuitBreaker(host="api.dead-service.com", failure_threshold=1, recovery_timeout_seconds=0.05)
        breaker.record_failure()
        self.assertEqual(breaker.state, CircuitState.OPEN)

        time.sleep(0.06)
        self.assertTrue(breaker.can_execute())
        self.assertEqual(breaker.state, CircuitState.HALF_OPEN)

        # Trial probe fails
        breaker.record_failure(Exception("Still Down"))
        self.assertEqual(breaker.state, CircuitState.OPEN)
        self.assertFalse(breaker.can_execute())

    def test_circuit_breaker_registry(self):
        """Test CircuitBreakerRegistry singleton host management and reset."""
        registry = CircuitBreakerRegistry()
        b1 = registry.get_breaker("https://api.alpha.com/v1/orders")
        b2 = registry.get_breaker("api.alpha.com")
        self.assertIs(b1, b2)
        self.assertEqual(b1.host, "api.alpha.com")

        b1.record_failure()
        self.assertEqual(len(registry.get_all()), 1)

        # Reset
        self.assertTrue(registry.reset_breaker("api.alpha.com"))
        self.assertEqual(b1.failure_count, 0)

    def test_safe_json_loads(self):
        """Test safe_json_loads handles malformed, empty, and valid JSON gracefully."""
        # Valid
        data, err = safe_json_loads('{"status": "ok", "count": 42}')
        self.assertIsNone(err)
        self.assertEqual(data["count"], 42)

        # Malformed
        bad_data, err = safe_json_loads('{invalid_json: true')
        self.assertIsNone(bad_data)
        self.assertIsNotNone(err)
        self.assertIn("JSON parse error", err)

        # Empty / None
        none_data, err = safe_json_loads(None, default={})
        self.assertIsNone(err)
        self.assertEqual(none_data, {})

    def test_safe_yaml_and_xml_loads(self):
        """Test safe_yaml_loads and safe_xml_loads resilience."""
        # Valid YAML
        y_data, y_err = safe_yaml_loads("name: Alice\nage: 30")
        self.assertIsNone(y_err)

        self.assertEqual(y_data["name"], "Alice")

        # Invalid YAML
        bad_y, y_err = safe_yaml_loads("key: [unclosed")
        self.assertIsNotNone(y_err)

        # Valid XML
        x_data, x_err = safe_xml_loads("<root><item id='1'>Test</item></root>")
        self.assertIsNone(x_err)
        self.assertIsNotNone(x_data)

        # Invalid XML
        bad_x, x_err = safe_xml_loads("<root><unclosed></root>")
        self.assertIsNotNone(x_err)

    def test_safe_decode_payload(self):
        """Test safe_decode_payload with binary and utf-8 bytes."""
        self.assertEqual(safe_decode_payload(b"Hello World"), "Hello World")
        self.assertEqual(safe_decode_payload(b""), "")
        # Invalid UTF-8 bytes should not crash
        res = safe_decode_payload(bytes([0xFF, 0xFE, 0xFD]))
        self.assertIsInstance(res, str)


    def test_resilience_service_error_summary(self):
        """Test ResilienceService error recording and summary aggregation."""
        ResilienceService.record_error("TEST_ERROR", "Test error message")
        ResilienceService.record_ai_fallback()

        summary = ResilienceService.get_error_summary()
        self.assertGreater(summary.total_errors_handled, 0)
        self.assertGreaterEqual(summary.ai_fallback_invocations, 1)

    def test_resilience_circuit_breaker_apis(self):
        """Test GET /api/v1/resilience/circuit-breakers and POST reset endpoints."""
        registry = CircuitBreakerRegistry()
        b = registry.get_breaker("api.partner.com")
        b.record_failure()

        # GET list
        res = self.client.get("/api/v1/resilience/circuit-breakers")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertGreaterEqual(data["total_breakers"], 1)

        # POST reset host
        res_reset = self.client.post("/api/v1/resilience/circuit-breakers/api.partner.com/reset")
        self.assertEqual(res_reset.status_code, 200)
        self.assertEqual(res_reset.json()["new_state"], "CLOSED")

        # POST reset all
        res_all = self.client.post("/api/v1/resilience/circuit-breakers/reset-all")
        self.assertEqual(res_all.status_code, 200)

        # GET error summary
        res_err = self.client.get("/api/v1/resilience/error-summary")
        self.assertEqual(res_err.status_code, 200)
        self.assertIn("total_errors_handled", res_err.json())


if __name__ == "__main__":
    unittest.main()
