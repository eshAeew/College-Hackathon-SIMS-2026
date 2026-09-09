"""Tests for FastAPI application scaffolding and health check using unittest."""
import unittest
from fastapi.testclient import TestClient
from app.main import app


class TestAppScaffolding(unittest.TestCase):
    """Test suite verifying app entry point and endpoints."""

    def setUp(self):
        self.client = TestClient(app)

    def test_root_endpoint(self):
        """Verify root / returns 200 and project identity."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "API Sentinel")
        self.assertIn("version", data)
        self.assertEqual(data["status"], "active")
        self.assertEqual(data["documentation"], "/docs")

    def test_health_check_endpoint(self):
        """Verify /api/v1/health returns standardized health payload."""
        response = self.client.get("/api/v1/health")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["status"], "healthy")
        self.assertIn("version", payload["data"])
        self.assertIn("database", payload["data"])
        self.assertIn("timestamp", payload)

    def test_openapi_docs_available(self):
        """Verify Swagger UI and OpenAPI JSON schemas are accessible."""
        openapi_resp = self.client.get("/openapi.json")
        self.assertEqual(openapi_resp.status_code, 200)
        openapi_json = openapi_resp.json()
        self.assertEqual(openapi_json["info"]["title"], "API Sentinel")

    def test_redoc_endpoint_available(self):
        """Verify /redoc returns 200 and contains the modern Redocly bundle."""
        redoc_resp = self.client.get("/redoc")
        self.assertEqual(redoc_resp.status_code, 200)
        self.assertIn("cdn.redoc.ly", redoc_resp.text)


if __name__ == "__main__":
    unittest.main()
