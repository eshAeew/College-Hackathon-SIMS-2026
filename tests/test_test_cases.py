"""Unit & Integration tests for TestCase Management & Scenario CRUD."""
import unittest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core.database import Base, get_db
from app.models.entities.project import Project
from app.models.entities.endpoint import Endpoint
from app.models.entities.test_case import TestCase
from app.models.schemas.test_case import TestCaseSeverity

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


class TestTestCaseManagement(unittest.TestCase):
    """Test suite verifying TestCase CRUD, filtering by tag/severity, cloning, and cascade deletion."""

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
        self.db = TestingSessionLocal()

        # Seed Project and Endpoint
        self.project = Project(
            name="TestCase Workspace",
            base_url="https://api.testcases.com"
        )
        self.db.add(self.project)
        self.db.commit()
        self.db.refresh(self.project)

        self.endpoint = Endpoint(
            project_id=self.project.id,
            name="Create User Order",
            method="POST",
            path="/api/v1/users/{user_id}/orders"
        )
        self.db.add(self.endpoint)
        self.db.commit()
        self.db.refresh(self.endpoint)

    def tearDown(self):
        self.db.close()

    def test_01_create_test_case_success(self):
        """Verify creating a functional test case under an endpoint."""
        response = self.client.post(
            f"/api/v1/endpoints/{self.endpoint.id}/test-cases",
            json={
                "name": "Standard Checkout - Valid Credit Card",
                "description": "Verifies successful order creation with valid Visa card",
                "severity": "critical",
                "tags": ["smoke", "checkout", "payments"],
                "path_params": {"user_id": "usr-889"},
                "query_params": {"coupon": "WELCOME10"},
                "headers": {"Authorization": "Bearer test-jwt-token"},
                "body_type": "json",
                "body": {
                    "items": [{"sku": "SKU-A", "qty": 1}],
                    "payment_method": "credit_card"
                },
                "assertions": {
                    "expected_status": 201,
                    "max_latency_ms": 1000
                }
            }
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()["data"]
        self.assertEqual(data["name"], "Standard Checkout - Valid Credit Card")
        self.assertEqual(data["endpoint_id"], self.endpoint.id)
        self.assertEqual(data["severity"], "critical")
        self.assertIn("smoke", data["tags"])
        self.assertEqual(data["path_params"], {"user_id": "usr-889"})
        self.assertEqual(data["body"]["payment_method"], "credit_card")
        self.assertTrue(data["is_active"])

    def test_02_create_test_case_nonexistent_endpoint(self):
        """Verify creating a test case under non-existent endpoint returns 404."""
        response = self.client.post(
            "/api/v1/endpoints/99999/test-cases",
            json={"name": "Orphan Test Case"}
        )
        self.assertEqual(response.status_code, 404)

    def test_03_list_and_filter_by_tags(self):
        """Verify listing test cases and filtering by specific tag."""
        # Create test case 1 (smoke, regression)
        self.client.post(
            f"/api/v1/endpoints/{self.endpoint.id}/test-cases",
            json={"name": "Smoke Scenario", "tags": ["smoke", "regression"]}
        )
        # Create test case 2 (security)
        self.client.post(
            f"/api/v1/endpoints/{self.endpoint.id}/test-cases",
            json={"name": "SQL Injection Probe", "tags": ["security", "negative"]}
        )

        # Filter by smoke
        smoke_resp = self.client.get(f"/api/v1/endpoints/{self.endpoint.id}/test-cases?tag=smoke")
        self.assertEqual(smoke_resp.status_code, 200)
        smoke_items = smoke_resp.json()["data"]
        self.assertTrue(any(tc["name"] == "Smoke Scenario" for tc in smoke_items))
        self.assertFalse(any(tc["name"] == "SQL Injection Probe" for tc in smoke_items))

        # Filter by security
        sec_resp = self.client.get(f"/api/v1/endpoints/{self.endpoint.id}/test-cases?tag=security")
        self.assertEqual(sec_resp.status_code, 200)
        sec_items = sec_resp.json()["data"]
        self.assertTrue(any(tc["name"] == "SQL Injection Probe" for tc in sec_items))
        self.assertFalse(any(tc["name"] == "Smoke Scenario" for tc in sec_items))

    def test_04_list_and_filter_by_severity(self):
        """Verify filtering test cases by severity level."""
        self.client.post(
            f"/api/v1/endpoints/{self.endpoint.id}/test-cases",
            json={"name": "Critical Flow", "severity": "critical"}
        )
        self.client.post(
            f"/api/v1/endpoints/{self.endpoint.id}/test-cases",
            json={"name": "Low Priority Edge Case", "severity": "low"}
        )

        resp = self.client.get(f"/api/v1/endpoints/{self.endpoint.id}/test-cases?severity=critical")
        self.assertEqual(resp.status_code, 200)
        items = resp.json()["data"]
        self.assertTrue(all(tc["severity"] == "critical" for tc in items))

    def test_05_get_and_update_test_case(self):
        """Verify retrieving single test case and partial update."""
        create_resp = self.client.post(
            f"/api/v1/endpoints/{self.endpoint.id}/test-cases",
            json={"name": "To Be Updated", "severity": "low"}
        )
        tc_id = create_resp.json()["data"]["id"]

        # Get details
        get_resp = self.client.get(f"/api/v1/test-cases/{tc_id}")
        self.assertEqual(get_resp.status_code, 200)
        self.assertEqual(get_resp.json()["data"]["name"], "To Be Updated")

        # Update
        update_resp = self.client.put(
            f"/api/v1/test-cases/{tc_id}",
            json={
                "name": "Updated Name Successfully",
                "severity": "high",
                "tags": ["updated", "p0"],
                "body": {"updated": True}
            }
        )
        self.assertEqual(update_resp.status_code, 200)
        data = update_resp.json()["data"]
        self.assertEqual(data["name"], "Updated Name Successfully")
        self.assertEqual(data["severity"], "high")
        self.assertEqual(data["tags"], ["updated", "p0"])
        self.assertEqual(data["body"], {"updated": True})

    def test_06_toggle_active_state(self):
        """Verify toggling active status on a test case."""
        create_resp = self.client.post(
            f"/api/v1/endpoints/{self.endpoint.id}/test-cases",
            json={"name": "Toggle Active Scenario", "is_active": True}
        )
        tc_id = create_resp.json()["data"]["id"]

        # Toggle to disabled
        t1 = self.client.patch(f"/api/v1/test-cases/{tc_id}/toggle-active")
        self.assertEqual(t1.status_code, 200)
        self.assertFalse(t1.json()["data"]["is_active"])

        # Toggle back to enabled
        t2 = self.client.patch(f"/api/v1/test-cases/{tc_id}/toggle-active")
        self.assertEqual(t2.status_code, 200)
        self.assertTrue(t2.json()["data"]["is_active"])

    def test_07_duplicate_test_case(self):
        """Verify duplicating an existing test case."""
        create_resp = self.client.post(
            f"/api/v1/endpoints/{self.endpoint.id}/test-cases",
            json={
                "name": "Original Test Case",
                "tags": ["smoke"],
                "body": {"amount": 100}
            }
        )
        tc_id = create_resp.json()["data"]["id"]

        # Duplicate with default name
        dup1 = self.client.post(f"/api/v1/test-cases/{tc_id}/duplicate", json={})
        self.assertEqual(dup1.status_code, 201)
        self.assertEqual(dup1.json()["data"]["name"], "Original Test Case (Copy)")
        self.assertEqual(dup1.json()["data"]["body"], {"amount": 100})

        # Duplicate with custom name
        dup2 = self.client.post(
            f"/api/v1/test-cases/{tc_id}/duplicate",
            json={"name": "Cloned with Custom Name"}
        )
        self.assertEqual(dup2.status_code, 201)
        self.assertEqual(dup2.json()["data"]["name"], "Cloned with Custom Name")

    def test_08_delete_test_case(self):
        """Verify deleting a test case."""
        create_resp = self.client.post(
            f"/api/v1/endpoints/{self.endpoint.id}/test-cases",
            json={"name": "Delete Me"}
        )
        tc_id = create_resp.json()["data"]["id"]

        del_resp = self.client.delete(f"/api/v1/test-cases/{tc_id}")
        self.assertEqual(del_resp.status_code, 200)

        # Verify 404
        get_resp = self.client.get(f"/api/v1/test-cases/{tc_id}")
        self.assertEqual(get_resp.status_code, 404)

    def test_09_cascade_deletion_on_endpoint_delete(self):
        """Verify that deleting an endpoint cascades and removes all associated test cases."""
        # Create dedicated endpoint
        ep_resp = self.client.post(
            f"/api/v1/projects/{self.project.id}/endpoints",
            json={"name": "Temp Endpoint", "method": "GET", "path": "/temp"}
        )
        temp_ep_id = ep_resp.json()["data"]["id"]

        # Create 2 test cases under this endpoint
        tc1 = self.client.post(
            f"/api/v1/endpoints/{temp_ep_id}/test-cases",
            json={"name": "Temp TC 1"}
        ).json()["data"]["id"]

        tc2 = self.client.post(
            f"/api/v1/endpoints/{temp_ep_id}/test-cases",
            json={"name": "Temp TC 2"}
        ).json()["data"]["id"]

        # Delete endpoint
        del_ep = self.client.delete(f"/api/v1/endpoints/{temp_ep_id}")
        self.assertEqual(del_ep.status_code, 200)

        # Verify test cases are gone
        self.assertEqual(self.client.get(f"/api/v1/test-cases/{tc1}").status_code, 404)
        self.assertEqual(self.client.get(f"/api/v1/test-cases/{tc2}").status_code, 404)


if __name__ == "__main__":
    unittest.main()
