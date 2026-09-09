"""Unit and integration test suite for Stage 20: Dashboard & Web Interface."""
import unittest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.entities.project import Project
from app.models.entities.endpoint import Endpoint
from app.models.entities.test_case import TestCase
from app.models.entities.test_run import TestRun
from app.models.entities.test_result import TestResult
from app.models.entities.ai_recommendation import AIRecommendation


class TestDashboardUI(unittest.TestCase):
    """Test suite verifying Web Dashboard rendering and Aggregator APIs."""

    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
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

        # Seed sample data
        db = self.SessionLocal()
        p = Project(name="E-Commerce API", base_url="http://127.0.0.1:8000", environment="development")
        db.add(p)
        db.commit()
        db.refresh(p)

        ep1 = Endpoint(project_id=p.id, name="List Products", method="GET", path="/api/v1/products")
        ep2 = Endpoint(project_id=p.id, name="Create Product", method="POST", path="/api/v1/products")
        db.add_all([ep1, ep2])
        db.commit()
        db.refresh(ep1)
        db.refresh(ep2)

        tc1 = TestCase(endpoint_id=ep1.id, name="Smoke Get Products", severity="low")
        db.add(tc1)
        db.commit()
        db.refresh(tc1)

        run = TestRun(
            project_id=p.id,
            name="Sprint 20 Regression",
            status="COMPLETED",
            environment="development",
            total_tests=1,
            passed_tests=1,
            failed_tests=0,
            duration_ms=25.4
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        rec = AIRecommendation(
            evidence_id="EV-12345",
            root_cause_category="MISSING_INPUT_VALIDATION",
            likely_cause="Server crashed with 500 when sent empty body",
            severity="CRITICAL",
            suggested_fix="Add Pydantic validation model",
            code_snippet="class Item(BaseModel): pass",
            source="RULE_BASED_HEURISTIC"
        )
        db.add(rec)
        db.commit()
        db.close()

    def tearDown(self):
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=self.engine)

    def test_01_render_root_dashboard_html(self):
        """Verify GET / with browser accept header returns HTTP 200 with HTML and Nova Dark theme classes."""
        res = self.client.get("/", headers={"accept": "text/html,application/xhtml+xml"})
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/html", res.headers.get("content-type", ""))
        self.assertIn("API Sentinel", res.text)
        self.assertIn("bg-neutral-background", res.text)
        self.assertIn("brand-primary", res.text)

    def test_02_render_dashboard_route_html(self):
        """Verify GET /dashboard returns HTTP 200 with HTML."""
        res = self.client.get("/dashboard")
        self.assertEqual(res.status_code, 200)
        self.assertIn("API Sentinel", res.text)

    def test_03_dashboard_overview_api(self):
        """Verify GET /api/v1/dashboard/overview returns aggregated KPIs."""
        res = self.client.get("/api/v1/dashboard/overview")
        self.assertEqual(res.status_code, 200)
        json_data = res.json()
        self.assertTrue(json_data["success"])
        data = json_data["data"]

        # Check KPI counts
        self.assertEqual(data["kpi"]["total_projects"], 1)
        self.assertEqual(data["kpi"]["total_endpoints"], 2)
        self.assertEqual(data["kpi"]["total_active_endpoints"], 2)
        self.assertEqual(data["kpi"]["total_test_cases"], 1)
        self.assertGreaterEqual(data["kpi"]["total_assertions"], 0)
        self.assertEqual(data["kpi"]["total_test_runs"], 1)
        self.assertEqual(data["kpi"]["global_pass_rate_pct"], 100.0)
        self.assertEqual(data["kpi"]["db_engine"], "SQLite 3")
        self.assertIn("ai_engine_status", data["kpi"])

        # Check critical issues
        self.assertEqual(len(data["critical_issues"]), 1)
        self.assertEqual(data["critical_issues"][0]["root_cause_category"], "MISSING_INPUT_VALIDATION")

        # Check recent runs
        self.assertEqual(len(data["recent_runs"]), 1)
        self.assertEqual(data["recent_runs"][0]["name"], "Sprint 20 Regression")

    def test_04_project_detail_dashboard_view(self):
        """Verify GET /api/v1/dashboard/projects/{id} returns project drill-down view."""
        res = self.client.get("/api/v1/dashboard/projects/1")
        self.assertEqual(res.status_code, 200)
        data = res.json()["data"]
        self.assertEqual(data["name"], "E-Commerce API")
        self.assertEqual(len(data["endpoints"]), 2)
        self.assertEqual(data["total_endpoints"], 2)
        self.assertEqual(data["pass_rate_pct"], 100.0)

    def test_05_project_detail_not_found(self):
        """Verify GET /api/v1/dashboard/projects/999 returns HTTP 404."""
        res = self.client.get("/api/v1/dashboard/projects/999")
        self.assertEqual(res.status_code, 404)


if __name__ == "__main__":
    unittest.main()
