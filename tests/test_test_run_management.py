"""Unit and Integration Tests for Test Run Management & Orchestration (Stage 12)."""
import asyncio
import unittest
from unittest.mock import AsyncMock, patch
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
from app.models.schemas.execution import ExecutionResultResponse
from app.models.schemas.test_case import (
    AssertionRuleResult,
    TestCaseAssertionReport,
    TestCaseExecutionEvaluationResponse,
)
from app.models.schemas.test_run import RunStatus, TestResultStatus
from app.utils.run_state_machine import (
    InvalidStateTransitionError,
    calculate_run_metrics,
    validate_state_transition,
)


class TestRunStateMachine(unittest.TestCase):
    """Unit tests for run state transitions and metric computations."""

    def test_valid_transitions(self):
        # QUEUED -> RUNNING
        validate_state_transition("QUEUED", "RUNNING")
        # QUEUED -> CANCELLED
        validate_state_transition("QUEUED", "CANCELLED")
        # RUNNING -> COMPLETED
        validate_state_transition("RUNNING", "COMPLETED")
        # RUNNING -> CANCELLED
        validate_state_transition("RUNNING", "CANCELLED")
        # RUNNING -> FAILED
        validate_state_transition("RUNNING", "FAILED")

    def test_invalid_transitions(self):
        # QUEUED -> COMPLETED directly is illegal
        with self.assertRaises(InvalidStateTransitionError):
            validate_state_transition("QUEUED", "COMPLETED")

        # Terminal state COMPLETED cannot transition to RUNNING
        with self.assertRaises(InvalidStateTransitionError):
            validate_state_transition("COMPLETED", "RUNNING")

        # Terminal state CANCELLED cannot transition to COMPLETED
        with self.assertRaises(InvalidStateTransitionError):
            validate_state_transition("CANCELLED", "COMPLETED")

    def test_calculate_run_metrics(self):
        class MockResult:
            def __init__(self, status):
                self.status = status

        results = [
            MockResult("PASS"),
            MockResult("PASS"),
            MockResult("FAIL"),
            MockResult("ERROR")
        ]
        total, passed, failed, warnings, errors, pass_rate, dur = calculate_run_metrics(
            results, None, None
        )
        self.assertEqual(total, 4)
        self.assertEqual(passed, 2)
        self.assertEqual(failed, 1)
        self.assertEqual(errors, 1)
        self.assertEqual(pass_rate, 50.0)


class TestRunManagementAPIIntegration(unittest.TestCase):
    """Integration tests for Test Run REST APIs and Orchestrator."""

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
        self.project = Project(name="Orchestrator Test Project", base_url="https://api.example.com")
        self.db.add(self.project)
        self.db.commit()

        self.endpoint = Endpoint(project_id=self.project.id, name="Test Endpoint", method="GET", path="/items")
        self.db.add(self.endpoint)
        self.db.commit()

        self.tc1 = TestCase(
            endpoint_id=self.endpoint.id,
            name="Smoke Test Case 1",
            tags_json='["smoke", "critical"]',
            assertions_json='{"expected_status": 200}'
        )
        self.tc2 = TestCase(
            endpoint_id=self.endpoint.id,
            name="Regression Test Case 2",
            tags_json='["regression"]',
            assertions_json='{"expected_status": 200}'
        )
        self.db.add_all([self.tc1, self.tc2])
        self.db.commit()

    def tearDown(self):
        self.db.query(TestResult).delete()
        self.db.query(TestRun).delete()
        self.db.query(TestCase).delete()
        self.db.query(Endpoint).delete()
        self.db.query(Project).delete()
        self.db.commit()
        self.db.close()

    @patch("app.services.test_case_service.TestCaseService.evaluate_test_case")
    def test_create_and_execute_test_run(self, mock_evaluate):
        # Mock evaluation return
        mock_evaluate.return_value = TestCaseExecutionEvaluationResponse(
            test_case_id=self.tc1.id,
            test_case_name=self.tc1.name,
            endpoint_id=self.endpoint.id,
            http_method="GET",
            target_url="https://api.example.com/items",
            status_code=200,
            latency_ms=45.2,
            response_headers={"content-type": "application/json"},
            response_body={"status": "ok"},
            assertion_report=TestCaseAssertionReport(
                all_passed=True,
                total_rules=1,
                passed_rules=1,
                failed_rules=0,
                results=[
                    AssertionRuleResult(
                        rule_type="STATUS_CODE",
                        target="status_code",
                        operator="equals",
                        expected=200,
                        actual=200,
                        passed=True,
                        message="Status 200 matches"
                    )
                ]
            )
        )

        payload = {
            "name": "Sprint 12 Regression Suite",
            "environment": "staging",
            "concurrency": 2,
            "execute_immediately": True
        }

        response = self.client.post(f"/api/v1/projects/{self.project.id}/runs", json=payload)
        self.assertEqual(response.status_code, 201)
        data = response.json()["data"]
        self.assertEqual(data["name"], "Sprint 12 Regression Suite")
        self.assertEqual(data["status"], "COMPLETED")
        self.assertEqual(data["total_tests"], 2)
        self.assertEqual(data["passed_tests"], 2)
        self.assertEqual(data["failed_tests"], 0)
        self.assertEqual(data["pass_rate_pct"], 100.0)
        self.assertEqual(len(data["results"]), 2)

    def test_create_queued_run_and_manual_execute(self):
        payload = {
            "name": "Queued Run",
            "execute_immediately": False
        }
        create_resp = self.client.post(f"/api/v1/projects/{self.project.id}/runs", json=payload)
        self.assertEqual(create_resp.status_code, 201)
        run_id = create_resp.json()["data"]["id"]
        self.assertEqual(create_resp.json()["data"]["status"], "QUEUED")

        # Get details while queued
        get_resp = self.client.get(f"/api/v1/runs/{run_id}")
        self.assertEqual(get_resp.status_code, 200)
        self.assertEqual(get_resp.json()["data"]["status"], "QUEUED")

    def test_cancel_queued_run(self):
        payload = {"name": "Run to Cancel", "execute_immediately": False}
        create_resp = self.client.post(f"/api/v1/projects/{self.project.id}/runs", json=payload)
        run_id = create_resp.json()["data"]["id"]

        cancel_resp = self.client.post(f"/api/v1/runs/{run_id}/cancel", json={"reason": "User abort"})
        self.assertEqual(cancel_resp.status_code, 200)
        self.assertEqual(cancel_resp.json()["data"]["status"], "CANCELLED")
        self.assertEqual(cancel_resp.json()["data"]["cancellation_reason"], "User abort")

    def test_filter_runs_by_tag(self):
        payload = {
            "name": "Smoke Only Run",
            "tag_filter": "smoke",
            "execute_immediately": False
        }
        create_resp = self.client.post(f"/api/v1/projects/{self.project.id}/runs", json=payload)
        self.assertEqual(create_resp.status_code, 201)
        self.assertEqual(create_resp.json()["data"]["total_tests"], 1)

    def test_delete_test_run(self):
        payload = {"name": "Temporary Run", "execute_immediately": False}
        create_resp = self.client.post(f"/api/v1/projects/{self.project.id}/runs", json=payload)
        run_id = create_resp.json()["data"]["id"]

        del_resp = self.client.delete(f"/api/v1/runs/{run_id}")
        self.assertEqual(del_resp.status_code, 200)
        self.assertTrue(del_resp.json()["data"]["deleted"])

        get_resp = self.client.get(f"/api/v1/runs/{run_id}")
        self.assertEqual(get_resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
