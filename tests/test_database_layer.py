"""Comprehensive unit and integration tests for Stage 23: Persistence & Database Layer."""
import os
import unittest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.entities import Project, Endpoint, TestCase, TestRun, TestResult, AIRecommendation
from app.models.schemas.database import DatabaseHealthResponse, DatabaseBackupResponse, DatabaseMaintenanceResult
from app.repositories import (
    BaseRepository,
    ProjectRepository,
    EndpointRepository,
    TestCaseRepository,
    TestRunRepository,
    TestResultRepository,
    AIRecommendationRepository,
)
from app.services.database_service import DatabaseService


class TestDatabaseLayer(unittest.TestCase):
    """Test suite covering DAL repositories, DatabaseService, and maintenance REST APIs."""

    def setUp(self):
        # Create dedicated in-memory SQLite database for test isolation
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            echo=False,
        )
        self.TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        Base.metadata.create_all(bind=self.engine)

        self.db = self.TestingSessionLocal()


        def override_get_db():
            try:
                yield self.db
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        app.dependency_overrides.clear()

    def test_generic_base_repository_crud(self):
        """Test BaseRepository standard CRUD operations and existence checking."""
        repo = BaseRepository(Project, self.db)
        
        # Create
        proj = repo.create(name="Repo Test Project", base_url="http://127.0.0.1:8000", environment="development")
        self.assertIsNotNone(proj.id)
        self.assertEqual(proj.name, "Repo Test Project")
        
        # Count & Exists
        self.assertEqual(repo.count(), 1)
        self.assertTrue(repo.exists(proj.id))
        self.assertFalse(repo.exists(99999))

        # Get By ID & All
        fetched = repo.get_by_id(proj.id)
        self.assertEqual(fetched.name, "Repo Test Project")
        all_projs = repo.get_all(skip=0, limit=10)
        self.assertEqual(len(all_projs), 1)

        # Update
        updated = repo.update(proj.id, name="Renamed Project", environment="staging")
        self.assertEqual(updated.name, "Renamed Project")
        self.assertEqual(updated.environment, "staging")

        # Delete
        self.assertTrue(repo.delete(proj.id))
        self.assertEqual(repo.count(), 0)
        self.assertFalse(repo.exists(proj.id))

    def test_specialized_repositories(self):
        """Test specialized queries across Project, Endpoint, TestCase, TestRun, TestResult, and AIRecommendation repositories."""
        p_repo = ProjectRepository(self.db)
        e_repo = EndpointRepository(self.db)
        tc_repo = TestCaseRepository(self.db)
        tr_repo = TestRunRepository(self.db)
        res_repo = TestResultRepository(self.db)
        rec_repo = AIRecommendationRepository(self.db)

        # Project
        p = p_repo.create(name="Commerce Hub", base_url="https://api.commerce.com", environment="production")
        self.assertEqual(p_repo.get_by_name("Commerce Hub").id, p.id)
        self.assertEqual(len(p_repo.get_by_environment("production")), 1)

        # Endpoint
        ep = e_repo.create(project_id=p.id, method="POST", path="/orders", name="Create Order", is_active=True)
        self.assertEqual(len(e_repo.get_by_project(p.id, active_only=True)), 1)
        self.assertEqual(e_repo.count_by_project(p.id), 1)
        self.assertIsNotNone(e_repo.get_by_path_and_method(p.id, "POST", "/orders"))

        # TestCase
        tc = tc_repo.create(
            endpoint_id=ep.id,
            name="Nominal Order",
            tags_json='["smoke"]',
            assertions_json='{"expected_status": 201}',
            severity="CRITICAL",
            is_active=True
        )
        self.assertEqual(len(tc_repo.get_by_endpoint(ep.id)), 1)

        self.assertEqual(len(tc_repo.get_by_project(p.id)), 1)
        self.assertEqual(len(tc_repo.get_by_severity("CRITICAL")), 1)

        # TestRun
        run = tr_repo.create(project_id=p.id, name="Nightly Suite", status="COMPLETED", total_tests=1, passed_tests=1, failed_tests=0)
        self.assertEqual(len(tr_repo.get_recent_by_project(p.id)), 1)
        self.assertEqual(tr_repo.get_latest_completed(p.id).id, run.id)

        # TestResult
        res = res_repo.create(run_id=run.id, test_case_id=tc.id, endpoint_id=ep.id, status="PASS", test_name="Nominal Order Test", http_method="POST", url="/orders", response_code=201, response_time_ms=45.0)
        self.assertEqual(len(res_repo.get_by_run(run.id)), 1)

        self.assertEqual(len(res_repo.get_history_for_endpoint(ep.id)), 1)

        # AIRecommendation
        rec = rec_repo.create(test_result_id=res.id, evidence_id="EV-TEST12345", root_cause_category="SERVER_EXCEPTION", severity="HIGH", likely_cause="Unhandled NPE", suggested_fix="Add null guard")
        self.assertEqual(len(rec_repo.get_by_test_result(res.id)), 1)
        self.assertEqual(rec_repo.get_by_evidence_id("EV-TEST12345").likely_cause, "Unhandled NPE")
        self.assertEqual(len(rec_repo.get_by_root_cause_category("SERVER_EXCEPTION")), 1)

    def test_database_service_health(self):
        """Test DatabaseService.get_health diagnostics."""
        health = DatabaseService.get_health(self.db)
        self.assertIsInstance(health, DatabaseHealthResponse)
        self.assertEqual(health.status, "HEALTHY")
        self.assertEqual(health.dialect, "sqlite")
        self.assertGreaterEqual(health.ping_latency_ms, 0)
        self.assertIsInstance(health.tables.total_records, int)

    def test_database_service_seeding_and_purge(self):
        """Test DatabaseService seed_sample_data and purge_old_runs."""
        seed_res = DatabaseService.seed_sample_data(self.db)
        self.assertTrue(seed_res.success)
        self.assertGreater(seed_res.endpoints_created, 0)
        self.assertGreater(seed_res.test_cases_created, 0)

        # Check seeded data in db
        p_count = self.db.query(Project).count()
        self.assertGreaterEqual(p_count, 1)

        # Test purge with age threshold (mocking an old run)
        old_time = datetime.now(timezone.utc) - timedelta(days=60)
        old_run = TestRun(project_id=seed_res.project_id, name="Ancient Run", status="COMPLETED", created_at=old_time)
        self.db.add(old_run)
        self.db.commit()

        purge_res = DatabaseService.purge_old_runs(self.db, days_threshold=30)
        self.assertEqual(purge_res.days_threshold, 30)
        self.assertGreaterEqual(purge_res.runs_purged, 1)

    def test_database_health_api(self):
        """Test GET /api/v1/database/health REST endpoint."""
        res = self.client.get("/api/v1/database/health")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "HEALTHY")
        self.assertIn("tables", data)

    def test_database_vacuum_api(self):
        """Test POST /api/v1/database/maintenance/vacuum REST endpoint."""
        res = self.client.post("/api/v1/database/maintenance/vacuum")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "SUCCESS")
        self.assertIn("duration_ms", data)

    def test_database_purge_api(self):
        """Test POST /api/v1/database/maintenance/purge-runs REST endpoint."""
        res = self.client.post("/api/v1/database/maintenance/purge-runs", json={"days_threshold": 45})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["days_threshold"], 45)
        self.assertIn("runs_purged", data)

    def test_database_seed_api(self):
        """Test POST /api/v1/database/seed-sample REST endpoint."""
        res = self.client.post("/api/v1/database/seed-sample")
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["project_name"], "Alpha Commerce Demo Store")


if __name__ == "__main__":
    unittest.main()
