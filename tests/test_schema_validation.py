"""Tests for JSON Schema & Strict Data Type Validator Engine (Stage 07 Sub-Stage 02)."""
import unittest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.core.database import Base, engine, SessionLocal
from app.models.entities.project import Project
from app.models.entities.endpoint import Endpoint
from app.utils.schema_validator import (
    format_json_path,
    validate_json_schema_instance,
)
from app.services.validation_service import ValidationService


class TestSchemaValidatorUtils(unittest.TestCase):
    """Unit tests for low-level schema validator utility functions."""

    def setUp(self):
        self.sample_schema = {
            "type": "object",
            "required": ["id", "username", "email", "age"],
            "properties": {
                "id": {"type": "integer"},
                "username": {"type": "string", "minLength": 3, "maxLength": 20},
                "email": {"type": "string", "pattern": r"^[\w\.-]+@[\w\.-]+\.\w+$"},
                "age": {"type": "integer", "minimum": 18, "maximum": 120},
                "roles": {
                    "type": "array",
                    "minItems": 1,
                    "items": {"type": "string", "enum": ["admin", "editor", "viewer"]}
                },
                "profile": {
                    "type": "object",
                    "required": ["bio"],
                    "properties": {
                        "bio": {"type": "string"},
                        "website": {"type": "string"}
                    },
                    "additionalProperties": False
                }
            },
            "additionalProperties": True
        }

    def test_path_formatting(self):
        self.assertEqual(format_json_path([]), "$")
        self.assertEqual(format_json_path(["user", "name"]), "user.name")
        self.assertEqual(format_json_path(["users", 0, "email"]), "users[0].email")
        self.assertEqual(format_json_path(["items", 2, "tags", 1]), "items[2].tags[1]")

    def test_perfect_schema_match(self):
        valid_payload = {
            "id": 1,
            "username": "alice",
            "email": "alice@example.com",
            "age": 28,
            "roles": ["admin", "editor"],
            "profile": {
                "bio": "Software Engineer"
            }
        }
        is_valid, errors, stats = validate_json_schema_instance(valid_payload, self.sample_schema)
        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)
        self.assertEqual(stats["total_errors"], 0)
        self.assertIn("0 violations", stats["summary"])

    def test_missing_required_fields(self):
        incomplete_payload = {
            "id": 1,
            "username": "bob"
            # Missing email and age
        }
        is_valid, errors, stats = validate_json_schema_instance(incomplete_payload, self.sample_schema)
        self.assertFalse(is_valid)
        self.assertGreaterEqual(stats["total_errors"], 2)
        missing = stats["missing_fields"]
        self.assertTrue(any("email" in f for f in missing))
        self.assertTrue(any("age" in f for f in missing))

    def test_type_mismatch_extraction(self):
        type_wrong_payload = {
            "id": "not_an_int",
            "username": "charlie",
            "email": "charlie@test.com",
            "age": "thirty",
            "roles": ["viewer"],
            "profile": {"bio": "Hello"}
        }
        is_valid, errors, stats = validate_json_schema_instance(type_wrong_payload, self.sample_schema)
        self.assertFalse(is_valid)
        mismatches = stats["type_mismatches"]
        self.assertGreaterEqual(len(mismatches), 2)
        paths = [m["path"] for m in mismatches]
        self.assertIn("id", paths)
        self.assertIn("age", paths)

    def test_enum_and_range_violations(self):
        invalid_payload = {
            "id": 2,
            "username": "dan",
            "email": "dan@test.com",
            "age": 15,  # Below minimum 18
            "roles": ["superadmin"],  # Not in enum
            "profile": {"bio": "Admin"}
        }
        is_valid, errors, stats = validate_json_schema_instance(invalid_payload, self.sample_schema)
        self.assertFalse(is_valid)
        err_types = [e["error_type"] for e in errors]
        self.assertIn("range_minimum_violation", err_types)
        self.assertIn("enum_constraint_violation", err_types)

    def test_nested_additional_properties_forbidden(self):
        extra_prop_payload = {
            "id": 3,
            "username": "eve_user",
            "email": "eve@test.com",
            "age": 22,
            "roles": ["viewer"],
            "profile": {
                "bio": "Security Researcher",
                "hacker_score": 999  # forbidden additional property
            }
        }
        is_valid, errors, stats = validate_json_schema_instance(extra_prop_payload, self.sample_schema)
        self.assertFalse(is_valid)
        err_types = [e["error_type"] for e in errors]
        self.assertIn("additional_property_forbidden", err_types)

    def test_pattern_and_length_violations(self):
        bad_format_payload = {
            "id": 4,
            "username": "a",  # minLength 3
            "email": "not-an-email",  # regex pattern mismatch
            "age": 30,
            "roles": [],  # minItems 1
            "profile": {"bio": "Dev"}
        }
        is_valid, errors, stats = validate_json_schema_instance(bad_format_payload, self.sample_schema)
        self.assertFalse(is_valid)
        err_types = [e["error_type"] for e in errors]
        self.assertIn("length_minLength_violation", err_types)
        self.assertIn("pattern_mismatch", err_types)
        self.assertIn("length_minItems_violation", err_types)

    def test_malformed_json_schema(self):
        bad_schema = {
            "type": "invalid_type_name_unknown"
        }
        is_valid, errors, stats = validate_json_schema_instance({"test": 1}, bad_schema)
        self.assertFalse(is_valid)
        self.assertEqual(errors[0]["error_type"], "schema_syntax_error")


class TestValidationServiceSchema(unittest.TestCase):
    """Unit tests for ValidationService JSON Schema methods."""

    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)
        cls.db: Session = SessionLocal()
        cls.project = Project(
            name="Schema Validation Test Project",
            base_url="https://api.example.com",
            description="Testing JSON schema service"
        )
        cls.db.add(cls.project)
        cls.db.commit()
        cls.db.refresh(cls.project)

        cls.endpoint = Endpoint(
            project_id=cls.project.id,
            name="Get User Profile",
            method="GET",
            path="/users/{user_id}",
            response_schema={
                "type": "object",
                "required": ["id", "username", "status"],
                "properties": {
                    "id": {"type": "integer"},
                    "username": {"type": "string"},
                    "status": {"type": "string", "enum": ["active", "suspended"]}
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

    def test_validate_json_schema_with_string_and_dict(self):
        schema = {"type": "object", "required": ["count"], "properties": {"count": {"type": "integer"}}}
        
        # Valid dict
        report1 = ValidationService.validate_json_schema({"count": 42}, schema)
        self.assertTrue(report1.is_valid)
        self.assertEqual(report1.total_errors, 0)

        # Valid string
        report2 = ValidationService.validate_json_schema('{"count": 99}', schema)
        self.assertTrue(report2.is_valid)

        # Invalid type
        report3 = ValidationService.validate_json_schema({"count": "NaN"}, schema)
        self.assertFalse(report3.is_valid)
        self.assertEqual(len(report3.type_mismatches), 1)

    def test_validate_endpoint_response_schema_success_and_failure(self):
        # Valid response
        valid_res = {"id": 100, "username": "alpha_tester", "status": "active"}
        report_ok = ValidationService.validate_endpoint_response_schema(self.endpoint.id, valid_res, self.db)
        self.assertTrue(report_ok.is_valid)

        # Invalid response (status enum invalid & id wrong type)
        bad_res = {"id": "100", "username": "alpha_tester", "status": "deleted"}
        report_bad = ValidationService.validate_endpoint_response_schema(self.endpoint.id, bad_res, self.db)
        self.assertFalse(report_bad.is_valid)
        self.assertGreaterEqual(report_bad.total_errors, 2)


class TestValidationSchemaAPIEndpoints(unittest.TestCase):
    """Integration tests for JSON Schema Validation API routes."""

    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)
        cls.db = SessionLocal()
        cls.client = TestClient(app)

        cls.project = Project(
            name="API Test Project",
            base_url="https://api.test.com"
        )
        cls.db.add(cls.project)
        cls.db.commit()
        cls.db.refresh(cls.project)

        cls.endpoint = Endpoint(
            project_id=cls.project.id,
            name="API Test Endpoint",
            method="GET",
            path="/items",
            response_schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["item_id", "price"],
                    "properties": {
                        "item_id": {"type": "integer"},
                        "price": {"type": "number", "minimum": 0.01}
                    }
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

    def test_api_validate_json_schema_endpoint(self):
        schema = {
            "type": "object",
            "required": ["code", "message"],
            "properties": {
                "code": {"type": "integer"},
                "message": {"type": "string"}
            }
        }

        # Valid payload
        res = self.client.post("/api/v1/validations/json-schema", json={
            "instance": {"code": 200, "message": "Success"},
            "schema_definition": schema
        })
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["success"])
        self.assertTrue(body["data"]["is_valid"])
        self.assertEqual(body["data"]["total_errors"], 0)

        # Invalid payload (missing required field)
        res_bad = self.client.post("/api/v1/validations/json-schema", json={
            "instance": {"code": 200},
            "schema_definition": schema
        })
        self.assertEqual(res_bad.status_code, 200)
        body_bad = res_bad.json()
        self.assertFalse(body_bad["success"])
        self.assertFalse(body_bad["data"]["is_valid"])
        self.assertEqual(body_bad["data"]["total_errors"], 1)

    def test_api_validate_endpoint_response_schema_endpoint(self):
        # Valid array payload
        payload_ok = [
            {"item_id": 1, "price": 19.99},
            {"item_id": 2, "price": 49.50}
        ]
        res = self.client.post(f"/api/v1/validations/endpoints/{self.endpoint.id}/response-schema", json={
            "response_payload": payload_ok
        })
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["success"])
        self.assertTrue(body["data"]["is_valid"])

        # Invalid array payload (item 2 missing price)
        payload_bad = [
            {"item_id": 1, "price": 19.99},
            {"item_id": 2}
        ]
        res_bad = self.client.post(f"/api/v1/validations/endpoints/{self.endpoint.id}/response-schema", json={
            "response_payload": payload_bad
        })
        self.assertEqual(res_bad.status_code, 200)
        body_bad = res_bad.json()
        self.assertFalse(body_bad["success"])
        self.assertFalse(body_bad["data"]["is_valid"])

    def test_api_validate_endpoint_not_found(self):
        res = self.client.post("/api/v1/validations/endpoints/99999/response-schema", json={
            "response_payload": {"test": 1}
        })
        self.assertEqual(res.status_code, 404)


if __name__ == "__main__":
    unittest.main()
