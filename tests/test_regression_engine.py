"""Unit and Integration Tests for Regression Testing Engine & Delta Comparator (Stage 13)."""
import unittest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.entities.endpoint import Endpoint
from app.models.entities.project import Project
from app.models.entities.test_case import TestCase
from app.models.entities.test_run import TestRun
from app.models.entities.test_result import TestResult
from app.models.schemas.regression import (
    ComparisonExecutionItem,
    DirectRegressionComparisonRequest,
    RegressionSeverity,
    RegressionType,
    RegressionVerdict,
)
from app.utils.regression_comparator import (
    calculate_latency_delta,
    classify_regression,
    compare_execution_results,
)


class TestRegressionComparatorUnits(unittest.TestCase):
    """Unit tests for math deltas, regression classification, and summary logic."""

    def test_calculate_latency_delta(self):
        delta_ms, pct = calculate_latency_delta(100.0, 150.0)
        self.assertEqual(delta_ms, 50.0)
        self.assertEqual(pct, 50.0)

        delta_ms2, pct2 = calculate_latency_delta(200.0, 100.0)
        self.assertEqual(delta_ms2, -100.0)
        self.assertEqual(pct2, -50.0)

    def test_classify_functional_regression(self):
        base = ComparisonExecutionItem(test_name="Login API", status="PASS", status_code=200, response_time_ms=50.0)
        curr = ComparisonExecutionItem(test_name="Login API", status="FAIL", status_code=500, response_time_ms=55.0)

        reg_type, severity, badge, suggestion = classify_regression(base, curr)
        self.assertEqual(reg_type, RegressionType.FUNCTIONAL_REGRESSION)
        self.assertEqual(severity, RegressionSeverity.CRITICAL)
        self.assertEqual(badge, "CRITICAL CRASH")

    def test_classify_performance_regression(self):
        base = ComparisonExecutionItem(test_name="Search API", status="PASS", status_code=200, response_time_ms=100.0)
        curr = ComparisonExecutionItem(test_name="Search API", status="PASS", status_code=200, response_time_ms=250.0)  # +150%

        reg_type, severity, badge, suggestion = classify_regression(base, curr, latency_threshold_pct=50.0, min_latency_delta_ms=50.0)
        self.assertEqual(reg_type, RegressionType.PERFORMANCE_REGRESSION)
        self.assertEqual(severity, RegressionSeverity.HIGH)
        self.assertIn("SLOWDOWN", badge)

    def test_classify_resolved_improvement(self):
        base = ComparisonExecutionItem(test_name="Auth API", status="FAIL", status_code=401, response_time_ms=40.0)
        curr = ComparisonExecutionItem(test_name="Auth API", status="PASS", status_code=200, response_time_ms=35.0)

        reg_type, severity, badge, suggestion = classify_regression(base, curr)
        self.assertEqual(reg_type, RegressionType.RESOLVED_IMPROVEMENT)
        self.assertEqual(severity, RegressionSeverity.NONE)
        self.assertEqual(badge, "RESOLVED / FIXED")

    def test_compare_execution_results_summary(self):
        baseline = [
            ComparisonExecutionItem(test_case_id=1, test_name="TC1", status="PASS", status_code=200, response_time_ms=100.0),
            ComparisonExecutionItem(test_case_id=2, test_name="TC2", status="FAIL", status_code=500, response_time_ms=100.0),
            ComparisonExecutionItem(test_case_id=3, test_name="TC3", status="PASS", status_code=200, response_time_ms=100.0),
        ]
        current = [
            ComparisonExecutionItem(test_case_id=1, test_name="TC1", status="FAIL", status_code=500, response_time_ms=100.0), # Functional Break
            ComparisonExecutionItem(test_case_id=2, test_name="TC2", status="PASS", status_code=200, response_time_ms=100.0), # Fixed
            ComparisonExecutionItem(test_case_id=3, test_name="TC3", status="PASS", status_code=200, response_time_ms=300.0), # Perf Degradation (+200%)
        ]

        summary, regs, imps, stables = compare_execution_results(baseline, current)
        self.assertEqual(summary.total_compared_tests, 3)
        self.assertEqual(summary.total_regressions, 2)
        self.assertEqual(summary.functional_regressions, 1)
        self.assertEqual(summary.performance_regressions, 1)
        self.assertEqual(summary.resolved_improvements, 1)
        self.assertEqual(summary.verdict, RegressionVerdict.CRITICAL_REGRESSIONS_FOUND)


class TestRegressionAPIIntegration(unittest.TestCase):
    """Integration tests for Regression REST APIs."""

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool
        )
        cls.TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=cls.engine)
        Base.metadata.create_all(bind=cls.engine)

        def override_get_db():
            db = cls.TestingSessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(bind=cls.engine)
        app.dependency_overrides.clear()

    def setUp(self):
        self.db = self.TestingSessionLocal()
        self.project = Project(name="Regression Test Project", base_url="https://api.example.com")
        self.db.add(self.project)
        self.db.commit()

        # Run 1: Baseline Run (All Pass)
        self.run1 = TestRun(
            project_id=self.project.id,
            name="Baseline Run 1",
            status="COMPLETED",
            total_tests=2,
            passed_tests=2,
            failed_tests=0
        )
        self.db.add(self.run1)
        self.db.commit()

        self.res1_1 = TestResult(
            run_id=self.run1.id,
            test_case_id=1,
            test_name="Checkout API",
            http_method="POST",
            url="https://api.example.com/checkout",
            status="PASS",
            response_code=200,
            response_time_ms=100.0
        )
        self.res1_2 = TestResult(
            run_id=self.run1.id,
            test_case_id=2,
            test_name="Products API",
            http_method="GET",
            url="https://api.example.com/products",
            status="PASS",
            response_code=200,
            response_time_ms=80.0
        )
        self.db.add_all([self.res1_1, self.res1_2])
        self.db.commit()

        # Run 2: Current Run (Checkout API Broke, Products API Slowed Down)
        self.run2 = TestRun(
            project_id=self.project.id,
            name="Current Run 2",
            status="COMPLETED",
            total_tests=2,
            passed_tests=1,
            failed_tests=1
        )
        self.db.add(self.run2)
        self.db.commit()

        self.res2_1 = TestResult(
            run_id=self.run2.id,
            test_case_id=1,
            test_name="Checkout API",
            http_method="POST",
            url="https://api.example.com/checkout",
            status="FAIL",
            response_code=500,
            response_time_ms=110.0,
            failure_type="SERVER_CRASH"
        )
        self.res2_2 = TestResult(
            run_id=self.run2.id,
            test_case_id=2,
            test_name="Products API",
            http_method="GET",
            url="https://api.example.com/products",
            status="PASS",
            response_code=200,
            response_time_ms=250.0  # +212.5% slowdown
        )
        self.db.add_all([self.res2_1, self.res2_2])
        self.db.commit()

    def tearDown(self):
        self.db.query(TestResult).delete()
        self.db.query(TestRun).delete()
        self.db.query(Project).delete()
        self.db.commit()
        self.db.close()

    def test_direct_regression_comparison_endpoint(self):
        payload = {
            "baseline_run_name": "V1.0",
            "current_run_name": "V1.1",
            "latency_degradation_threshold_pct": 50.0,
            "baseline_results": [
                {"test_name": "Users", "status": "PASS", "status_code": 200, "response_time_ms": 100.0}
            ],
            "current_results": [
                {"test_name": "Users", "status": "FAIL", "status_code": 500, "response_time_ms": 105.0}
            ]
        }
        response = self.client.post("/api/v1/regression/compare", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["summary"]["total_regressions"], 1)
        self.assertEqual(data["summary"]["functional_regressions"], 1)
        self.assertEqual(data["summary"]["verdict"], "CRITICAL_REGRESSIONS_FOUND")

    def test_evaluate_run_regression_against_baseline(self):
        response = self.client.get(f"/api/v1/runs/{self.run2.id}/regression?baseline_run_id={self.run1.id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["baseline_run_id"], self.run1.id)
        self.assertEqual(data["current_run_id"], self.run2.id)
        self.assertEqual(data["summary"]["total_regressions"], 2)  # 1 functional + 1 performance
        self.assertEqual(data["summary"]["functional_regressions"], 1)
        self.assertEqual(data["summary"]["performance_regressions"], 1)

    def test_get_latest_project_regression_auto_baseline(self):
        response = self.client.get(f"/api/v1/projects/{self.project.id}/regressions/latest")
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["current_run_id"], self.run2.id)
        self.assertEqual(data["baseline_run_id"], self.run1.id)
        self.assertEqual(data["summary"]["verdict"], "CRITICAL_REGRESSIONS_FOUND")


if __name__ == "__main__":
    unittest.main()
