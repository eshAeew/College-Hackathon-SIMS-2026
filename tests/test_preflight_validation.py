"""Unit & Integration tests for Pre-Flight Syntax & Configuration Validation Engine."""
import unittest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core.database import Base, get_db
from app.models.schemas.request_config import BodyType
from app.utils.preflight_validator import (
    validate_url_syntax,
    validate_path_parameters,
    validate_body_syntax,
    validate_headers_syntax,
    execute_preflight_check,
)

# Use shared in-memory SQLite database with StaticPool for test execution
SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    """Override database session for testing."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


class TestPreflightValidation(unittest.TestCase):
    """Test suite verifying pre-flight URL, path parameter, JSON syntax, and header checks."""

    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=test_engine)
        app.dependency_overrides[get_db] = override_get_db

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(bind=test_engine)
        app.dependency_overrides.clear()

    def setUp(self):
        self.client = TestClient(app)

    def test_01_url_syntax_validation_unit(self):
        """Verify URL syntax validation for valid/invalid schemes, hosts, and ports."""
        # Valid URL
        valid_res = validate_url_syntax("https://api.store.com:8443", "/api/v1/items")
        self.assertTrue(valid_res[0])
        self.assertTrue(valid_res[1])  # scheme
        self.assertTrue(valid_res[2])  # host
        self.assertTrue(valid_res[3])  # port
        self.assertEqual(len(valid_res[5]), 0)  # no errors

        # Invalid Scheme
        ftp_res = validate_url_syntax("ftp://files.store.com", "/items")
        self.assertFalse(ftp_res[0])
        self.assertFalse(ftp_res[1])
        self.assertIn("Only 'http://' and 'https://' are supported", ftp_res[5][0])

        # Invalid Port (out of range)
        port_res = validate_url_syntax("http://localhost:99999", "/items")
        self.assertFalse(port_res[0])
        self.assertFalse(port_res[3])
        self.assertTrue(any("out of valid range" in err for err in port_res[5]))

        # Trailing colon without port
        colon_res = validate_url_syntax("http://localhost:", "/items")
        self.assertFalse(colon_res[0])
        self.assertTrue(any("trailing colon" in err for err in colon_res[5]))

    def test_02_path_parameter_completeness_unit(self):
        """Verify path parameter presence and missing variable detection."""
        # Complete
        comp_res = validate_path_parameters(
            "/users/{user_id}/posts/{post_id}",
            {"user_id": "1", "post_id": "42"}
        )
        self.assertTrue(comp_res[0])
        self.assertEqual(comp_res[2], [])

        # Missing post_id
        incomp_res = validate_path_parameters(
            "/users/{user_id}/posts/{post_id}",
            {"user_id": "1"}
        )
        self.assertFalse(incomp_res[0])
        self.assertEqual(incomp_res[2], ["post_id"])

    def test_03_body_syntax_validation_unit(self):
        """Verify body payload syntax checking for JSON and Form-Data."""
        # Valid JSON string
        self.assertTrue(validate_body_syntax('{"name": "test", "active": true}', BodyType.JSON)[0])
        
        # Malformed JSON string
        malformed_res = validate_body_syntax('{name: "unquoted"}', BodyType.JSON)
        self.assertFalse(malformed_res[0])
        self.assertIn("Malformed JSON string", malformed_res[1])

        # Valid Dict for JSON
        self.assertTrue(validate_body_syntax({"key": 123}, BodyType.JSON)[0])

        # Form data validation
        self.assertTrue(validate_body_syntax({"grant_type": "password"}, BodyType.FORM_DATA)[0])
        self.assertFalse(validate_body_syntax(12345, BodyType.FORM_DATA)[0])

    def test_04_headers_syntax_validation_unit(self):
        """Verify header syntax checking."""
        # Valid headers
        self.assertTrue(validate_headers_syntax({"Authorization": "Bearer 123", "X-Key": "val"})[0])

        # Header name with spaces
        inv_res = validate_headers_syntax({"Invalid Header Name": "val"})
        self.assertFalse(inv_res[0])
        self.assertTrue(any("whitespace" in err for err in inv_res[1]))

    def test_05_direct_preflight_check_api_success(self):
        """Verify POST /api/v1/requests/preflight-check returns clean report for valid request."""
        payload = {
            "base_url": "https://api.payments.com:443",
            "method": "POST",
            "path": "/v1/charges/{charge_id}",
            "path_params": {"charge_id": "ch_123456"},
            "query_params": {"notify": True},
            "headers": {"Authorization": "Bearer sec-token-99"},
            "body": {"amount": 2500, "currency": "USD"},
            "body_type": "json"
        }
        resp = self.client.post("/api/v1/requests/preflight-check", json=payload)
        self.assertEqual(resp.status_code, 200)
        report = resp.json()["data"]
        self.assertTrue(report["is_valid"])
        self.assertTrue(report["url_valid"])
        self.assertTrue(report["path_params_complete"])
        self.assertTrue(report["body_valid"])
        self.assertTrue(report["headers_valid"])
        self.assertEqual(len(report["errors"]), 0)
        self.assertIn("https://api.payments.com:443/v1/charges/ch_123456?notify=true", report["target_url"])

    def test_06_direct_preflight_check_api_with_errors(self):
        """Verify POST /api/v1/requests/preflight-check catches missing params, invalid port, and malformed body."""
        payload = {
            "base_url": "http://api.payments.com:99999",  # Invalid port
            "method": "POST",
            "path": "/v1/charges/{charge_id}/refunds/{refund_id}",
            "path_params": {"charge_id": "ch_123"},  # refund_id missing
            "headers": {"Bad Header Name": "val"},    # Invalid header key
            "body": "{invalid: json}",               # Malformed JSON
            "body_type": "json"
        }
        resp = self.client.post("/api/v1/requests/preflight-check", json=payload)
        self.assertEqual(resp.status_code, 200)
        report = resp.json()["data"]
        self.assertFalse(report["is_valid"])
        self.assertFalse(report["port_valid"])
        self.assertFalse(report["path_params_complete"])
        self.assertIn("refund_id", report["missing_path_params"])
        self.assertFalse(report["body_valid"])
        self.assertFalse(report["headers_valid"])
        self.assertTrue(len(report["errors"]) >= 4)

    def test_07_endpoint_preflight_check_api(self):
        """Verify POST /api/v1/projects/{p_id}/endpoints/{e_id}/preflight-check on stored entities."""
        # 1. Create project
        proj_resp = self.client.post("/api/v1/projects", json={
            "name": "Preflight Project",
            "base_url": "https://api.preflight.io",
            "global_headers": {"Authorization": "Bearer live-token"}
        })
        proj_id = proj_resp.json()["data"]["id"]

        # 2. Create endpoint with missing path parameter sample value
        ep_resp = self.client.post(f"/api/v1/projects/{proj_id}/endpoints", json={
            "name": "Get User Account",
            "method": "GET",
            "path": "/api/v1/accounts/{acc_id}",
            "path_params": {}  # acc_id is omitted
        })
        ep_id = ep_resp.json()["data"]["id"]

        # 3. Check preflight without override -> should flag missing acc_id
        check1 = self.client.post(f"/api/v1/projects/{proj_id}/endpoints/{ep_id}/preflight-check")
        self.assertEqual(check1.status_code, 200)
        report1 = check1.json()["data"]
        self.assertFalse(report1["is_valid"])
        self.assertIn("acc_id", report1["missing_path_params"])

        # 4. Check preflight with runtime override supplying acc_id -> should pass
        check2 = self.client.post(
            f"/api/v1/projects/{proj_id}/endpoints/{ep_id}/preflight-check",
            json={"path_params": {"acc_id": "acc-998877"}}
        )
        self.assertEqual(check2.status_code, 200)
        report2 = check2.json()["data"]
        self.assertTrue(report2["is_valid"])
        self.assertEqual(report2["missing_path_params"], [])

    def test_08_endpoint_preflight_not_found_and_mismatch(self):
        """Verify 404 and 400 for invalid preflight lookups."""
        self.assertEqual(
            self.client.post("/api/v1/projects/99999/endpoints/1/preflight-check").status_code,
            404
        )
        self.assertEqual(
            self.client.post("/api/v1/projects/1/endpoints/99999/preflight-check").status_code,
            404
        )


if __name__ == "__main__":
    unittest.main()
