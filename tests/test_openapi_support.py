"""Unit and Integration Tests for OpenAPI 3.0 / Swagger 2.0 Ingestion (Stage 14)."""
import unittest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.entities.endpoint import Endpoint
from app.models.entities.project import Project
from app.models.schemas.openapi import OpenApiSpecVersion
from app.utils.openapi_parser import (
    dereference_schema,
    detect_spec_format_and_parse,
    detect_spec_version,
    parse_openapi_document,
)

SAMPLE_OPENAPI_3_JSON = """{
  "openapi": "3.0.0",
  "info": {
    "title": "Petstore Inventory API",
    "version": "1.2.0",
    "description": "Sample API for managing pet store items"
  },
  "servers": [
    {"url": "https://api.petstore.com/v1"}
  ],
  "paths": {
    "/pets": {
      "get": {
        "summary": "List all pets",
        "operationId": "listPets",
        "tags": ["pets"],
        "parameters": [
          {"name": "limit", "in": "query", "required": false, "schema": {"type": "integer", "default": 20}}
        ],
        "responses": {
          "200": {
            "description": "A paged array of pets",
            "content": {
              "application/json": {
                "schema": {
                  "type": "array",
                  "items": {"$ref": "#/components/schemas/Pet"}
                }
              }
            }
          }
        }
      },
      "post": {
        "summary": "Create a pet",
        "operationId": "createPets",
        "tags": ["pets"],
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {"$ref": "#/components/schemas/Pet"}
            }
          }
        },
        "responses": {
          "201": {
            "description": "Null response"
          }
        }
      }
    },
    "/pets/{petId}": {
      "get": {
        "summary": "Info for a specific pet",
        "operationId": "showPetById",
        "tags": ["pets"],
        "parameters": [
          {"name": "petId", "in": "path", "required": true, "schema": {"type": "integer"}}
        ],
        "responses": {
          "200": {
            "description": "Expected response to a valid request",
            "content": {
              "application/json": {
                "schema": {"$ref": "#/components/schemas/Pet"}
              }
            }
          }
        }
      }
    }
  },
  "components": {
    "schemas": {
      "Pet": {
        "type": "object",
        "required": ["id", "name"],
        "properties": {
          "id": {"type": "integer", "format": "int64"},
          "name": {"type": "string"},
          "tag": {"type": "string"}
        }
      }
    }
  }
}"""

SAMPLE_SWAGGER_2_YAML = """
swagger: '2.0'
info:
  title: Swagger User API
  version: 2.0.0
host: api.users.com
basePath: /v2
schemes:
  - https
paths:
  /users:
    get:
      summary: Get all users
      responses:
        '200':
          description: OK
          schema:
            type: array
            items:
              $ref: '#/definitions/User'
definitions:
  User:
    type: object
    properties:
      id:
        type: integer
      email:
        type: string
"""


class TestOpenApiParserUnits(unittest.TestCase):
    """Unit tests for OpenAPI/Swagger parser and $ref resolution."""

    def test_parse_json_spec(self):
        doc = detect_spec_format_and_parse(SAMPLE_OPENAPI_3_JSON)
        self.assertIn("openapi", doc)
        self.assertEqual(detect_spec_version(doc), OpenApiSpecVersion.OPENAPI_3_0)

    def test_parse_yaml_spec(self):
        doc = detect_spec_format_and_parse(SAMPLE_SWAGGER_2_YAML)
        self.assertIn("swagger", doc)
        self.assertEqual(detect_spec_version(doc), OpenApiSpecVersion.SWAGGER_2_0)

    def test_parse_openapi_3_document_discovery(self):
        doc = detect_spec_format_and_parse(SAMPLE_OPENAPI_3_JSON)
        summary = parse_openapi_document(doc)
        
        self.assertEqual(summary.title, "Petstore Inventory API")
        self.assertEqual(summary.version, "1.2.0")
        self.assertEqual(summary.total_operations, 3)
        self.assertEqual(len(summary.servers), 1)
        self.assertEqual(summary.servers[0], "https://api.petstore.com/v1")

        # Test operations
        list_op = next(op for op in summary.operations if op.path == "/pets" and op.method == "GET")
        self.assertEqual(list_op.expected_status_code, 200)
        self.assertEqual(len(list_op.parameters), 1)
        self.assertEqual(list_op.parameters[0].name, "limit")

        # Test POST /pets body schema dereferencing
        post_op = next(op for op in summary.operations if op.path == "/pets" and op.method == "POST")
        self.assertEqual(post_op.expected_status_code, 201)
        self.assertIsNotNone(post_op.request_body_schema)
        self.assertEqual(post_op.request_body_schema.get("type"), "object")
        self.assertIn("id", post_op.request_body_schema.get("properties", {}))

    def test_dereference_schema_resolution(self):
        doc = {
            "components": {
                "schemas": {
                    "Address": {
                        "type": "object",
                        "properties": {"city": {"type": "string"}}
                    }
                }
            }
        }
        ref_schema = {"$ref": "#/components/schemas/Address"}
        resolved = dereference_schema(ref_schema, doc)
        self.assertEqual(resolved["type"], "object")
        self.assertIn("city", resolved["properties"])


class TestOpenApiAPIIntegration(unittest.TestCase):
    """Integration tests for OpenAPI REST endpoints."""

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
        self.project = Project(name="OpenAPI Import Workspace", base_url="https://api.example.com")
        self.db.add(self.project)
        self.db.commit()

    def tearDown(self):
        self.db.query(Endpoint).delete()
        self.db.query(Project).delete()
        self.db.commit()
        self.db.close()

    def test_validate_openapi_endpoint(self):
        payload = {"spec_content": SAMPLE_OPENAPI_3_JSON}
        response = self.client.post("/api/v1/openapi/validate", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["title"], "Petstore Inventory API")
        self.assertEqual(data["total_operations"], 3)

    def test_preview_project_openapi_spec(self):
        payload = {"spec_content": SAMPLE_SWAGGER_2_YAML}
        response = self.client.post(f"/api/v1/projects/{self.project.id}/openapi/parse", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["title"], "Swagger User API")
        self.assertEqual(data["total_operations"], 1)

    def test_import_openapi_spec_into_project(self):
        payload = {
            "spec_content": SAMPLE_OPENAPI_3_JSON,
            "overwrite_existing": True,
            "create_smoke_tests": True
        }
        response = self.client.post(f"/api/v1/projects/{self.project.id}/openapi/import", json=payload)
        self.assertEqual(response.status_code, 201)
        data = response.json()["data"]
        self.assertEqual(data["total_discovered"], 3)
        self.assertEqual(data["created_count"], 3)
        self.assertEqual(data["updated_count"], 0)

        # Verify endpoints persisted in SQLite database
        endpoints = self.db.query(Endpoint).filter(Endpoint.project_id == self.project.id).all()
        self.assertEqual(len(endpoints), 3)

        # Re-import with overwrite should update existing
        reimport_resp = self.client.post(f"/api/v1/projects/{self.project.id}/openapi/import", json=payload)
        self.assertEqual(reimport_resp.status_code, 201)
        re_data = reimport_resp.json()["data"]
        self.assertEqual(re_data["created_count"], 0)
        self.assertEqual(re_data["updated_count"], 3)

    def test_upload_openapi_file_endpoint(self):
        files = {
            "file": ("swagger.yaml", SAMPLE_SWAGGER_2_YAML.encode("utf-8"), "application/x-yaml")
        }
        response = self.client.post(
            f"/api/v1/projects/{self.project.id}/openapi/import-file",
            files=files,
            data={"overwrite_existing": "true", "create_smoke_tests": "false"}
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()["data"]
        self.assertEqual(data["created_count"], 1)


if __name__ == "__main__":
    unittest.main()
