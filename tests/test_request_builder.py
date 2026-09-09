"""Unit & Integration tests for Dynamic HTTP Request Builder & Serialization Engine."""
import unittest
import urllib.parse
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core.database import Base, get_db
from app.models.schemas.request_config import BodyType
from app.services.request_builder_service import RequestBuilderService

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


class TestRequestBuilder(unittest.TestCase):
    """Test suite verifying path interpolation, header merging, body serialization, and request compilation."""

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

    def test_01_resolve_path_unit(self):
        """Verify URL path variable interpolation and URL encoding."""
        # Simple resolution
        path = "/api/v1/users/{user_id}/orders/{order_id}"
        resolved = RequestBuilderService.resolve_path(path, {"user_id": "100", "order_id": "200"})
        self.assertEqual(resolved, "/api/v1/users/100/orders/200")

        # Special character encoding
        special_resolved = RequestBuilderService.resolve_path(
            "/api/v1/tags/{tag_name}",
            {"tag_name": "tech & gadgets"}
        )
        self.assertEqual(special_resolved, "/api/v1/tags/tech%20%26%20gadgets")

        # Missing variable raises ValueError
        with self.assertRaises(ValueError):
            RequestBuilderService.resolve_path("/api/v1/users/{user_id}", {})

    def test_02_encode_query_params_unit(self):
        """Verify encoding of primitive, boolean, and array query parameters."""
        params = {
            "search": "running shoes",
            "active": True,
            "category": ["footwear", "sports"],
            "page": 1
        }
        encoded = RequestBuilderService.encode_query_params(params)
        self.assertIn("search=running+shoes", encoded)
        self.assertIn("active=true", encoded)
        self.assertIn("category=footwear", encoded)
        self.assertIn("category=sports", encoded)
        self.assertIn("page=1", encoded)

    def test_03_merge_headers_unit(self):
        """Verify hierarchical and case-insensitive header merging."""
        project_headers = {
            "Authorization": "Bearer project-token",
            "X-Tenant-ID": "tenant-1"
        }
        endpoint_headers = {
            "Content-Type": "application/json",
            "x-tenant-id": "tenant-override"
        }
        runtime_overrides = {
            "AUTHORIZATION": "Bearer runtime-override-token",
            "X-Trace-ID": "trace-99"
        }

        merged = RequestBuilderService.merge_headers(
            project_headers=project_headers,
            endpoint_headers=endpoint_headers,
            override_headers=runtime_overrides
        )

        self.assertEqual(merged["AUTHORIZATION"], "Bearer runtime-override-token")
        self.assertEqual(merged["x-tenant-id"], "tenant-override")
        self.assertEqual(merged["Content-Type"], "application/json")
        self.assertEqual(merged["X-Trace-ID"], "trace-99")
        self.assertIn("User-Agent", merged)

    def test_04_body_serialization_unit(self):
        """Verify body serialization for JSON, Form-Data, Raw Text, and Empty."""
        headers = {"Accept": "application/json"}

        # JSON Serialization
        json_payload = {"name": "Laptop", "price": 999.99}
        raw_bytes, raw_preview, parsed, updated_headers = RequestBuilderService.serialize_body(
            body=json_payload,
            body_type=BodyType.JSON,
            headers=headers
        )
        self.assertIsInstance(raw_bytes, bytes)
        self.assertIn('"Laptop"', raw_preview)
        self.assertEqual(updated_headers["Content-Type"], "application/json")

        # Form-Data Serialization
        form_payload = {"username": "alice", "grant_type": "password"}
        f_bytes, f_preview, _, f_headers = RequestBuilderService.serialize_body(
            body=form_payload,
            body_type=BodyType.FORM_DATA,
            headers=headers
        )
        self.assertEqual(f_preview, "username=alice&grant_type=password")
        self.assertEqual(f_headers["Content-Type"], "application/x-www-form-urlencoded")

        # Raw Text Serialization
        t_bytes, t_preview, _, t_headers = RequestBuilderService.serialize_body(
            body="<xml><tag>val</tag></xml>",
            body_type=BodyType.RAW_TEXT,
            headers={"Content-Type": "application/xml"}
        )
        self.assertEqual(t_preview, "<xml><tag>val</tag></xml>")
        self.assertEqual(t_headers["Content-Type"], "application/xml")

        # Empty Body
        e_bytes, e_preview, _, _ = RequestBuilderService.serialize_body(
            body=None,
            body_type=BodyType.EMPTY,
            headers=headers
        )
        self.assertIsNone(e_bytes)
        self.assertIsNone(e_preview)

    def test_05_curl_generation_unit(self):
        """Verify cURL command generation."""
        curl = RequestBuilderService.generate_curl_command(
            method="POST",
            url="https://api.store.com/v1/orders",
            headers={"Content-Type": "application/json", "Authorization": "Bearer xyz"},
            raw_body_preview='{"item_id": 101}'
        )
        self.assertTrue(curl.startswith("curl -X POST 'https://api.store.com/v1/orders'"))
        self.assertIn("-H 'Content-Type: application/json'", curl)
        self.assertIn("-d '{\"item_id\": 101}'", curl)

    def test_06_build_endpoint_request_api_success(self):
        """Verify POST /api/v1/projects/{p_id}/endpoints/{e_id}/build-request endpoint."""
        # 1. Create project
        proj_resp = self.client.post("/api/v1/projects", json={
            "name": "Request Builder Workspace",
            "base_url": "https://api.builder.com",
            "global_headers": {"Authorization": "Bearer global-jwt"}
        })
        proj_id = proj_resp.json()["data"]["id"]

        # 2. Create endpoint
        ep_resp = self.client.post(f"/api/v1/projects/{proj_id}/endpoints", json={
            "name": "Get Inventory Item",
            "method": "GET",
            "path": "/api/v1/warehouses/{wh_id}/items/{item_id}",
            "path_params": {"wh_id": "wh-01", "item_id": "item-999"},
            "query_params": {"detailed": "true"},
            "headers": {"X-Custom": "ep-val"}
        })
        ep_id = ep_resp.json()["data"]["id"]

        # 3. Build request
        build_resp = self.client.post(f"/api/v1/projects/{proj_id}/endpoints/{ep_id}/build-request")
        self.assertEqual(build_resp.status_code, 200)
        data = build_resp.json()["data"]
        self.assertEqual(data["method"], "GET")
        self.assertEqual(data["resolved_path"], "/api/v1/warehouses/wh-01/items/item-999")
        self.assertIn("https://api.builder.com/api/v1/warehouses/wh-01/items/item-999?detailed=true", data["url"])
        self.assertEqual(data["headers"]["Authorization"], "Bearer global-jwt")
        self.assertEqual(data["headers"]["X-Custom"], "ep-val")
        self.assertIn("curl -X GET", data["curl_command"])

    def test_07_build_endpoint_request_api_with_runtime_overrides(self):
        """Verify building request with runtime parameter overrides."""
        override_payload = {
            "base_url": "https://staging.builder.com",
            "path_params": {"item_id": "item-OVERRIDE"},
            "query_params": {"page": 2},
            "headers": {"Authorization": "Bearer override-jwt"},
            "body": {"status": "dispatched"},
            "body_type": "json"
        }
        resp = self.client.post(
            "/api/v1/projects/1/endpoints/1/build-request",
            json=override_payload
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["base_url"], "https://staging.builder.com")
        self.assertEqual(data["headers"]["Authorization"], "Bearer override-jwt")
        self.assertIn("page=2", data["url"])
        self.assertEqual(data["body_type"], "json")
        self.assertEqual(data["body"]["status"], "dispatched")

    def test_08_build_endpoint_request_mismatched_project(self):
        """Verify 400 when endpoint does not belong to specified project."""
        # Create separate project
        proj2_resp = self.client.post("/api/v1/projects", json={
            "name": "Project 2",
            "base_url": "https://api.proj2.com"
        })
        proj2_id = proj2_resp.json()["data"]["id"]

        # Call with project 2 and endpoint 1 (which belongs to project 1)
        resp = self.client.post(f"/api/v1/projects/{proj2_id}/endpoints/1/build-request")
        self.assertEqual(resp.status_code, 400)

    def test_09_direct_request_builder_api(self):
        """Verify POST /api/v1/requests/build direct ad-hoc request compilation."""
        direct_payload = {
            "base_url": "https://mock-target.io",
            "method": "POST",
            "path": "/api/v2/payments/{payment_id}",
            "path_params": {"payment_id": "pay-555"},
            "query_params": {"dry_run": True},
            "headers": {"X-Secret": "sec-123"},
            "body": {"amount": 500, "currency": "USD"},
            "body_type": "json"
        }
        resp = self.client.post("/api/v1/requests/build", json=direct_payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["method"], "POST")
        self.assertEqual(data["resolved_path"], "/api/v2/payments/pay-555")
        self.assertIn("dry_run=true", data["url"])
        self.assertEqual(data["headers"]["Content-Type"], "application/json")
        self.assertEqual(data["headers"]["X-Secret"], "sec-123")
        self.assertIn("-d '{\n  \"amount\": 500", data["curl_command"])

    def test_10_direct_request_builder_missing_path_param_returns_422(self):
        """Verify 422 Unprocessable Entity when required path variable is missing."""
        invalid_payload = {
            "base_url": "https://mock-target.io",
            "method": "GET",
            "path": "/api/v2/users/{missing_id}",
            "path_params": {}  # missing_id not supplied
        }
        resp = self.client.post("/api/v1/requests/build", json=invalid_payload)
        self.assertEqual(resp.status_code, 422)


if __name__ == "__main__":
    unittest.main()
