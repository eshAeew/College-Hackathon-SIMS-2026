"""Unit and integration test suite for Stage 19: AI Recommendation Layer."""
import json
import unittest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.entities.project import Project
from app.models.entities.endpoint import Endpoint
from app.models.entities.test_run import TestRun
from app.models.entities.test_result import TestResult
from app.models.schemas.ai_recommendation import RecommendationSeverity, RecommendationSource
from app.utils.evidence_packager import categorize_root_cause
from app.services.failure_analysis_service import FailureAnalysisService
from app.services.ai_recommendation_service import AIRecommendationService

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


class TestStage19AiRecommendation(unittest.TestCase):
    """Test suite for AI prompt synthesis, heuristic recommendations, and REST APIs."""

    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=test_engine)
        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)

        # Seed sample project, endpoint, test run, and test result
        db = TestingSessionLocal()
        project = Project(name="AI Test Project", base_url="https://api.example.com")
        db.add(project)
        db.commit()
        db.refresh(project)
        cls.project_id = project.id

        endpoint = Endpoint(project_id=project.id, name="Checkout", method="POST", path="/checkout")
        db.add(endpoint)
        db.commit()
        db.refresh(endpoint)
        cls.endpoint_id = endpoint.id

        run = TestRun(project_id=project.id, name="AI Diagnostic Run", status="COMPLETED", total_tests=1)
        db.add(run)
        db.commit()
        db.refresh(run)
        cls.run_id = run.id

        result = TestResult(
            run_id=run.id,
            endpoint_id=endpoint.id,
            test_name="checkout-null-cart",
            status="FAIL",
            http_method="POST",
            url="https://api.example.com/checkout",
            response_code=500,
            response_time_ms=350.0,
            response_body_snippet="KeyError: 'cart_id'",
            failure_evidence_json=json.dumps({"is_negative_test": True, "expected_status": 400})
        )
        db.add(result)
        db.commit()
        db.refresh(result)
        cls.result_id = result.id
        db.close()

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(bind=test_engine)
        app.dependency_overrides.clear()

    def test_01_ai_status_reports_offline_mode(self):
        """Audit /ai/status reports RULE_BASED_HEURISTIC in test environment."""
        resp = self.client.get("/api/v1/ai/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["active_engine"], "RULE_BASED_HEURISTIC")
        self.assertFalse(data["ai_enabled"])
        self.assertIn("offline mode", data["message"].lower())

    def test_02_prompt_synthesizer_structure_and_guardrails(self):
        """Audit that synthesized prompt adheres to strict rules and JSON schema."""
        evidence = self.client.post("/api/v1/failure-analysis/package", json={
            "test_name": "checkout-null-cart",
            "http_method": "POST",
            "url": "https://api.example.com/checkout",
            "status_code": 500,
            "expected_status": 400,
            "is_negative_test": True,
            "response_body": "KeyError: 'cart_id'"
        }).json()["data"]

        resp = self.client.post("/api/v1/ai/synthesize-prompt", json=evidence)
        self.assertEqual(resp.status_code, 200)
        prompt = resp.json()["data"]

        # Guardrails: Prime directive enforced
        self.assertIn("Never state whether the test passed or failed", prompt["system_prompt"])
        self.assertIn("JSON RESPONSE SCHEMA", prompt["system_prompt"])
        self.assertIn("DIAGNOSTIC EVIDENCE", prompt["user_prompt"])
        self.assertIn("EV-", prompt["evidence_id"])
        self.assertGreater(prompt["estimated_tokens"], 20)

    def test_03_recommend_from_snapshot_rule_based(self):
        """Audit heuristic recommendation generation on ad-hoc negative failure snapshot."""
        resp = self.client.post("/api/v1/ai/recommend-from-snapshot", json={
            "test_name": "checkout-null-cart",
            "http_method": "POST",
            "url": "https://api.example.com/checkout",
            "status_code": 500,
            "expected_status": 400,
            "is_negative_test": True,
            "response_body": "KeyError: 'cart_id'",
            "persist": False
        })
        self.assertEqual(resp.status_code, 200)
        card = resp.json()["data"]

        self.assertEqual(card["source"], "RULE_BASED_HEURISTIC")
        self.assertEqual(card["root_cause_category"], "MISSING_INPUT_VALIDATION")
        self.assertEqual(card["severity"], "CRITICAL")
        self.assertIn("Pydantic", card["suggested_fix"])
        self.assertIn("class ItemRequest(BaseModel):", card["code_snippet"])
        self.assertGreater(len(card["references"]), 0)

    def test_04_recommend_for_persisted_result_and_list(self):
        """Audit generating and persisting recommendation linked to TestResult."""
        resp = self.client.post(f"/api/v1/results/{self.result_id}/recommendation?persist=true")
        self.assertEqual(resp.status_code, 200)
        card = resp.json()["data"]
        self.assertEqual(card["source"], "RULE_BASED_HEURISTIC")

        # List persisted recommendations
        list_resp = self.client.get(f"/api/v1/results/{self.result_id}/recommendations")
        self.assertEqual(list_resp.status_code, 200)
        recs = list_resp.json()["data"]
        self.assertGreaterEqual(len(recs), 1)
        self.assertEqual(recs[0]["test_result_id"], self.result_id)
        self.assertEqual(recs[0]["severity"], "CRITICAL")

    def test_05_recommendation_not_found(self):
        """Audit 404 response on non-existent result."""
        resp = self.client.post("/api/v1/results/99999/recommendation")
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
