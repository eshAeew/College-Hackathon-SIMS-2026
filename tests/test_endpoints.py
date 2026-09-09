"""Unit & Integration tests for Endpoint Registration, CRUD, Duplication, and Validation."""
import unittest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core.database import Base, get_db

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


class TestEndpointCRUD(unittest.TestCase):
    """Comprehensive test suite for Endpoint management."""

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

    def test_01_create_endpoint_success(self):
        """Verify endpoint registration under a project."""
        # 1. Create a parent project
        proj_resp = self.client.post("/api/v1/projects", json={
            "name": "E-Store API",
            "base_url": "https://api.store.com",
            "environment": "development"
        })
        self.assertEqual(proj_resp.status_code, 201)
        project_id = proj_resp.json()["data"]["id"]

        # 2. Register an endpoint
        payload = {
            "name": "Create Order",
            "description": "Submit a new customer order",
            "method": "POST",
            "path": "/api/v1/orders",
            "expected_status": 201,
            "is_active": True,
            "headers": {"Content-Type": "application/json"},
            "query_params": {"notify": "true"},
            "path_params": {},
            "body_schema": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "integer"},
                    "quantity": {"type": "integer"}
                },
                "required": ["item_id", "quantity"]
            }
        }
        resp = self.client.post(f"/api/v1/projects/{project_id}/endpoints", json=payload)
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertTrue(data["success"])
        endpoint = data["data"]
        self.assertEqual(endpoint["name"], "Create Order")
        self.assertEqual(endpoint["method"], "POST")
        self.assertEqual(endpoint["path"], "/api/v1/orders")
        self.assertEqual(endpoint["expected_status"], 201)
        self.assertEqual(endpoint["project_id"], project_id)
        self.assertEqual(endpoint["headers"]["Content-Type"], "application/json")
        self.assertEqual(endpoint["query_params"]["notify"], "true")
        self.assertIn("required", endpoint["body_schema"])

    def test_02_create_endpoint_invalid_project(self):
        """Verify 404 when registering endpoint under non-existent project."""
        payload = {
            "name": "Orphan Endpoint",
            "method": "GET",
            "path": "/api/v1/orphan"
        }
        resp = self.client.post("/api/v1/projects/99999/endpoints", json=payload)
        self.assertEqual(resp.status_code, 404)

    def test_03_create_endpoint_path_validation(self):
        """Verify validation error when path does not start with leading slash."""
        payload = {
            "name": "Invalid Path",
            "method": "GET",
            "path": "api/v1/no-leading-slash"
        }
        resp = self.client.post("/api/v1/projects/1/endpoints", json=payload)
        self.assertEqual(resp.status_code, 422)

    def test_04_create_endpoint_blank_name_validation(self):
        """Verify validation error when endpoint name is blank."""
        payload = {
            "name": "   ",
            "method": "GET",
            "path": "/api/v1/valid"
        }
        resp = self.client.post("/api/v1/projects/1/endpoints", json=payload)
        self.assertEqual(resp.status_code, 422)

    def test_05_create_endpoint_invalid_http_method(self):
        """Verify validation error when HTTP method is invalid."""
        payload = {
            "name": "Invalid Method",
            "method": "CONNECT_INVALID",
            "path": "/api/v1/valid"
        }
        resp = self.client.post("/api/v1/projects/1/endpoints", json=payload)
        self.assertEqual(resp.status_code, 422)

    def test_06_list_endpoints_for_project(self):
        """Verify listing endpoints for a project."""
        resp = self.client.get("/api/v1/projects/1/endpoints")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertIsInstance(data["data"], list)
        self.assertTrue(len(data["data"]) >= 1)

    def test_07_list_endpoints_for_non_existent_project(self):
        """Verify 404 when listing endpoints for non-existent project."""
        resp = self.client.get("/api/v1/projects/99999/endpoints")
        self.assertEqual(resp.status_code, 404)

    def test_08_get_endpoint_by_id_success_and_not_found(self):
        """Verify retrieving specific endpoint by ID and 404 for non-existent."""
        resp = self.client.get("/api/v1/endpoints/1")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["id"], 1)

        resp_404 = self.client.get("/api/v1/endpoints/99999")
        self.assertEqual(resp_404.status_code, 404)

    def test_09_update_endpoint(self):
        """Verify updating endpoint configuration."""
        update_payload = {
            "name": "Updated Create Order",
            "method": "PUT",
            "path": "/api/v1/orders/{order_id}",
            "expected_status": 200,
            "path_params": {"order_id": "123"},
            "headers": {"X-Custom-Header": "custom-val"}
        }
        resp = self.client.put("/api/v1/endpoints/1", json=update_payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["name"], "Updated Create Order")
        self.assertEqual(data["method"], "PUT")
        self.assertEqual(data["path"], "/api/v1/orders/{order_id}")
        self.assertEqual(data["expected_status"], 200)
        self.assertEqual(data["path_params"]["order_id"], "123")
        self.assertEqual(data["headers"]["X-Custom-Header"], "custom-val")

    def test_10_duplicate_endpoint(self):
        """Verify duplicating an endpoint."""
        # 1. Duplicate with default generated name
        resp_dup1 = self.client.post("/api/v1/endpoints/1/duplicate")
        self.assertEqual(resp_dup1.status_code, 201)
        cloned1 = resp_dup1.json()["data"]
        self.assertNotEqual(cloned1["id"], 1)
        self.assertEqual(cloned1["name"], "[Copy] Updated Create Order")
        self.assertEqual(cloned1["path"], "/api/v1/orders/{order_id}")

        # 2. Duplicate with custom name
        resp_dup2 = self.client.post("/api/v1/endpoints/1/duplicate", json={"name": "Cloned Order Endpoint"})
        self.assertEqual(resp_dup2.status_code, 201)
        cloned2 = resp_dup2.json()["data"]
        self.assertEqual(cloned2["name"], "Cloned Order Endpoint")

    def test_11_toggle_endpoint_active(self):
        """Verify toggling active status of endpoint."""
        # Check initial status (True)
        resp1 = self.client.get("/api/v1/endpoints/1")
        self.assertTrue(resp1.json()["data"]["is_active"])

        # Toggle to False
        resp2 = self.client.patch("/api/v1/endpoints/1/toggle-active")
        self.assertEqual(resp2.status_code, 200)
        self.assertFalse(resp2.json()["data"]["is_active"])

        # Filter query ?is_active=false
        filter_resp = self.client.get("/api/v1/projects/1/endpoints?is_active=false")
        self.assertEqual(filter_resp.status_code, 200)
        inactive_ids = [ep["id"] for ep in filter_resp.json()["data"]]
        self.assertIn(1, inactive_ids)

        # Toggle back to True
        resp3 = self.client.patch("/api/v1/endpoints/1/toggle-active")
        self.assertEqual(resp3.status_code, 200)
        self.assertTrue(resp3.json()["data"]["is_active"])

    def test_12_delete_endpoint(self):
        """Verify deleting an endpoint."""
        # Create temporary endpoint to delete
        create_resp = self.client.post("/api/v1/projects/1/endpoints", json={
            "name": "Endpoint To Delete",
            "method": "DELETE",
            "path": "/api/v1/temp"
        })
        ep_id = create_resp.json()["data"]["id"]

        del_resp = self.client.delete(f"/api/v1/endpoints/{ep_id}")
        self.assertEqual(del_resp.status_code, 200)

        get_resp = self.client.get(f"/api/v1/endpoints/{ep_id}")
        self.assertEqual(get_resp.status_code, 404)

    def test_13_cascade_delete_with_project(self):
        """Verify deleting a project automatically cascade-deletes all its endpoints."""
        proj_resp = self.client.post("/api/v1/projects", json={
            "name": "Project for Cascade Test",
            "base_url": "https://api.temp.com"
        })
        temp_proj_id = proj_resp.json()["data"]["id"]

        ep1 = self.client.post(f"/api/v1/projects/{temp_proj_id}/endpoints", json={
            "name": "Temp EP 1",
            "path": "/ep1"
        }).json()["data"]["id"]

        ep2 = self.client.post(f"/api/v1/projects/{temp_proj_id}/endpoints", json={
            "name": "Temp EP 2",
            "path": "/ep2"
        }).json()["data"]["id"]

        # Delete project
        del_proj = self.client.delete(f"/api/v1/projects/{temp_proj_id}")
        self.assertEqual(del_proj.status_code, 200)

        # Verify child endpoints are gone
        self.assertEqual(self.client.get(f"/api/v1/endpoints/{ep1}").status_code, 404)
        self.assertEqual(self.client.get(f"/api/v1/endpoints/{ep2}").status_code, 404)

    def test_14_project_summary_reflects_endpoint_count(self):
        """Verify project summary returns dynamic count of registered endpoints."""
        proj_resp = self.client.post("/api/v1/projects", json={
            "name": "Summary Count Test Project",
            "base_url": "https://api.count.com"
        })
        proj_id = proj_resp.json()["data"]["id"]

        # Initial count is 0
        sum1 = self.client.get(f"/api/v1/projects/{proj_id}/summary").json()["data"]
        self.assertEqual(sum1["total_endpoints"], 0)

        # Add 3 endpoints
        for i in range(3):
            self.client.post(f"/api/v1/projects/{proj_id}/endpoints", json={
                "name": f"Endpoint {i}",
                "path": f"/endpoint/{i}"
            })

        sum2 = self.client.get(f"/api/v1/projects/{proj_id}/summary").json()["data"]
        self.assertEqual(sum2["total_endpoints"], 3)


if __name__ == "__main__":
    unittest.main()
