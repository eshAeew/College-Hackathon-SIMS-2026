"""Unit and integration tests for Stage 18: Failure Analysis Engine."""
import unittest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.entities.test_result import TestResult
from app.models.entities.test_run import TestRun
from app.models.schemas.failure_analysis import RootCauseCategory
from app.utils.evidence_packager import (
    build_curl_command,
    build_historical_context,
    categorize_root_cause,
    derive_severity,
    mask_sensitive_headers,
    snippet_body,
)

SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


class TestStage18Primitives(unittest.TestCase):
    """Test pure helper primitives in evidence packager."""

    def test_01_mask_sensitive_headers(self):
        headers = {
            "Authorization": "Bearer super-secret-jwt-token",
            "Cookie": "session_id=123456",
            "X-API-Key": "my-secret-key",
            "Content-Type": "application/json",
            "User-Agent": "APISentinel/1.0",
        }
        masked = mask_sensitive_headers(headers)
        self.assertEqual(masked["Authorization"], "***REDACTED***")
        self.assertEqual(masked["Cookie"], "***REDACTED***")
        self.assertEqual(masked["X-API-Key"], "***REDACTED***")
        self.assertEqual(masked["Content-Type"], "application/json")
        self.assertEqual(masked["User-Agent"], "APISentinel/1.0")

    def test_02_snippet_body_truncation(self):
        long_body = "A" * 6000
        truncated = snippet_body(long_body, max_len=4096)
        self.assertLess(len(truncated), 6000)
        self.assertIn("truncated", truncated)

    def test_03_curl_command_masks_secrets(self):
        cmd = build_curl_command(
            "POST",
            "https://api.example.com/login",
            headers={"Authorization": "Bearer leak-token", "Content-Type": "application/json"},
            body={"email": "user@example.com"}
        )
        self.assertIn("curl -X POST", cmd)
        self.assertNotIn("leak-token", cmd)
        self.assertIn("***REDACTED***", cmd)
        self.assertIn("user@example.com", cmd)

    def test_04_historical_context_ratings(self):
        h_chronic = build_historical_context(previous_failures=9, total_observations=10)
        self.assertEqual(h_chronic.persistence_rating, "CHRONIC")
        self.assertEqual(h_chronic.failure_rate_pct, 90.0)

        h_intermittent = build_historical_context(previous_failures=3, total_observations=10)
        self.assertEqual(h_intermittent.persistence_rating, "INTERMITTENT")

        h_new = build_historical_context(previous_failures=0, total_observations=1)
        self.assertEqual(h_new.persistence_rating, "NEW")

    def test_05_root_cause_categories(self):
        # Missing input validation (negative test + 500)
        a1 = categorize_root_cause(status_code=500, expected_status=400, is_negative_test=True)
        self.assertEqual(a1.category, RootCauseCategory.MISSING_INPUT_VALIDATION)
        self.assertEqual(derive_severity(a1).value, "CRITICAL")

        # Plain server exception
        a2 = categorize_root_cause(status_code=500, expected_status=200)
        self.assertEqual(a2.category, RootCauseCategory.SERVER_EXCEPTION)

        # Network timeout
        a3 = categorize_root_cause(network_error="ConnectTimeout: Connection timed out")
        self.assertEqual(a3.category, RootCauseCategory.NETWORK_TIMEOUT)

        # Schema mismatch
        a4 = categorize_root_cause(schema_errors=["Field 'id' required"])
        self.assertEqual(a4.category, RootCauseCategory.RESPONSE_CONTRACT_MISMATCH)

        # Performance SLA breach
        a5 = categorize_root_cause(latency_ms=1200.0, max_latency_ms=500.0)
        self.assertEqual(a5.category, RootCauseCategory.PERFORMANCE_SLA_BREACH)

        # Auth failures
        self.assertEqual(categorize_root_cause(status_code=401).category, RootCauseCategory.AUTHENTICATION_FAILURE)
        self.assertEqual(categorize_root_cause(status_code=403).category, RootCauseCategory.AUTHORIZATION_FAILURE)
        self.assertEqual(categorize_root_cause(status_code=429).category, RootCauseCategory.RATE_LIMITED)
        self.assertEqual(categorize_root_cause(status_code=404).category, RootCauseCategory.ENDPOINT_NOT_FOUND)
        self.assertEqual(categorize_root_cause(status_code=405).category, RootCauseCategory.METHOD_NOT_ALLOWED)
        self.assertEqual(categorize_root_cause(status_code=201, expected_status=200).category, RootCauseCategory.STATUS_CODE_MISMATCH)


class TestStage18Api(unittest.TestCase):
    """Integration tests for Stage 18 REST endpoints."""

    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=test_engine)
        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)

        # Seed test project and run with test results
        p_res = cls.client.post("/api/v1/projects", json={
            "name": "Failure Analysis Project",
            "base_url": "https://api.example.com"
        }).json()["data"]
        cls.project_id = p_res["id"]

        ep_res = cls.client.post(f"/api/v1/projects/{cls.project_id}/endpoints", json={
            "name": "Checkout",
            "method": "POST",
            "path": "/checkout"
        }).json()["data"]
        cls.endpoint_id = ep_res["id"]

        db = TestingSessionLocal()
        run = TestRun(
            project_id=cls.project_id,
            name="Run with Failures",
            status="COMPLETED",
            total_tests=2,
            passed_tests=1,
            failed_tests=1
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        cls.run_id = run.id

        res_pass = TestResult(
            run_id=cls.run_id,
            endpoint_id=cls.endpoint_id,
            test_name="checkout-valid",
            status="PASS",
            http_method="POST",
            url="https://api.example.com/checkout",
            response_code=200,
            response_time_ms=80.0
        )
        res_fail = TestResult(
            run_id=cls.run_id,
            endpoint_id=cls.endpoint_id,
            test_name="checkout-bad-payload",
            status="FAIL",
            http_method="POST",
            url="https://api.example.com/checkout",
            response_code=500,
            response_time_ms=450.0,
            response_body_snippet="Internal Server Error: NullPointerException",
            failure_type="SERVER_ERROR"
        )
        db.add_all([res_pass, res_fail])
        db.commit()
        db.refresh(res_fail)
        cls.failing_result_id = res_fail.id
        db.close()

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(bind=test_engine)
        app.dependency_overrides.clear()

    def test_06_package_evidence_endpoint(self):
        resp = self.client.post("/api/v1/failure-analysis/package", json={
            "test_name": "checkout-bad-payload",
            "http_method": "POST",
            "url": "https://api.example.com/checkout",
            "request_headers": {"Authorization": "Bearer secret-token", "Content-Type": "application/json"},
            "request_body": {"item_id": 999},
            "status_code": 500,
            "expected_status": 400,
            "is_negative_test": True,
            "response_body": "Internal Server Error: NullPointerException"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertTrue(data["evidence_id"].startswith("EV-"))
        self.assertEqual(data["root_cause"]["category"], "MISSING_INPUT_VALIDATION")
        self.assertEqual(data["severity"], "CRITICAL")
        self.assertEqual(data["request"]["headers"]["Authorization"], "***REDACTED***")
        self.assertIn("curl -X POST", data["request"]["curl_command"])

    def test_07_categorize_endpoint(self):
        resp = self.client.post("/api/v1/failure-analysis/categorize", json={
            "status_code": 401,
            "expected_status": 200
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["category"], "AUTHENTICATION_FAILURE")

    def test_08_get_result_evidence_endpoint(self):
        resp = self.client.get(f"/api/v1/results/{self.failing_result_id}/evidence")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["test_name"], "checkout-bad-payload")
        self.assertEqual(data["root_cause"]["category"], "SERVER_EXCEPTION")

    def test_09_get_run_failure_analysis_endpoint(self):
        resp = self.client.get(f"/api/v1/runs/{self.run_id}/failure-analysis")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["total_failures"], 1)
        self.assertIn("SERVER_EXCEPTION", data["category_breakdown"])

    def test_10_not_found_handlers(self):
        self.assertEqual(self.client.get("/api/v1/results/99999/evidence").status_code, 404)
        self.assertEqual(self.client.get("/api/v1/runs/99999/failure-analysis").status_code, 404)


if __name__ == "__main__":
    unittest.main()
