"""Unit and integration test suite for Stage 21: Run Comparison & Diff Tool."""
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
from app.models.schemas.run_comparison import DeltaStatus, DiffCategory
from app.services.run_comparison_service import RunComparisonService


class TestRunComparisonEngine(unittest.TestCase):
    """Test suite verifying Run Comparison calculations, categorized diffs, and REST APIs."""

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

        # Seed test data: 1 Project, 2 Test Runs (Base Run #14 vs Target Run #15)
        db = self.SessionLocal()
        p = Project(name="E-Commerce API", base_url="http://127.0.0.1:8000", environment="production")
        db.add(p)
        db.commit()
        db.refresh(p)
        self.project_id = p.id

        # Endpoints
        ep1 = Endpoint(project_id=p.id, name="List Items", method="GET", path="/items")
        ep2 = Endpoint(project_id=p.id, name="Create Item", method="POST", path="/items")
        ep3 = Endpoint(project_id=p.id, name="Get Item", method="GET", path="/items/{id}")
        ep4 = Endpoint(project_id=p.id, name="Delete Item", method="DELETE", path="/items/{id}")
        db.add_all([ep1, ep2, ep3, ep4])
        db.commit()
        db.refresh(ep1)
        db.refresh(ep2)
        db.refresh(ep3)
        db.refresh(ep4)

        # Test Cases
        tc1 = TestCase(endpoint_id=ep1.id, name="Get Items Happy Path", severity="high")
        tc2 = TestCase(endpoint_id=ep2.id, name="Create Item Valid", severity="high")
        tc3 = TestCase(endpoint_id=ep3.id, name="Get Item Exists", severity="medium")
        tc4 = TestCase(endpoint_id=ep4.id, name="Delete Item Normal", severity="medium")
        db.add_all([tc1, tc2, tc3, tc4])
        db.commit()
        db.refresh(tc1)
        db.refresh(tc2)
        db.refresh(tc3)
        db.refresh(tc4)

        # Run 14 (Base Run - Previous)
        run14 = TestRun(
            project_id=p.id,
            name="Run #14 - Release Candidate 1",
            status="COMPLETED",
            environment="production",
            total_tests=4,
            passed_tests=3,
            failed_tests=1,
            duration_ms=840.0
        )
        db.add(run14)
        db.commit()
        db.refresh(run14)
        self.run14_id = run14.id

        # Results for Run 14
        r14_1 = TestResult(run_id=run14.id, test_case_id=tc1.id, endpoint_id=ep1.id, status="PASS", test_name=tc1.name, http_method="GET", url="/items", response_code=200, response_time_ms=50.0)
        r14_2 = TestResult(run_id=run14.id, test_case_id=tc2.id, endpoint_id=ep2.id, status="PASS", test_name=tc2.name, http_method="POST", url="/items", response_code=201, response_time_ms=100.0)
        r14_3 = TestResult(run_id=run14.id, test_case_id=tc3.id, endpoint_id=ep3.id, status="FAIL", test_name=tc3.name, http_method="GET", url="/items/1", response_code=500, response_time_ms=120.0)
        r14_4 = TestResult(run_id=run14.id, test_case_id=tc4.id, endpoint_id=ep4.id, status="PASS", test_name=tc4.name, http_method="DELETE", url="/items/1", response_code=204, response_time_ms=80.0)
        db.add_all([r14_1, r14_2, r14_3, r14_4])
        db.commit()

        # Run 15 (Target Run - Current)
        # TC1: PASS -> FAIL (Regression)
        # TC2: Latency spike: 100ms -> 350ms (+250ms, +250%)
        # TC3: FAIL (500) -> PASS (200) (Fixed Bug)
        # TC4: Status Code Drift: 204 -> 200 (Behavior Changed)
        run15 = TestRun(
            project_id=p.id,
            name="Run #15 - Release Candidate 2",
            status="COMPLETED",
            environment="production",
            total_tests=4,
            passed_tests=3,
            failed_tests=1,
            duration_ms=1160.0
        )
        db.add(run15)
        db.commit()
        db.refresh(run15)
        self.run15_id = run15.id

        r15_1 = TestResult(run_id=run15.id, test_case_id=tc1.id, endpoint_id=ep1.id, status="FAIL", test_name=tc1.name, http_method="GET", url="/items", response_code=500, response_time_ms=60.0)
        r15_2 = TestResult(run_id=run15.id, test_case_id=tc2.id, endpoint_id=ep2.id, status="PASS", test_name=tc2.name, http_method="POST", url="/items", response_code=201, response_time_ms=350.0)
        r15_3 = TestResult(run_id=run15.id, test_case_id=tc3.id, endpoint_id=ep3.id, status="PASS", test_name=tc3.name, http_method="GET", url="/items/1", response_code=200, response_time_ms=90.0)
        r15_4 = TestResult(run_id=run15.id, test_case_id=tc4.id, endpoint_id=ep4.id, status="PASS", test_name=tc4.name, http_method="DELETE", url="/items/1", response_code=200, response_time_ms=85.0)
        db.add_all([r15_1, r15_2, r15_3, r15_4])
        db.commit()
        db.close()

    def tearDown(self):
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=self.engine)

    def test_01_metrics_table_computation(self):
        """Verify side-by-side metric comparison table calculation."""
        db = self.SessionLocal()
        report = RunComparisonService.compare_runs(
            db=db,
            base_run_id=self.run14_id,
            target_run_id=self.run15_id
        )
        db.close()

        # Check metrics
        m = report.metrics
        self.assertEqual(m.total_tests.previous, 4)
        self.assertEqual(m.total_tests.current, 4)
        self.assertEqual(m.total_tests.delta, 0)
        self.assertEqual(m.total_tests.status, DeltaStatus.UNCHANGED)

        self.assertEqual(m.passed_tests.previous, 3)
        self.assertEqual(m.passed_tests.current, 3)

        self.assertEqual(m.avg_latency.previous, 210.0)
        self.assertEqual(m.avg_latency.current, 290.0)
        self.assertEqual(m.avg_latency.delta, 80.0)
        self.assertEqual(m.avg_latency.status, DeltaStatus.DEGRADED)

    def test_02_categorized_transitions_detection(self):
        """Verify new failures, fixed failures, behavior changes, and latency degradation."""
        db = self.SessionLocal()
        report = RunComparisonService.compare_runs(
            db=db,
            base_run_id=self.run14_id,
            target_run_id=self.run15_id
        )
        db.close()

        self.assertEqual(report.new_failures_count, 1)
        self.assertEqual(report.fixed_failures_count, 1)
        self.assertEqual(report.behavior_changed_count, 1)
        self.assertEqual(report.latency_degraded_count, 1)

        cat_map = {d.test_name: d for d in report.diffs}
        self.assertEqual(cat_map["Get Items Happy Path"].category, DiffCategory.NEW_FAILURE)
        self.assertEqual(cat_map["Get Item Exists"].category, DiffCategory.FIXED_FAILURE)
        self.assertEqual(cat_map["Delete Item Normal"].category, DiffCategory.BEHAVIOR_CHANGED)
        self.assertEqual(cat_map["Create Item Valid"].category, DiffCategory.LATENCY_DEGRADED)

    def test_03_natural_language_insights_generation(self):
        """Verify synthesized natural language bullet points."""
        db = self.SessionLocal()
        report = RunComparisonService.compare_runs(
            db=db,
            base_run_id=self.run14_id,
            target_run_id=self.run15_id
        )
        db.close()

        insights_text = " ".join(report.insights)
        self.assertIn("1 new failure(s) detected", insights_text)
        self.assertIn("Average latency increased by 80.0ms", insights_text)
        self.assertIn("1 existing test(s) changed behavior", insights_text)

    def test_04_api_get_runs_compare(self):
        """Verify GET /api/v1/runs/compare returns 200 with full comparison report."""
        res = self.client.get(f"/api/v1/runs/compare?base_run_id={self.run14_id}&target_run_id={self.run15_id}")
        self.assertEqual(res.status_code, 200)
        json_data = res.json()
        self.assertTrue(json_data["success"])
        data = json_data["data"]

        self.assertEqual(data["base_run"]["id"], self.run14_id)
        self.assertEqual(data["target_run"]["id"], self.run15_id)
        self.assertEqual(data["new_failures_count"], 1)
        self.assertEqual(data["fixed_failures_count"], 1)
        self.assertEqual(len(data["diffs"]), 4)

    def test_05_api_post_runs_compare(self):
        """Verify POST /api/v1/runs/compare returns 200."""
        res = self.client.post("/api/v1/runs/compare", json={
            "base_run_id": self.run14_id,
            "target_run_id": self.run15_id,
            "latency_threshold_pct": 20.0,
            "min_latency_delta_ms": 40.0
        })
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["success"])

    def test_06_nonexistent_run_404(self):
        """Verify comparing invalid run ID returns HTTP 404."""
        res = self.client.get(f"/api/v1/runs/compare?base_run_id=999&target_run_id={self.run15_id}")
        self.assertEqual(res.status_code, 404)


if __name__ == "__main__":
    unittest.main()
