"""Unit and Integration tests for Stage 28: Final Demo Workflow & Pitch Playbook."""
import unittest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core.database import Base, get_db
from app.services.demo_workflow_service import DemoWorkflowService

SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


class TestDemoWorkflowAndPitch(unittest.TestCase):
    """Test suite covering demo bootstrapping, phase 1 & 2 executions, story runner, and pitch playbook."""

    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=test_engine)
        app.dependency_overrides[get_db] = override_get_db

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=test_engine)

    def setUp(self):
        self.client = TestClient(app, raise_server_exceptions=False)
        self.db = TestingSessionLocal()

    def tearDown(self):
        self.db.close()

    def test_demo_bootstrap(self):
        """Test Step 1-6: Workspace bootstrap and test case generation."""
        boot = DemoWorkflowService.bootstrap_demo(self.db)
        self.assertEqual(boot.project_name, "Alpha Commerce Demo Store")
        self.assertEqual(boot.endpoints_imported, 6)
        self.assertGreaterEqual(boot.test_cases_created, 9)
        self.assertEqual(boot.status, "READY")

    def test_phase_1_baseline_execution(self):
        """Test Step 7-11: Phase 1 baseline execution detects injected flaws."""
        phase_1 = DemoWorkflowService.execute_phase_1_baseline(self.db)
        self.assertGreater(phase_1["total_tests"], 0)
        self.assertGreater(phase_1["detected_failures_count"], 0)
        self.assertGreater(phase_1["ai_recommendations_count"], 0)

    def test_phase_2_verification_execution(self):
        """Test Step 12-14: Phase 2 verification execution after fixing flaws."""
        phase_1 = DemoWorkflowService.execute_phase_1_baseline(self.db)
        DemoWorkflowService.apply_demo_fixes()
        phase_2 = DemoWorkflowService.execute_phase_2_verification(self.db, baseline_run_id=phase_1["run_id"])
        self.assertEqual(phase_2["failed"], 0)
        self.assertEqual(phase_2["pass_rate"], 100.0)
        self.assertEqual(phase_2["verdict"], "CLEAN_PASS")

    def test_run_complete_14_step_story(self):
        """Test autonomous 1-click execution of the 14-step demonstration lifecycle."""
        story = DemoWorkflowService.run_complete_story(self.db)
        self.assertEqual(story.project_name, "Alpha Commerce Demo Store")
        self.assertGreaterEqual(story.total_steps, 5)
        self.assertEqual(story.regression_verdict, "ALL_BUGS_RESOLVED")
        self.assertEqual(story.phase_2_pass_rate, 100.0)

    def test_pitch_playbook_content(self):
        """Test 3-minute pitch playbook content and structure."""
        playbook = DemoWorkflowService.get_pitch_playbook()
        self.assertEqual(playbook.target_time_limit, "3 Minutes (180 Seconds)")
        self.assertEqual(len(playbook.pitch_timeline), 5)
        self.assertGreaterEqual(len(playbook.judge_qa_cheatsheet), 4)

    def test_rest_api_demo_workflow_endpoints(self):
        """Test REST endpoints: /bootstrap, /execute-phase-1, /apply-fixes, /execute-phase-2, /run-complete-story, /playbook."""
        # 1. POST /bootstrap
        res_boot = self.client.post("/api/v1/demo/bootstrap")
        self.assertEqual(res_boot.status_code, 200)
        self.assertEqual(res_boot.json()["status"], "READY")

        # 2. POST /execute-phase-1
        res_p1 = self.client.post("/api/v1/demo/execute-phase-1")
        self.assertEqual(res_p1.status_code, 200)
        p1_data = res_p1.json()
        self.assertIn("run_id", p1_data)

        # 3. POST /apply-fixes
        res_fixes = self.client.post("/api/v1/demo/apply-fixes")
        self.assertEqual(res_fixes.status_code, 200)
        self.assertEqual(res_fixes.json()["status"], "FIXES_APPLIED")

        # 4. POST /execute-phase-2
        res_p2 = self.client.post(f"/api/v1/demo/execute-phase-2?baseline_run_id={p1_data['run_id']}")
        self.assertEqual(res_p2.status_code, 200)
        self.assertEqual(res_p2.json()["pass_rate"], 100.0)

        # 5. POST /run-complete-story
        res_story = self.client.post("/api/v1/demo/run-complete-story")
        self.assertEqual(res_story.status_code, 200)
        self.assertEqual(res_story.json()["regression_verdict"], "ALL_BUGS_RESOLVED")

        # 6. GET /playbook
        res_playbook = self.client.get("/api/v1/demo/playbook")
        self.assertEqual(res_playbook.status_code, 200)
        self.assertIn("pitch_timeline", res_playbook.json())


if __name__ == "__main__":
    unittest.main()
