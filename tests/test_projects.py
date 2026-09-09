"""Unit & Integration tests for Project CRUD operations and Workspace Summary statistics."""
import unittest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core.database import Base, get_db
from app.models.entities.project import Project

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


class TestProjectCRUD(unittest.TestCase):
    """Test suite verifying full lifecycle of Project / Workspace management."""

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

    def test_01_create_project_success(self):
        """Verify successful project creation."""
        payload = {
            "name": "E-Commerce Mock API",
            "description": "Mock store API for testing",
            "base_url": "http://localhost:8001",
            "environment": "development",
            "global_headers": {"Authorization": "Bearer test-token-123"}
        }
        response = self.client.post("/api/v1/projects", json=payload)
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertTrue(data["success"])
        project = data["data"]
        self.assertEqual(project["name"], "E-Commerce Mock API")
        self.assertEqual(project["base_url"], "http://localhost:8001")
        self.assertEqual(project["global_headers"]["Authorization"], "Bearer test-token-123")
        self.assertIn("id", project)

    def test_02_create_project_invalid_base_url(self):
        """Verify project creation fails if base_url is invalid."""
        payload = {
            "name": "Invalid Project",
            "base_url": "ftp://invalid-url"
        }
        response = self.client.post("/api/v1/projects", json=payload)
        self.assertEqual(response.status_code, 422)

    def test_03_list_projects(self):
        """Verify listing all registered projects."""
        response = self.client.get("/api/v1/projects")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertTrue(len(data["data"]) >= 1)

    def test_04_get_project_by_id_success(self):
        """Verify retrieving specific project details."""
        response = self.client.get("/api/v1/projects/1")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["data"]["id"], 1)
        self.assertEqual(data["data"]["name"], "E-Commerce Mock API")

    def test_05_get_project_by_id_not_found(self):
        """Verify 404 response for non-existent project."""
        response = self.client.get("/api/v1/projects/9999")
        self.assertEqual(response.status_code, 404)

    def test_06_get_project_summary_success(self):
        """Verify project summary statistics endpoint."""
        response = self.client.get("/api/v1/projects/1/summary")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        summary = payload["data"]
        self.assertEqual(summary["project_id"], 1)
        self.assertEqual(summary["project_name"], "E-Commerce Mock API")
        self.assertEqual(summary["base_url"], "http://localhost:8001")
        self.assertEqual(summary["total_endpoints"], 0)
        self.assertEqual(summary["health_score"], 100.0)
        self.assertEqual(summary["global_headers_count"], 1)
        self.assertTrue(summary["has_auth_header"])
        self.assertTrue(len(summary["environment_presets"]) >= 3)

    def test_07_get_project_summary_not_found(self):
        """Verify 404 on summary for non-existent project."""
        response = self.client.get("/api/v1/projects/9999/summary")
        self.assertEqual(response.status_code, 404)

    def test_08_update_project_success(self):
        """Verify updating existing project attributes."""
        update_payload = {
            "name": "Updated E-Commerce API",
            "base_url": "https://api.staging.store.com",
            "global_headers": {"X-Custom-Key": "secret-val"}
        }
        response = self.client.put("/api/v1/projects/1", json=update_payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["data"]["name"], "Updated E-Commerce API")
        self.assertEqual(data["data"]["base_url"], "https://api.staging.store.com")
        self.assertEqual(data["data"]["global_headers"]["X-Custom-Key"], "secret-val")

    def test_09_delete_project_success(self):
        """Verify project deletion and subsequent 404."""
        create_resp = self.client.post("/api/v1/projects", json={
            "name": "To Delete",
            "base_url": "http://localhost:5000"
        })
        del_id = create_resp.json()["data"]["id"]

        del_resp = self.client.delete(f"/api/v1/projects/{del_id}")
        self.assertEqual(del_resp.status_code, 200)

        fetch_resp = self.client.get(f"/api/v1/projects/{del_id}")
        self.assertEqual(fetch_resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
