"""Tests for Negative & Adversarial Testing Engine (Stage 08 Sub-Stages 01 & 02)."""
import unittest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.core.database import Base, engine, SessionLocal
from app.models.entities.project import Project
from app.models.entities.endpoint import Endpoint
from app.models.schemas.adversarial import (
    MutationStrategy,
    PayloadMutationRequest,
    NegativeTestEvaluationRequest,
    AdversarialEndpointScanRequest,
)
from app.models.schemas.execution import ExecutionResultResponse
from app.utils.mutation_engine import (
    mutate_missing_fields,
    mutate_type_inversions,
    mutate_boundaries,
    mutate_null_injections,
    generate_all_mutations,
)
from app.utils.adversarial_classifier import classify_negative_response
from app.services.adversarial_service import AdversarialService


class TestMutationEngine(unittest.TestCase):
    """Unit tests for combinatorial payload mutation generators."""

    def setUp(self):
        self.sample_payload = {
            "username": "johndoe",
            "age": 30,
            "is_active": True,
            "tags": ["dev", "python"],
            "profile": {
                "bio": "Developer",
                "score": 95
            }
        }

    def test_mutate_missing_fields(self):
        mutations = mutate_missing_fields(self.sample_payload)
        self.assertGreaterEqual(len(mutations), 6)  # 5 top-level keys + 2 nested keys
        
        # Check that top-level username is omitted in one variant
        username_mut = next(m for m in mutations if m["target_field"] == "username")
        self.assertNotIn("username", username_mut["payload"])
        self.assertEqual(username_mut["strategy"], "missing_required_field")

        # Check nested omission
        nested_mut = next(m for m in mutations if m["target_field"] == "profile.bio")
        self.assertNotIn("bio", nested_mut["payload"]["profile"])

    def test_mutate_type_inversions(self):
        mutations = mutate_type_inversions(self.sample_payload)
        self.assertGreater(len(mutations), 0)

        # Check age (int) inversion
        age_muts = [m for m in mutations if m["target_field"] == "age"]
        self.assertTrue(any(isinstance(m["mutated_value"], str) for m in age_muts))
        self.assertTrue(any(isinstance(m["mutated_value"], bool) for m in age_muts))

        # Check username (str) inversion
        user_muts = [m for m in mutations if m["target_field"] == "username"]
        self.assertTrue(any(isinstance(m["mutated_value"], int) for m in user_muts))

    def test_mutate_boundaries(self):
        mutations = mutate_boundaries(self.sample_payload)
        self.assertGreater(len(mutations), 0)

        # String boundary (empty string, XSS, huge string)
        user_muts = [m for m in mutations if m["target_field"] == "username"]
        mutated_vals = [m["mutated_value"] for m in user_muts]
        self.assertIn("", mutated_vals)

        # Integer boundary (0, negative, overflow)
        age_muts = [m for m in mutations if m["target_field"] == "age"]
        age_vals = [m["mutated_value"] for m in age_muts]
        self.assertIn(0, age_vals)
        self.assertIn(-1, age_vals)

    def test_mutate_null_injections(self):
        mutations = mutate_null_injections(self.sample_payload)
        self.assertGreaterEqual(len(mutations), 6)

        user_mut = next(m for m in mutations if m["target_field"] == "username")
        self.assertIsNone(user_mut["payload"]["username"])

    def test_generate_all_mutations_and_limits(self):
        # Max limit enforcement
        all_muts = generate_all_mutations(self.sample_payload, max_count=10)
        self.assertLessEqual(len(all_muts), 10)
        self.assertTrue(all(m["mutation_id"].startswith("MUT-") for m in all_muts))

        # Specific strategy filtering
        missing_only = generate_all_mutations(
            self.sample_payload,
            strategies=["missing_required_field"]
        )
        self.assertTrue(all(m["strategy"] == "missing_required_field" for m in missing_only))


class TestAdversarialClassifier(unittest.TestCase):
    """Unit tests for 4xx vs 500 response classification."""

    def test_classify_properly_handled_4xx(self):
        res_400 = classify_negative_response(400)
        self.assertTrue(res_400["passed"])
        self.assertEqual(res_400["classification"], "PROPERLY_HANDLED_4XX")
        self.assertEqual(res_400["severity"], "NONE")
        self.assertEqual(res_400["verdict"], "PASS")

        res_422 = classify_negative_response(422)
        self.assertTrue(res_422["passed"])
        self.assertEqual(res_422["classification"], "PROPERLY_HANDLED_4XX")

    def test_classify_unhandled_5xx_crash(self):
        res_500 = classify_negative_response(500, mutation_info={"target_field": "age", "strategy": "type_inversion"})
        self.assertFalse(res_500["passed"])
        self.assertEqual(res_500["classification"], "UNHANDLED_SERVER_EXCEPTION_5XX")
        self.assertEqual(res_500["severity"], "CRITICAL")
        self.assertEqual(res_500["verdict"], "FAIL_CRITICAL")
        self.assertIn("CRITICAL VULNERABILITY", res_500["message"])
        self.assertIsNotNone(res_500["recommendation"])

    def test_classify_unvalidated_2xx_acceptance(self):
        res_200 = classify_negative_response(200, mutation_info={"target_field": "email", "strategy": "boundary_extreme_value"})
        self.assertFalse(res_200["passed"])
        self.assertEqual(res_200["classification"], "UNVALIDATED_ACCEPTANCE_2XX")
        self.assertEqual(res_200["severity"], "HIGH")
        self.assertEqual(res_200["verdict"], "FAIL_HIGH")
        self.assertIn("HIGH VULNERABILITY", res_200["message"])


class TestAdversarialServiceAndAPI(unittest.TestCase):
    """Integration tests for Adversarial Service and REST API routes."""

    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)
        cls.db: Session = SessionLocal()
        cls.client = TestClient(app)

        cls.project = Project(
            name="Adversarial Testing Project",
            base_url="https://api.adversarial-test.com"
        )
        cls.db.add(cls.project)
        cls.db.commit()
        cls.db.refresh(cls.project)

        cls.endpoint = Endpoint(
            project_id=cls.project.id,
            name="Create Account",
            method="POST",
            path="/accounts",
            body_schema={
                "type": "object",
                "required": ["username", "email", "tier"],
                "properties": {
                    "username": {"type": "string"},
                    "email": {"type": "string"},
                    "tier": {"type": "integer"}
                }
            }
        )
        cls.db.add(cls.endpoint)
        cls.db.commit()
        cls.db.refresh(cls.endpoint)

    @classmethod
    def tearDownClass(cls):
        cls.db.query(Endpoint).filter(Endpoint.project_id == cls.project.id).delete()
        cls.db.query(Project).filter(Project.id == cls.project.id).delete()
        cls.db.commit()
        cls.db.close()

    def test_api_generate_mutations(self):
        res = self.client.post("/api/v1/adversarial/mutate", json={
            "baseline_payload": {
                "username": "testuser",
                "email": "test@test.com",
                "tier": 1
            },
            "strategies": ["missing_required_field", "type_inversion"],
            "max_mutations": 15
        })
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["success"])
        self.assertGreater(body["data"]["total_mutations"], 0)
        self.assertLessEqual(body["data"]["total_mutations"], 15)

    def test_api_evaluate_response(self):
        # 422 Rejection
        res_422 = self.client.post("/api/v1/adversarial/evaluate-response", json={
            "status_code": 422,
            "target_field": "email",
            "strategy": "boundary_extreme_value"
        })
        self.assertEqual(res_422.status_code, 200)
        self.assertTrue(res_422.json()["success"])
        self.assertEqual(res_422.json()["data"]["classification"], "PROPERLY_HANDLED_4XX")

        # 500 Crash
        res_500 = self.client.post("/api/v1/adversarial/evaluate-response", json={
            "status_code": 500,
            "target_field": "tier",
            "strategy": "type_inversion"
        })
        self.assertEqual(res_500.status_code, 200)
        self.assertFalse(res_500.json()["success"])
        self.assertEqual(res_500.json()["data"]["classification"], "UNHANDLED_SERVER_EXCEPTION_5XX")
        self.assertEqual(res_500.json()["data"]["severity"], "CRITICAL")

    @patch("app.services.http_dispatcher.HttpDispatcherService.dispatch_endpoint", new_callable=AsyncMock)
    def test_api_scan_endpoint_success(self, mock_dispatch):
        # Mock dispatcher returning 422 for all invalid inputs
        mock_dispatch.return_value = ExecutionResultResponse(
            url="https://api.adversarial-test.com/accounts",
            method="POST",
            status_code=422,
            status_text="Unprocessable Entity",
            headers={"content-type": "application/json"},
            body="{'detail': 'Validation failed'}",
            parsed_body={"detail": "Validation failed"},
            elapsed_ms=12.5,
            is_success=False,
            redirect_count=0
        )

        res = self.client.post(f"/api/v1/adversarial/endpoints/{self.endpoint.id}/scan", json={
            "max_mutations": 5,
            "timeout_seconds": 2.0
        })
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["properly_handled_4xx_count"], 5)
        self.assertEqual(body["data"]["unhandled_5xx_crashes_count"], 0)
        self.assertEqual(body["data"]["safety_score"], 100.0)

    @patch("app.services.http_dispatcher.HttpDispatcherService.dispatch_endpoint", new_callable=AsyncMock)
    def test_api_scan_endpoint_vulnerabilities_detected(self, mock_dispatch):
        # Mock dispatcher returning 500 crash
        mock_dispatch.return_value = ExecutionResultResponse(
            url="https://api.adversarial-test.com/accounts",
            method="POST",
            status_code=500,
            status_text="Internal Server Error",
            headers={"content-type": "text/plain"},
            body="NullPointerException in UserHandler",
            elapsed_ms=45.0,
            is_success=False,
            redirect_count=0
        )

        res = self.client.post(f"/api/v1/adversarial/endpoints/{self.endpoint.id}/scan", json={
            "max_mutations": 4
        })
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertFalse(body["success"])
        self.assertEqual(body["data"]["unhandled_5xx_crashes_count"], 4)
        self.assertEqual(body["data"]["safety_score"], 0.0)
        self.assertEqual(len(body["data"]["critical_vulnerabilities"]), 4)

    def test_api_scan_endpoint_not_found(self):
        res = self.client.post("/api/v1/adversarial/endpoints/99999/scan", json={
            "max_mutations": 5
        })
        self.assertEqual(res.status_code, 404)


if __name__ == "__main__":
    unittest.main()
