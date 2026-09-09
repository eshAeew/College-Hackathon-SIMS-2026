"""Unit & Integration tests for Endpoint Parameter, Header & Body Contract Specifications."""
import unittest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core.database import Base, get_db
from app.utils.contract_parser import (
    extract_path_variables,
    validate_json_schema,
    validate_contract_specification,
)

# Use shared in-memory SQLite database with StaticPool for test execution
SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    """Override database session for testing."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


class TestContractSpecification(unittest.TestCase):
    """Test suite verifying URL path variable extraction, JSON Schema validation, and contract endpoints."""

    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=test_engine)
        app.dependency_overrides[get_db] = override_get_db

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(bind=test_engine)
        app.dependency_overrides.clear()

    def setUp(self):
        self.client = TestClient(app)

    def test_01_path_variable_extraction_unit(self):
        """Verify variable extraction from various URL path patterns."""
        self.assertEqual(
            extract_path_variables("/api/v1/users/{user_id}/orders/{order_id}"),
            ["user_id", "order_id"]
        )
        self.assertEqual(extract_path_variables("/api/v1/health"), [])
        self.assertEqual(
            extract_path_variables("/stores/{id}/items/{id}"),
            ["id"]
        )
        self.assertEqual(extract_path_variables(""), [])

    def test_02_json_schema_validation_unit(self):
        """Verify JSON Schema validation against Draft-7 specification."""
        valid_schema = {
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
                "email": {"type": "string", "format": "email"}
            },
            "required": ["id", "email"]
        }
        is_valid, err = validate_json_schema(valid_schema)
        self.assertTrue(is_valid)
        self.assertIsNone(err)

        # Empty schema is valid
        self.assertTrue(validate_json_schema({})[0])
        self.assertTrue(validate_json_schema(None)[0])

        # Invalid type specification in JSON Schema
        invalid_schema = {"type": "unsupported_data_type"}
        is_invalid, err_msg = validate_json_schema(invalid_schema)
        self.assertFalse(is_invalid)
        self.assertIsNotNone(err_msg)

    def test_03_contract_specification_inspection_unit(self):
        """Verify contract specification inspection logic."""
        res_complete = validate_contract_specification(
            path="/api/v1/users/{user_id}",
            path_params={"user_id": "42"},
            body_schema={"type": "object"},
            response_schema={"type": "object"}
        )
        self.assertTrue(res_complete["is_valid"])
        self.assertEqual(res_complete["path_variables"], ["user_id"])
        self.assertEqual(res_complete["missing_path_params"], [])

        res_missing = validate_contract_specification(
            path="/api/v1/users/{user_id}/orders/{order_id}",
            path_params={"user_id": "42"}  # order_id missing
        )
        self.assertFalse(res_missing["is_valid"])
        self.assertEqual(res_missing["missing_path_params"], ["order_id"])

    def test_04_ad_hoc_validate_contract_api(self):
        """Verify POST /api/v1/endpoints/validate-contract endpoint."""
        payload = {
            "path": "/api/v1/organizations/{org_id}/members/{member_id}",
            "path_params": {"org_id": "acme-corp", "member_id": "1001"},
            "headers": {"Content-Type": "application/json", "Accept": "application/json"},
            "query_params": {"role": "admin"},
            "body_schema": {
                "type": "object",
                "properties": {"role": {"type": "string"}},
                "required": ["role"]
            },
            "response_schema": {
                "type": "object",
                "properties": {"status": {"type": "string"}},
                "required": ["status"]
            }
        }
        resp = self.client.post("/api/v1/endpoints/validate-contract", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertTrue(data["is_valid"])
        self.assertEqual(data["path_variables"], ["org_id", "member_id"])
        self.assertEqual(data["missing_path_params"], [])

        # Test invalid schema payload
        invalid_payload = {
            "path": "/api/v1/test",
            "body_schema": {"type": "not_a_real_type"}
        }
        resp_inv = self.client.post("/api/v1/endpoints/validate-contract", json=invalid_payload)
        self.assertEqual(resp_inv.status_code, 200)
        self.assertFalse(resp_inv.json()["data"]["is_valid"])
        self.assertTrue(len(resp_inv.json()["data"]["errors"]) > 0)

    def test_05_get_endpoint_contract_api(self):
        """Verify GET /api/v1/endpoints/{id}/contract endpoint."""
        # Create project and endpoint
        proj_resp = self.client.post("/api/v1/projects", json={
            "name": "Contract Test Project",
            "base_url": "https://api.contract.com"
        })
        proj_id = proj_resp.json()["data"]["id"]

        ep_resp = self.client.post(f"/api/v1/projects/{proj_id}/endpoints", json={
            "name": "Get User Details",
            "method": "GET",
            "path": "/api/v1/users/{user_id}",
            "path_params": {"user_id": "99"},
            "headers": {"Authorization": "Bearer token-xyz"},
            "query_params": {"full": "true"},
            "expected_status": 200,
            "response_schema": {
                "type": "object",
                "properties": {"name": {"type": "string"}}
            }
        })
        ep_id = ep_resp.json()["data"]["id"]

        contract_resp = self.client.get(f"/api/v1/endpoints/{ep_id}/contract")
        self.assertEqual(contract_resp.status_code, 200)
        contract = contract_resp.json()["data"]
        self.assertEqual(contract["endpoint_id"], ep_id)
        self.assertEqual(contract["path"], "/api/v1/users/{user_id}")
        self.assertEqual(contract["path_variables"], ["user_id"])
        self.assertEqual(contract["path_params"]["user_id"], "99")
        self.assertEqual(contract["headers"]["Authorization"], "Bearer token-xyz")
        self.assertEqual(contract["expected_status"], 200)
        self.assertTrue(contract["is_valid"])
        self.assertEqual(contract["missing_path_params"], [])

    def test_06_update_endpoint_contract_api(self):
        """Verify PUT /api/v1/endpoints/{id}/contract endpoint."""
        update_payload = {
            "headers": {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-Api-Key": "key-999"
            },
            "query_params": {"page": 1, "size": 50},
            "path_params": {"user_id": "42"},
            "expected_status": 201,
            "body_schema": {
                "type": "object",
                "properties": {"action": {"type": "string"}}
            },
            "response_schema": {
                "type": "object",
                "properties": {"result": {"type": "string"}}
            }
        }
        resp = self.client.put("/api/v1/endpoints/1/contract", json=update_payload)
        self.assertEqual(resp.status_code, 200)
        contract = resp.json()["data"]
        self.assertEqual(contract["expected_status"], 201)
        self.assertEqual(contract["headers"]["X-Api-Key"], "key-999")
        self.assertEqual(contract["query_params"]["size"], 50)
        self.assertIn("action", contract["body_schema"]["properties"])
        self.assertIn("result", contract["response_schema"]["properties"])

    def test_07_update_contract_invalid_schema_returns_422(self):
        """Verify 422 Unprocessable Entity when updating contract with malformed JSON Schema."""
        invalid_update = {
            "body_schema": {"type": "invalid_type_name_schema"}
        }
        resp = self.client.put("/api/v1/endpoints/1/contract", json=invalid_update)
        self.assertEqual(resp.status_code, 422)

    def test_08_contract_endpoints_not_found(self):
        """Verify 404 for contract requests on non-existent endpoint."""
        self.assertEqual(self.client.get("/api/v1/endpoints/99999/contract").status_code, 404)
        self.assertEqual(
            self.client.put("/api/v1/endpoints/99999/contract", json={"expected_status": 200}).status_code,
            404
        )


if __name__ == "__main__":
    unittest.main()
