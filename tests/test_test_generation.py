"""Unit and Integration Tests for Automatic Test Generation Engine (Stage 15)."""
import json
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
from app.models.schemas.test_generation import (
    AcceptStagedTestsRequest,
    AdHocTestGenerationRequest,
    BulkProjectTestGenerationRequest,
    EndpointTestGenerationRequest,
    GeneratedTestCategory,
    StagedTestCase,
    TestGenerationOptions,
    TestGenerationStrategy,
)
from app.utils.test_synthesizer import (
    generate_mock_value_for_schema,
    generate_test_suite_for_endpoint,
    synthesize_happy_path_payload,
    synthesize_mock_path_params,
)


class TestSynthesizerUnit(unittest.TestCase):
    """Unit tests for schema-to-mock generator and test synthesizer."""

    def test_mock_value_generation_types(self):
        """Verify mock data generation across string, integer, float, bool, array, and object types."""
        # String with email format
        email_val = generate_mock_value_for_schema({"type": "string", "format": "email"}, "contact_email")
        self.assertIn("@", email_val)

        # String with uuid format
        uuid_val = generate_mock_value_for_schema({"type": "string", "format": "uuid"}, "user_id")
        self.assertEqual(uuid_val, "123e4567-e89b-12d3-a456-426614174000")

        # Integer with min/max
        int_val = generate_mock_value_for_schema({"type": "integer", "minimum": 10}, "age")
        self.assertGreaterEqual(int_val, 10)

        # Enum
        enum_val = generate_mock_value_for_schema({"type": "string", "enum": ["ADMIN", "USER"]}, "role")
        self.assertIn(enum_val, ["ADMIN", "USER"])

        # Array of objects
        arr_schema = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "sku": {"type": "string"},
                    "quantity": {"type": "integer", "minimum": 1}
                }
            }
        }
        arr_val = generate_mock_value_for_schema(arr_schema, "cart_items")
        self.assertIsInstance(arr_val, list)
        self.assertGreaterEqual(len(arr_val), 1)
        self.assertIn("sku", arr_val[0])
        self.assertIn("quantity", arr_val[0])

    def test_synthesize_path_params(self):
        """Verify dynamic path placeholder extraction and mock population."""
        path = "/api/v1/organizations/{org_id}/users/{user_name}/orders/{orderId}"
        params = synthesize_mock_path_params(path)
        self.assertIn("org_id", params)
        self.assertIn("user_name", params)
        self.assertIn("orderId", params)

    def test_generate_test_suite_combinatorial(self):
        """Verify generation of happy path, missing fields, invalid types, boundaries, and null injections."""
        body_schema = {
            "type": "object",
            "required": ["username", "email", "age"],
            "properties": {
                "username": {"type": "string", "minLength": 3},
                "email": {"type": "string", "format": "email"},
                "age": {"type": "integer", "minimum": 18}
            }
        }

        staged_tests = generate_test_suite_for_endpoint(
            method="POST",
            path="/users",
            body_schema=body_schema,
            options=TestGenerationOptions(strategies=[TestGenerationStrategy.ALL], max_tests_per_endpoint=20)
        )

        self.assertGreaterEqual(len(staged_tests), 5)

        # Verify presence of strategies
        categories = {t.category for t in staged_tests}
        strategies = {t.strategy for t in staged_tests}

        self.assertIn(GeneratedTestCategory.POSITIVE, categories)
        self.assertIn(GeneratedTestCategory.NEGATIVE, categories)
        self.assertIn(TestGenerationStrategy.HAPPY_PATH, strategies)
        self.assertIn(TestGenerationStrategy.MISSING_REQUIRED, strategies)
        self.assertIn(TestGenerationStrategy.INVALID_TYPE, strategies)


class TestTestGenerationAPIIntegration(unittest.TestCase):
    """Integration tests for Test Generation REST API endpoints."""

    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool
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

        # Seed Project and Endpoints
        db = self.SessionLocal()
        self.project = Project(
            name="E-Commerce Microservice",
            description="Test Project for Automated Generation",
            base_url="https://api.ecommerce.example"
        )
        db.add(self.project)
        db.commit()
        db.refresh(self.project)

        self.endpoint_post = Endpoint(
            project_id=self.project.id,
            name="Create Product",
            method="POST",
            path="/products",
            expected_status=201,
            headers_json=json.dumps({"Authorization": "Bearer token123"}),
            body_schema_json=json.dumps({
                "type": "object",
                "required": ["title", "price"],
                "properties": {
                    "title": {"type": "string"},
                    "price": {"type": "number", "minimum": 0.01},
                    "in_stock": {"type": "boolean"}
                }
            }),
            is_active=True
        )
        self.endpoint_get = Endpoint(
            project_id=self.project.id,
            name="Get Product by ID",
            method="GET",
            path="/products/{id}",
            expected_status=200,
            path_params_json=json.dumps({"id": 101}),
            is_active=True
        )
        db.add(self.endpoint_post)
        db.add(self.endpoint_get)
        db.commit()
        db.refresh(self.endpoint_post)
        db.refresh(self.endpoint_get)

        self.project_id = self.project.id
        self.endpoint_post_id = self.endpoint_post.id
        self.endpoint_get_id = self.endpoint_get.id
        db.close()

    def tearDown(self):
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=self.engine)

    def test_adhoc_test_generation_endpoint(self):
        """Verify POST /api/v1/test-generation/generate-adhoc synthesizes valid preview."""
        req_payload = {
            "method": "POST",
            "path": "/orders",
            "body_schema": {
                "type": "object",
                "required": ["order_id", "total_amount"],
                "properties": {
                    "order_id": {"type": "string"},
                    "total_amount": {"type": "number", "minimum": 1.0}
                }
            },
            "options": {
                "include_positive": True,
                "include_negative": True,
                "max_tests_per_endpoint": 10
            }
        }
        resp = self.client.post("/api/v1/test-generation/generate-adhoc", json=req_payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertGreaterEqual(data["total_generated"], 3)
        self.assertEqual(data["positive_count"], 1)
        self.assertGreaterEqual(data["negative_count"], 2)

    def test_endpoint_generate_tests_preview(self):
        """Verify POST /api/v1/endpoints/{id}/generate-tests previews staged test cases."""
        resp = self.client.post(
            f"/api/v1/endpoints/{self.endpoint_post_id}/generate-tests",
            json={"options": {"max_tests_per_endpoint": 10}}
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["endpoint_id"], self.endpoint_post_id)
        self.assertGreaterEqual(len(data["staged_tests"]), 4)

    def test_accept_staged_tests_persists_in_db(self):
        """Verify POST /api/v1/endpoints/{id}/accept-tests saves test cases into SQLite."""
        # Step 1: Generate tests
        gen_resp = self.client.post(f"/api/v1/endpoints/{self.endpoint_post_id}/generate-tests")
        self.assertEqual(gen_resp.status_code, 200)
        staged_tests = gen_resp.json()["data"]["staged_tests"]

        # Step 2: Accept tests
        accept_payload = {
            "staged_tests": staged_tests,
            "activate_immediately": True
        }
        accept_resp = self.client.post(
            f"/api/v1/endpoints/{self.endpoint_post_id}/accept-tests",
            json=accept_payload
        )
        self.assertEqual(accept_resp.status_code, 201)
        data = accept_resp.json()["data"]
        self.assertEqual(data["total_accepted"], len(staged_tests))
        self.assertEqual(len(data["created_test_case_ids"]), len(staged_tests))

        # Step 3: Verify records exist in database
        db = self.SessionLocal()
        saved_cases = db.query(TestCase).filter(TestCase.endpoint_id == self.endpoint_post_id).all()
        self.assertEqual(len(saved_cases), len(staged_tests))
        self.assertTrue(all(c.is_active for c in saved_cases))
        db.close()

    def test_bulk_project_test_generation(self):
        """Verify POST /api/v1/projects/{id}/generate-tests bulk generates for all endpoints."""
        req_payload = {
            "options": {"max_tests_per_endpoint": 5},
            "auto_accept": True
        }
        resp = self.client.post(f"/api/v1/projects/{self.project_id}/generate-tests", json=req_payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["project_id"], self.project_id)
        self.assertEqual(data["total_endpoints_processed"], 2)
        self.assertGreaterEqual(data["total_tests_generated"], 4)
        self.assertEqual(data["total_tests_accepted"], data["total_tests_generated"])



if __name__ == "__main__":
    unittest.main()