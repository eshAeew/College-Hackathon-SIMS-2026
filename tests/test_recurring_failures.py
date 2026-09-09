"""Unit and Integration Tests for Recurring Failure Detection & Pattern Clustering (Stage 11)."""
import unittest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.entities.endpoint import Endpoint
from app.models.entities.project import Project
from app.models.schemas.recurring_failure import (
    AnalyzeHistoricalFailuresRequest,
    FailureCategory,
    HistoricalExecutionSample,
    PersistenceRating,
)
from app.utils.failure_fingerprinter import (
    calculate_persistence_rating,
    categorize_failure,
    cluster_failure_samples,
    generate_failure_fingerprint,
    normalize_error_message,
)


class TestFailureFingerprinting(unittest.TestCase):
    """Unit tests for error normalization, categorization, persistence grading, and clustering."""

    def test_normalize_error_message(self):
        raw_trace = "Connection failed at 2026-09-09T18:30:00.000Z for session 123e4567-e89b-12d3-a456-426614174000 at pointer 0x7ffd5a89b4c0"
        normalized = normalize_error_message(raw_trace)
        self.assertNotIn("2026-09-09", normalized)
        self.assertNotIn("123e4567", normalized)
        self.assertNotIn("0x7ffd5a", normalized)
        self.assertIn("<TIMESTAMP>", normalized)
        self.assertIn("<UUID>", normalized)
        self.assertIn("<HEX_ADDR>", normalized)

    def test_categorize_failures(self):
        self.assertEqual(categorize_failure(500, "Internal Server Error"), FailureCategory.SERVER_CRASH)
        self.assertEqual(categorize_failure(401, "Invalid Bearer Token"), FailureCategory.AUTH_FAILURE)
        self.assertEqual(categorize_failure(422, "Field 'email' missing"), FailureCategory.VALIDATION_ERROR)
        self.assertEqual(categorize_failure(504, "Gateway Timeout"), FailureCategory.TIMEOUT)
        self.assertEqual(categorize_failure(200, None, ["Field 'price' is not float"]), FailureCategory.ASSERTION_FAILED)
        self.assertEqual(categorize_failure(None, "ConnectError: Connection refused"), FailureCategory.NETWORK_ERROR)

    def test_generate_failure_fingerprint_stability(self):
        msg1 = "Database connection timed out for user <NUM_ID>"
        msg2 = "Database connection timed out for user <NUM_ID>"
        cid1, fp1 = generate_failure_fingerprint(FailureCategory.TIMEOUT, 504, msg1)
        cid2, fp2 = generate_failure_fingerprint(FailureCategory.TIMEOUT, 504, msg2)
        self.assertEqual(cid1, cid2)
        self.assertEqual(fp1, fp2)

    def test_calculate_persistence_rating_chronic(self):
        # 5 consecutive failures
        history = [False, False, False, False, False]
        rating, consec, rate, flapping = calculate_persistence_rating(history)
        self.assertEqual(rating, PersistenceRating.CHRONIC)
        self.assertEqual(consec, 5)
        self.assertEqual(rate, 100.0)
        self.assertFalse(flapping)

    def test_calculate_persistence_rating_intermittent_flapping(self):
        # Flapping pattern: pass, fail, pass, fail, pass, fail
        history = [True, False, True, False, True, False]
        rating, consec, rate, flapping = calculate_persistence_rating(history)
        self.assertEqual(rating, PersistenceRating.INTERMITTENT)
        self.assertTrue(flapping)
        self.assertEqual(consec, 1)
        self.assertEqual(rate, 50.0)

    def test_calculate_persistence_rating_resolved(self):
        # Previously failed, but latest runs passed
        history = [False, False, True, True]
        rating, consec, rate, flapping = calculate_persistence_rating(history)
        self.assertEqual(rating, PersistenceRating.RESOLVED)
        self.assertEqual(consec, 0)

    def test_cluster_failure_samples(self):
        samples = [
            HistoricalExecutionSample(endpoint_id=1, passed=False, status_code=500, error_message="DB pool exhausted at pointer 0x100"),
            HistoricalExecutionSample(endpoint_id=2, passed=False, status_code=500, error_message="DB pool exhausted at pointer 0x200"),
            HistoricalExecutionSample(endpoint_id=1, passed=False, status_code=401, error_message="Expired JWT token"),
            HistoricalExecutionSample(endpoint_id=3, passed=True, status_code=200)
        ]

        clusters = cluster_failure_samples(samples)
        self.assertEqual(len(clusters), 2)
        
        # The DB pool exhausted cluster should combine endpoint 1 and 2
        db_cluster = next(c for c in clusters if c.category == FailureCategory.SERVER_CRASH)
        self.assertEqual(db_cluster.occurrence_count, 2)
        self.assertIn(1, db_cluster.affected_endpoint_ids)
        self.assertIn(2, db_cluster.affected_endpoint_ids)


class TestRecurringFailureAPIIntegration(unittest.TestCase):
    """Integration tests for recurring failure REST routes."""

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
        self.project = Project(name="Failure Analysis Test Workspace", base_url="https://api.example.com")
        self.db.add(self.project)
        self.db.commit()

        self.endpoint1 = Endpoint(project_id=self.project.id, name="Checkout API", method="POST", path="/checkout")
        self.endpoint2 = Endpoint(project_id=self.project.id, name="User Profile", method="GET", path="/users/{id}")
        self.db.add_all([self.endpoint1, self.endpoint2])
        self.db.commit()

    def tearDown(self):
        self.db.query(Endpoint).delete()
        self.db.query(Project).delete()
        self.db.commit()
        self.db.close()

    def test_analyze_batch_historical_failures_endpoint(self):
        payload = {
            "samples": [
                {"endpoint_id": self.endpoint1.id, "passed": False, "status_code": 500, "error_message": "Database deadlock detected"},
                {"endpoint_id": self.endpoint1.id, "passed": False, "status_code": 500, "error_message": "Database deadlock detected"},
                {"endpoint_id": self.endpoint1.id, "passed": False, "status_code": 500, "error_message": "Database deadlock detected"},
                {"endpoint_id": self.endpoint2.id, "passed": True, "status_code": 200},
                {"endpoint_id": self.endpoint2.id, "passed": False, "status_code": 401, "error_message": "Invalid auth token"},
                {"endpoint_id": self.endpoint2.id, "passed": True, "status_code": 200}
            ],
            "project_name": "E-Commerce Checkout",
            "window_size": 10
        }

        response = self.client.post("/api/v1/recurring-failures/analyze", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["total_analyzed_runs"], 6)
        self.assertEqual(data["total_endpoints"], 2)
        self.assertEqual(data["chronic_failure_count"], 1)  # endpoint 1 is chronic
        self.assertTrue(len(data["failure_clusters"]) >= 2)

    def test_get_project_recurring_failures_endpoint(self):
        response = self.client.get(f"/api/v1/recurring-failures/projects/{self.project.id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["project_id"], self.project.id)
        self.assertTrue(data["total_endpoints"] >= 2)

    def test_get_single_endpoint_recurrence(self):
        response = self.client.get(f"/api/v1/recurring-failures/endpoints/{self.endpoint1.id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["endpoint_id"], self.endpoint1.id)
        self.assertEqual(data["persistence_rating"], "HEALTHY")


if __name__ == "__main__":
    unittest.main()