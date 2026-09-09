"""Unit and Integration Tests for Stage 22: Reporting & Export Engine."""
import unittest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core.database import Base, get_db
from app.models.entities.project import Project
from app.models.entities.endpoint import Endpoint
from app.models.entities.test_case import TestCase
from app.models.entities.test_run import TestRun
from app.models.entities.test_result import TestResult
from app.models.schemas.report import ComprehensiveTestReport, ReportVerdict
from app.services.report_service import ReportService


class TestReportingEngine(unittest.TestCase):
    """Test suite validating Report generation, HTML/Markdown exports, and REST APIs."""

    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = TestingSessionLocal()

        def override_get_db():
            try:
                yield self.db
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

        # Seed Project
        self.project = Project(
            name="Alpha Commerce API",
            base_url="https://api.alphacommerce.com",
            environment="staging"
        )
        self.db.add(self.project)
        self.db.commit()
        self.db.refresh(self.project)

        # Seed Endpoint
        self.endpoint = Endpoint(
            project_id=self.project.id,
            name="List Products",
            method="GET",
            path="/products",
            expected_status=200,
            is_active=True
        )
        self.db.add(self.endpoint)
        self.db.commit()
        self.db.refresh(self.endpoint)

        # Seed TestCase
        self.test_case = TestCase(
            endpoint_id=self.endpoint.id,
            name="Verify Product Catalog Nominal",
            assertions_json='[{"type": "status_code", "expected": 200, "operator": "equals"}]',
            is_active=True
        )
        self.db.add(self.test_case)
        self.db.commit()
        self.db.refresh(self.test_case)

        # Seed TestRun
        self.run = TestRun(
            project_id=self.project.id,
            name="Sprint 22 Release Suite",
            environment="staging",
            status="COMPLETED",
            total_tests=3,
            passed_tests=2,
            failed_tests=1,
            duration_ms=640.5,
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc)
        )
        self.db.add(self.run)
        self.db.commit()
        self.db.refresh(self.run)

        # Seed TestResults
        r1 = TestResult(
            run_id=self.run.id,
            test_case_id=self.test_case.id,
            endpoint_id=self.endpoint.id,
            status="PASS",
            test_name="Verify Product Catalog Nominal",
            http_method="GET",
            url="https://api.alphacommerce.com/products",
            response_code=200,
            response_time_ms=45.2
        )
        r2 = TestResult(
            run_id=self.run.id,
            test_case_id=self.test_case.id,
            endpoint_id=self.endpoint.id,
            status="PASS",
            test_name="Verify Auth Headers",
            http_method="GET",
            url="https://api.alphacommerce.com/products",
            response_code=200,
            response_time_ms=52.8
        )
        r3 = TestResult(
            run_id=self.run.id,
            test_case_id=self.test_case.id,
            endpoint_id=self.endpoint.id,
            status="FAIL",
            test_name="Slow Checkout Probe",
            http_method="POST",
            url="https://api.alphacommerce.com/checkout",
            response_code=500,
            response_time_ms=750.0,
            failure_type="SERVER_CRASH",
            failure_evidence_json='{"summary": "500 Internal Server Error encountered"}'
        )
        self.db.add_all([r1, r2, r3])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        app.dependency_overrides.clear()

    def test_generate_report_bundle(self):
        """Test synthesizing complete 6-section ComprehensiveTestReport."""
        report = ReportService.generate_report(self.run.id, self.db)
        self.assertIsInstance(report, ComprehensiveTestReport)
        
        # 1. Summary
        self.assertEqual(report.summary.run_id, self.run.id)
        self.assertEqual(report.summary.project_name, "Alpha Commerce API")
        self.assertEqual(report.summary.total_tests, 3)
        self.assertEqual(report.summary.passed_tests, 2)
        self.assertEqual(report.summary.failed_tests, 1)
        self.assertAlmostEqual(report.summary.pass_rate_pct, 66.7, places=1)
        self.assertEqual(report.summary.verdict, ReportVerdict.DEGRADED)

        # 2. Functional
        self.assertEqual(report.functional.total_tests, 3)
        self.assertEqual(len(report.functional.failures), 1)
        self.assertEqual(report.functional.failures[0].test_name, "Slow Checkout Probe")
        self.assertEqual(report.functional.failures[0].response_code, 500)

        # 3. Performance
        self.assertGreater(report.performance.avg_latency_ms, 0)
        self.assertEqual(report.performance.max_latency_ms, 750.0)
        self.assertEqual(report.performance.sla_breach_count, 1)
        self.assertEqual(report.performance.slow_endpoints[0].sla_breach_ms, 250.0)

        # 4. Actionable Recommendations
        self.assertGreaterEqual(report.recommendations.total_recommendations, 1)
        self.assertEqual(report.recommendations.recommendations[0].endpoint_method, "POST")

    def test_markdown_report_generation(self):
        """Test generating GitHub-flavored markdown report."""
        report = ReportService.generate_report(self.run.id, self.db)
        md = ReportService.generate_markdown_report(report)
        
        self.assertIn("# 🛡️ API Sentinel — Test Execution Report", md)
        self.assertIn("Alpha Commerce API", md)
        self.assertIn("Slow Checkout Probe", md)
        self.assertIn("SLA Breaching Endpoints", md)
        self.assertIn("Actionable AI & Rule-Based Remediations", md)

    def test_html_report_generation(self):
        """Test generating standalone responsive HTML report."""
        report = ReportService.generate_report(self.run.id, self.db)
        html = ReportService.generate_html_report(report)
        
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("API Sentinel Diagnostic Report", html)
        self.assertIn("Alpha Commerce API", html)
        self.assertIn("750.0ms", html)
        self.assertIn("Slow Checkout Probe", html)

    def test_get_report_json_api(self):
        """Test GET /api/v1/reports/runs/{run_id} REST endpoint."""
        res = self.client.get(f"/api/v1/reports/runs/{self.run.id}")
        self.assertEqual(res.status_code, 200)
        json_data = res.json()
        self.assertTrue(json_data["success"])
        self.assertEqual(json_data["data"]["summary"]["run_id"], self.run.id)
        self.assertEqual(json_data["data"]["functional"]["total_tests"], 3)

    def test_get_report_html_and_markdown_apis(self):
        """Test GET /html and /markdown export endpoints."""
        html_res = self.client.get(f"/api/v1/reports/runs/{self.run.id}/html")
        self.assertEqual(html_res.status_code, 200)
        self.assertIn("text/html", html_res.headers["content-type"])
        self.assertIn("API Sentinel Diagnostic Report", html_res.text)

        md_res = self.client.get(f"/api/v1/reports/runs/{self.run.id}/markdown")
        self.assertEqual(md_res.status_code, 200)
        self.assertIn("text/markdown", md_res.headers["content-type"])
        self.assertIn("# 🛡️ API Sentinel — Test Execution Report", md_res.text)

    def test_download_report_api(self):
        """Test GET /api/v1/reports/runs/{run_id}/download attachments."""
        # Download HTML
        res_html = self.client.get(f"/api/v1/reports/runs/{self.run.id}/download?format=html")
        self.assertEqual(res_html.status_code, 200)
        self.assertIn('attachment; filename="api_sentinel_report_run_', res_html.headers["content-disposition"])

        # Download Markdown
        res_md = self.client.get(f"/api/v1/reports/runs/{self.run.id}/download?format=md")
        self.assertEqual(res_md.status_code, 200)
        self.assertIn(".md", res_md.headers["content-disposition"])

        # Download JSON
        res_json = self.client.get(f"/api/v1/reports/runs/{self.run.id}/download?format=json")
        self.assertEqual(res_json.status_code, 200)
        self.assertIn(".json", res_json.headers["content-disposition"])

    def test_report_not_found(self):
        """Test 404 behavior on non-existent run ID."""
        res = self.client.get("/api/v1/reports/runs/99999")
        self.assertEqual(res.status_code, 404)


if __name__ == "__main__":
    unittest.main()
