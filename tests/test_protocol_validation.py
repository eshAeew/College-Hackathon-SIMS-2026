"""Tests for Protocol & Format Validation Engine (Stage 07 Sub-Stage 01)."""
import unittest
from fastapi.testclient import TestClient

from app.main import app
from app.utils.protocol_validator import (
    validate_status_code,
    validate_content_type,
    validate_payload_syntax,
    normalize_content_type,
)
from app.services.validation_service import ValidationService
from app.models.schemas.validation import ProtocolValidationRequest


class TestProtocolValidatorUtils(unittest.TestCase):
    """Unit tests for low-level protocol validator utility functions."""

    def test_status_code_exact_match(self):
        passed, msg = validate_status_code(200, 200)
        self.assertTrue(passed)
        self.assertIn("matches expected 200", msg)

        passed, msg = validate_status_code(404, 200)
        self.assertFalse(passed)
        self.assertIn("Expected HTTP status 200, but received 404", msg)

    def test_status_code_list(self):
        passed, msg = validate_status_code(201, [200, 201, 204])
        self.assertTrue(passed)
        self.assertIn("is in allowed list", msg)

        passed, msg = validate_status_code(500, [200, 201])
        self.assertFalse(passed)
        self.assertIn("Expected HTTP status in [200, 201], but received 500", msg)

    def test_status_code_class_range(self):
        passed, msg = validate_status_code(200, "2xx")
        self.assertTrue(passed)
        self.assertIn("satisfies 2XX range", msg)

        passed, msg = validate_status_code(204, "2XX")
        self.assertTrue(passed)

        passed, msg = validate_status_code(404, "2xx")
        self.assertFalse(passed)

        passed, msg = validate_status_code(503, "5xx")
        self.assertTrue(passed)

    def test_status_code_numeric_range(self):
        passed, msg = validate_status_code(204, "200-299")
        self.assertTrue(passed)
        self.assertIn("is within range [200, 299]", msg)

        passed, msg = validate_status_code(301, "200-299")
        self.assertFalse(passed)

    def test_content_type_normalization_and_matching(self):
        self.assertEqual(normalize_content_type("application/json; charset=utf-8"), "application/json")
        self.assertEqual(normalize_content_type("json"), "application/json")
        self.assertEqual(normalize_content_type("xml"), "application/xml")

        # Exact and normalized matching
        passed, msg = validate_content_type("application/json; charset=utf-8", "application/json")
        self.assertTrue(passed)

        # Alias matching
        passed, msg = validate_content_type("application/json", "json")
        self.assertTrue(passed)

        # Problem JSON structured suffix matching
        passed, msg = validate_content_type("application/problem+json; charset=utf-8", "application/json")
        self.assertTrue(passed)

        # Mismatch
        passed, msg = validate_content_type("text/html", "application/json")
        self.assertFalse(passed)
        self.assertIn("Expected Content-Type 'application/json', but received 'text/html'", msg)

        # Missing Content-Type
        passed, msg = validate_content_type(None, "application/json")
        self.assertFalse(passed)
        self.assertIn("no Content-Type header was returned", msg)

    def test_payload_syntax_json(self):
        # Valid JSON
        passed, parsed, err, desc = validate_payload_syntax('{"key": "value", "count": 10}', "json")
        self.assertTrue(passed)
        self.assertEqual(parsed, {"key": "value", "count": 10})
        self.assertIsNone(err)

        # Valid pre-parsed dict
        passed, parsed, err, desc = validate_payload_syntax({"id": 1}, "json")
        self.assertTrue(passed)
        self.assertEqual(parsed, {"id": 1})

        # Malformed JSON
        passed, parsed, err, desc = validate_payload_syntax('{"key": "unclosed}', "json")
        self.assertFalse(passed)
        self.assertIsNone(parsed)
        self.assertIn("Malformed JSON", err)

    def test_payload_syntax_xml(self):
        # Valid XML
        xml_data = "<response><status>OK</status><id>123</id></response>"
        passed, parsed, err, desc = validate_payload_syntax(xml_data, "xml")
        self.assertTrue(passed)
        self.assertEqual(parsed, "response")

        # Malformed XML
        bad_xml = "<response><status>OK</unclosed>"
        passed, parsed, err, desc = validate_payload_syntax(bad_xml, "xml")
        self.assertFalse(passed)
        self.assertIn("Malformed XML syntax", err)

    def test_payload_syntax_text_and_binary(self):
        passed, parsed, err, desc = validate_payload_syntax("Hello Plain Text", "text")
        self.assertTrue(passed)
        self.assertEqual(parsed, "Hello Plain Text")

        passed, parsed, err, desc = validate_payload_syntax(b"rawbytes", "binary")
        self.assertTrue(passed)


class TestValidationService(unittest.TestCase):
    """Unit tests for ValidationService composite logic."""

    def test_composite_protocol_validation_success(self):
        req = ProtocolValidationRequest(
            actual_status=200,
            expected_status="2xx",
            actual_content_type="application/json; charset=utf-8",
            expected_content_type="json",
            raw_payload='{"success": true}',
            expected_payload_format="json"
        )
        report = ValidationService.validate_protocol(req)
        self.assertTrue(report.all_passed)
        self.assertEqual(report.total_checks, 3)
        self.assertEqual(report.passed_checks, 3)
        self.assertEqual(report.failed_checks, 0)
        self.assertEqual(report.parsed_payload, {"success": True})

    def test_composite_protocol_validation_partial_failure(self):
        req = ProtocolValidationRequest(
            actual_status=500,
            expected_status="2xx",
            actual_content_type="text/plain",
            expected_content_type="json",
            raw_payload="Internal Server Error",
            expected_payload_format="text"
        )
        report = ValidationService.validate_protocol(req)
        self.assertFalse(report.all_passed)
        self.assertEqual(report.total_checks, 3)
        self.assertEqual(report.passed_checks, 1)  # Only text syntax passed
        self.assertEqual(report.failed_checks, 2)


class TestValidationAPIEndpoints(unittest.TestCase):
    """Integration tests for Validation API routes."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_api_status_code_validation(self):
        res = self.client.post("/api/v1/validations/status-code", json={
            "actual_status": 201,
            "expected_status": "2xx"
        })
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["success"])
        self.assertTrue(body["data"]["passed"])
        self.assertEqual(body["data"]["check_type"], "status_code")

    def test_api_content_type_validation(self):
        res = self.client.post("/api/v1/validations/content-type", json={
            "actual_content_type": "application/json; charset=utf-8",
            "expected_content_type": "json"
        })
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["success"])
        self.assertTrue(body["data"]["passed"])

    def test_api_payload_syntax_validation(self):
        # Valid
        res = self.client.post("/api/v1/validations/payload-syntax", json={
            "payload": '{"foo": "bar"}',
            "expected_format": "json"
        })
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["success"])
        self.assertTrue(body["data"]["passed"])

        # Invalid
        res = self.client.post("/api/v1/validations/payload-syntax", json={
            "payload": "{invalid_json}",
            "expected_format": "json"
        })
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertFalse(body["success"])
        self.assertFalse(body["data"]["passed"])

    def test_api_composite_protocol_validation(self):
        res = self.client.post("/api/v1/validations/protocol", json={
            "actual_status": 200,
            "expected_status": "200-299",
            "actual_content_type": "application/json",
            "expected_content_type": "application/json",
            "raw_payload": '{"message": "hello"}',
            "expected_payload_format": "json"
        })
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["success"])
        self.assertTrue(body["data"]["all_passed"])
        self.assertEqual(body["data"]["total_checks"], 3)


if __name__ == "__main__":
    unittest.main()
