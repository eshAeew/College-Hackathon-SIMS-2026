"""Unit and Integration Tests for Result Classification Engine (Stage 17)."""
import json
import unittest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.entities.project import Project
from app.models.entities.test_result import TestResult
from app.models.entities.test_run import TestRun
from app.models.schemas.result_classification import (
    BatchClassificationRequest,
    ClassificationSeverity,
    ExecutionClassificationInput,
    ExecutionOutcomeTier,
    FailureSubCategory,
)
from app.utils.result_classifier import (
    classify_batch_executions,
    classify_execution,
)


class TestResultClassifierUnit(unittest.TestCase):
    """Unit tests for the 4-tier decision matrix and severity classifier."""

    def test_pass_classification(self):
        """Verify clean passing executions receive PASS outcome and NONE severity."""
        inp = ExecutionClassificationInput(
            test_name="Get User Profile",
            http_method="GET",
            url="/users/1",
            status_code=200,
            expected_status=200,
            latency_ms=45.2,
            max_latency_ms=500.0,
            assertions_passed=True
        )
        res = classify_execution(inp)
        self.assertEqual(res.outcome, ExecutionOutcomeTier.PASS)
        self.assertEqual(res.severity, ClassificationSeverity.NONE)
        self.assertEqual(res.priority_rank, 5)

    def test_fail_status_mismatch(self):
        """Verify status code mismatches are classified as FAIL with HIGH/MEDIUM severity."""
        inp = ExecutionClassificationInput(
            test_name="Checkout Cart",
            http_method="POST",
            url="/cart/checkout",
            status_code=400,
            expected_status=201,
            assertions_passed=False,
            endpoint_severity="high"
        )
        res = classify_execution(inp)
        self.assertEqual(res.outcome, ExecutionOutcomeTier.FAIL)
        self.assertEqual(res.severity, ClassificationSeverity.HIGH)
        self.assertEqual(res.sub_category, FailureSubCategory.STATUS_CODE_MISMATCH)
        self.assertEqual(res.priority_rank, 2)

    def test_error_http_500_on_negative_test(self):
        """Verify HTTP 500 crashes on negative input are flagged as CRITICAL."""
        inp = ExecutionClassificationInput(
            test_name="Negative Fuzz - Null Injection",
            http_method="POST",
            url="/orders",
            status_code=500,
            expected_status=400,
            is_negative_test=True,
            assertions_passed=False
        )
        res = classify_execution(inp)
        self.assertEqual(res.outcome, ExecutionOutcomeTier.ERROR)
        self.assertEqual(res.severity, ClassificationSeverity.CRITICAL)
        self.assertEqual(res.sub_category, FailureSubCategory.HTTP_500_SERVER_CRASH)
        self.assertEqual(res.priority_rank, 1)

    def test_warning_latency_sla_breach(self):
        """Verify functional passes with high latency receive WARNING outcome."""
        inp = ExecutionClassificationInput(
            test_name="Search Products",
            http_method="GET",
            url="/products/search",
            status_code=200,
            expected_status=200,
            latency_ms=1200.0,
            max_latency_ms=500.0,
            assertions_passed=True
        )
        res = classify_execution(inp)
        self.assertEqual(res.outcome, ExecutionOutcomeTier.WARNING)
        self.assertEqual(res.sub_category, FailureSubCategory.LATENCY_SLA_BREACH)
        self.assertIn("SLA Warning", res.title)

    def test_error_network_connection_refused(self):
        """Verify network exceptions are classified as ERROR."""
        inp = ExecutionClassificationInput(
            test_name="External Service",
            http_method="GET",
            url="http://unreachable-host:9999/api",
            network_error="[Errno 111] Connection refused",
            assertions_passed=False
        )
        res = classify_execution(inp)
        self.assertEqual(res.outcome, ExecutionOutcomeTier.ERROR)
        self.assertEqual(res.severity, ClassificationSeverity.HIGH)
        self.assertEqual(res.sub_category, FailureSubCategory.NETWORK_CONNECTIVITY_ERROR)


class TestResultClassificationAPIIntegration(unittest.TestCase):
    """Integration tests for Result Classification REST API endpoints."""

    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool
        )
        Base.metadata.create_all(bind=self.engine)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

        def override_get_db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

        # Seed Database Project, TestRun, and TestResult records
        db = self.SessionLocal()
        self.project = Project(
            name="Payment Service",
            description="Testing classification",
            base_url="https://pay.example.com",
            environment="staging"
        )
        db.add(self.project)
        db.commit()
        db.refresh(self.project)
        self.project_id = self.project.id

        self.test_run = TestRun(
            project_id=self.project_id,
            name="Nightly Classification Run",
            status="COMPLETED",
            environment="staging",
            total_tests=3,
            passed_tests=1,
            failed_tests=1,
            error_tests=1
        )
        db.add(self.test_run)
        db.commit()
        db.refresh(self.test_run)
        self.run_id = self.test_run.id

        # Results
        r1 = TestResult(
            run_id=self.run_id,
            test_name="Health Check",
            http_method="GET",
            url="/health",
            status="PASS",
            response_code=200,
            response_time_ms=25.0
        )
        r2 = TestResult(
            run_id=self.run_id,
            test_name="Charge Card - Invalid CVV",
            http_method="POST",
            url="/charge",
            status="FAIL",
            response_code=500,
            response_time_ms=110.0,
            failure_type="HTTP_500",
            failure_evidence_json=json.dumps({"message": "HTTP 500 Server Error"})
        )
        r3 = TestResult(
            run_id=self.run_id,
            test_name="Refund Transaction",
            http_method="POST",
            url="/refund",
            status="ERROR",
            response_code=None,
            response_time_ms=0.0,
            failure_type="NETWORK_TIMEOUT",
            failure_evidence_json=json.dumps({"message": "Connection timed out after 5.0s"})
        )
        db.add_all([r1, r2, r3])
        db.commit()
        db.close()


    def tearDown(self):
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=self.engine)

    def test_api_classify_single(self):
        """Verify POST /api/v1/classification/classify."""
        payload = {
            "test_name": "Get Balance",
            "http_method": "GET",
            "url": "/account/balance",
            "status_code": 200,
            "expected_status": 200,
            "latency_ms": 30.0,
            "assertions_passed": True
        }
        resp = self.client.post("/api/v1/classification/classify", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["outcome"], "PASS")
        self.assertEqual(data["severity"], "NONE")

    def test_api_classify_batch(self):
        """Verify POST /api/v1/classification/classify-batch computes summary and health index."""
        payload = {
            "items": [
                {
                    "test_name": "T1",
                    "http_method": "GET",
                    "url": "/t1",
                    "status_code": 200,
                    "expected_status": 200,
                    "latency_ms": 20.0,
                    "assertions_passed": True
                },
                {
                    "test_name": "T2",
                    "http_method": "POST",
                    "url": "/t2",
                    "status_code": 500,
                    "expected_status": 400,
                    "is_negative_test": True,
                    "assertions_passed": False
                }
            ]
        }
        resp = self.client.post("/api/v1/classification/classify-batch", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        summary = data["summary"]
        self.assertEqual(summary["total_executions"], 2)
        self.assertEqual(summary["pass_count"], 1)
        self.assertEqual(summary["error_count"], 1)
        self.assertEqual(summary["critical_severity_count"], 1)
        self.assertEqual(len(data["prioritized_failures"]), 1)

    def test_api_get_test_run_classification(self):
        """Verify GET /api/v1/runs/{id}/classification."""
        resp = self.client.get(f"/api/v1/runs/{self.run_id}/classification")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["run_id"], self.run_id)
        self.assertEqual(data["summary"]["total_executions"], 3)
        self.assertGreaterEqual(len(data["prioritized_failures"]), 1)

    def test_api_get_project_latest_classification(self):
        """Verify GET /api/v1/projects/{id}/classification/latest."""
        resp = self.client.get(f"/api/v1/projects/{self.project_id}/classification/latest")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["project_id"], self.project_id)
        self.assertEqual(data["run_id"], self.run_id)


if __name__ == "__main__":
    unittest.main()
