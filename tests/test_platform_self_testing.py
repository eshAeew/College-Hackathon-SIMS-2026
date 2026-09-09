"""Unit and Integration tests for Stage 26: Platform Self-Testing Suite."""
import unittest
from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas.self_test import SubsystemCategory
from app.services.self_test_service import SelfTestService


class TestPlatformSelfTesting(unittest.TestCase):
    """Test suite covering programmatic self-test execution, subsystem filtering, and REST APIs."""

    def setUp(self):
        self.client = TestClient(app)

    def test_get_available_suites(self):
        """Test listing available architectural subsystem test suites."""
        suites = SelfTestService.get_available_suites()
        self.assertGreaterEqual(len(suites), 5)
        suite_ids = [s.id for s in suites]
        self.assertIn("core_foundation", suite_ids)
        self.assertIn("execution_engine", suite_ids)
        self.assertIn("resilience_data_audit", suite_ids)

    def test_run_subsystem_self_tests(self):
        """Test running a targeted subsystem self-test suite programmatically."""
        report = SelfTestService.run_self_tests(
            subsystem=SubsystemCategory.CORE_FOUNDATION,
            include_tracebacks=True,
        )
        self.assertEqual(report.subsystem, "core_foundation")
        self.assertEqual(report.verdict, "ALL_PASSED")
        self.assertGreater(report.total_tests, 0)
        self.assertEqual(report.failed, 0)
        self.assertEqual(report.errors, 0)
        self.assertEqual(report.pass_rate, 100.0)
        self.assertGreater(len(report.subsystems_breakdown), 0)

    def test_run_full_suite_self_tests(self):
        """Test running full platform self-testing suite programmatically."""
        report = SelfTestService.run_self_tests(
            subsystem=SubsystemCategory.FULL_SUITE,
            stop_on_first_error=False,
        )
        self.assertEqual(report.subsystem, "full_suite")
        self.assertEqual(report.verdict, "ALL_PASSED")
        self.assertGreaterEqual(report.total_tests, 250)
        self.assertEqual(report.failed, 0)
        self.assertEqual(report.errors, 0)
        self.assertEqual(report.pass_rate, 100.0)
        self.assertEqual(len(report.subsystems_breakdown), 5)

    def test_health_matrix_computation(self):
        """Test computing subsystem readiness matrix."""
        matrix = SelfTestService.get_health_matrix()
        self.assertEqual(matrix.overall_system_status, "HEALTHY")
        self.assertEqual(matrix.total_subsystems, 5)
        self.assertEqual(matrix.healthy_subsystems, 5)
        self.assertEqual(len(matrix.subsystems), 5)

    def test_rest_api_self_test_endpoints(self):
        """Test REST endpoints: GET /suites, POST /run, GET /latest, GET /matrix."""
        # 1. GET /suites
        res_suites = self.client.get("/api/v1/self-test/suites")
        self.assertEqual(res_suites.status_code, 200)
        suites_data = res_suites.json()
        self.assertGreaterEqual(len(suites_data), 5)

        # 2. POST /run (targeted subsystem)
        payload = {
            "subsystem": "core_foundation",
            "stop_on_first_error": False,
            "include_tracebacks": True,
        }
        res_run = self.client.post("/api/v1/self-test/run", json=payload)
        self.assertEqual(res_run.status_code, 200)
        run_data = res_run.json()
        self.assertEqual(run_data["verdict"], "ALL_PASSED")
        self.assertGreater(run_data["total_tests"], 0)

        # 3. GET /latest
        res_latest = self.client.get("/api/v1/self-test/latest")
        self.assertEqual(res_latest.status_code, 200)
        self.assertEqual(res_latest.json()["verdict"], "ALL_PASSED")

        # 4. GET /matrix
        res_matrix = self.client.get("/api/v1/self-test/matrix")
        self.assertEqual(res_matrix.status_code, 200)
        self.assertEqual(res_matrix.json()["overall_system_status"], "HEALTHY")


if __name__ == "__main__":
    unittest.main()
