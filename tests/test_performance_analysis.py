"""Unit and Integration Tests for Performance Analysis & SLA Benchmarking (Stage 10)."""
import unittest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.entities.endpoint import Endpoint
from app.models.entities.project import Project
from app.models.schemas.execution import ExecutionResultResponse
from app.models.schemas.performance import (
    AnalyzeLatencyBatchRequest,
    DirectBenchmarkRequest,
    EndpointBenchmarkRequest,
    LatencyBucket,
    SLAPerformanceRating,
    SLAPolicy,
)
from app.utils.performance_calculator import (
    calculate_percentile,
    classify_latency_bucket,
    compute_latency_percentiles,
    evaluate_sla_policy,
)


class TestPerformanceCalculator(unittest.TestCase):
    """Unit tests for statistical math and SLA evaluation functions."""

    def test_percentile_calculations(self):
        # 10 sorted latency values: [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
        data = [float(x) for x in range(10, 110, 10)]
        self.assertEqual(calculate_percentile(data, 0), 10.0)
        self.assertEqual(calculate_percentile(data, 50), 55.0)
        self.assertEqual(calculate_percentile(data, 90), 91.0)
        self.assertEqual(calculate_percentile(data, 95), 95.5)
        self.assertEqual(calculate_percentile(data, 99), 99.1)
        self.assertEqual(calculate_percentile(data, 100), 100.0)

    def test_latency_bucket_classification(self):
        self.assertEqual(classify_latency_bucket(50.0), LatencyBucket.FAST)
        self.assertEqual(classify_latency_bucket(199.9), LatencyBucket.FAST)
        self.assertEqual(classify_latency_bucket(200.0), LatencyBucket.ACCEPTABLE)
        self.assertEqual(classify_latency_bucket(450.0), LatencyBucket.ACCEPTABLE)
        self.assertEqual(classify_latency_bucket(500.1), LatencyBucket.SLOW)
        self.assertEqual(classify_latency_bucket(999.0), LatencyBucket.SLOW)
        self.assertEqual(classify_latency_bucket(1001.0), LatencyBucket.CRITICAL)

    def test_compute_latency_percentiles_full(self):
        latencies = [50.0, 60.0, 70.0, 80.0, 90.0, 100.0, 150.0, 250.0, 600.0, 1200.0]
        metrics = compute_latency_percentiles(latencies)

        self.assertEqual(metrics.sample_count, 10)
        self.assertEqual(metrics.min_ms, 50.0)
        self.assertEqual(metrics.max_ms, 1200.0)
        self.assertEqual(metrics.jitter_ms, 1150.0)
        self.assertTrue(metrics.p95_ms > 600.0)
        self.assertTrue(metrics.p99_ms > 1000.0)
        self.assertEqual(metrics.distribution.fast_count, 7)
        self.assertEqual(metrics.distribution.acceptable_count, 1)
        self.assertEqual(metrics.distribution.slow_count, 1)
        self.assertEqual(metrics.distribution.critical_count, 1)

    def test_sla_policy_optimal(self):
        latencies = [40.0, 45.0, 50.0, 55.0, 60.0, 65.0, 70.0, 75.0, 80.0, 85.0]
        metrics = compute_latency_percentiles(latencies)
        policy = SLAPolicy(target_p95_ms=200.0, target_p99_ms=300.0, max_acceptable_latency_ms=500.0, warn_threshold_ms=100.0)

        sla = evaluate_sla_policy(metrics, policy, total_requests=10, error_count=0)
        self.assertTrue(sla.sla_met)
        self.assertEqual(sla.rating, SLAPerformanceRating.OPTIMAL)
        self.assertEqual(sla.compliance_percentage, 100.0)
        self.assertEqual(len(sla.breaches), 0)

    def test_sla_policy_breach_detection(self):
        latencies = [100.0, 200.0, 300.0, 600.0, 800.0, 1200.0, 1800.0]
        metrics = compute_latency_percentiles(latencies)
        policy = SLAPolicy(
            target_p95_ms=500.0,  # breached (actual ~1620)
            target_p99_ms=1000.0, # breached (actual ~1764)
            max_acceptable_latency_ms=1500.0, # breached (actual 1800)
            warn_threshold_ms=400.0 # breached (mean ~714)
        )

        sla = evaluate_sla_policy(metrics, policy, total_requests=7, error_count=1)
        self.assertFalse(sla.sla_met)
        self.assertEqual(sla.rating, SLAPerformanceRating.BREACHED)
        self.assertTrue(len(sla.breaches) >= 3)
        self.assertTrue(len(sla.recommendations) > 0)


class TestPerformanceAPIIntegration(unittest.TestCase):
    """Integration tests for performance REST endpoints."""

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
        self.project = Project(name="Perf Test Workspace", base_url="https://api.example.com")
        self.db.add(self.project)
        self.db.commit()

        self.endpoint = Endpoint(
            project_id=self.project.id,
            name="Search Products",
            method="GET",
            path="/products"
        )
        self.db.add(self.endpoint)
        self.db.commit()

    def tearDown(self):
        self.db.query(Endpoint).delete()
        self.db.query(Project).delete()
        self.db.commit()
        self.db.close()

    def test_analyze_latency_batch_endpoint(self):
        payload = {
            "latencies": [45.2, 52.1, 48.0, 60.3, 55.4, 72.1, 80.0, 65.2],
            "error_count": 0,
            "sla_policy": {
                "target_p95_ms": 150.0,
                "target_p99_ms": 250.0,
                "max_acceptable_latency_ms": 500.0,
                "warn_threshold_ms": 100.0
            }
        }

        response = self.client.post("/api/v1/performance/analyze", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["total_requests"], 8)
        self.assertEqual(data["successful_requests"], 8)
        self.assertTrue(data["sla_result"]["sla_met"])
        self.assertEqual(data["sla_result"]["rating"], "OPTIMAL")
        self.assertTrue(data["metrics"]["mean_ms"] > 0)

    @patch("app.services.http_dispatcher.HttpDispatcherService.dispatch_httpx_request", new_callable=AsyncMock)
    def test_direct_benchmark_endpoint(self, mock_dispatch):
        mock_dispatch.return_value = ExecutionResultResponse(
            url="https://httpbin.org/get",
            method="GET",
            status_code=200,
            status_text="OK",
            headers={"content-type": "application/json"},
            body_raw="{}",
            body_parsed={},
            elapsed_ms=45.0
        )

        payload = {
            "base_url": "https://httpbin.org",
            "method": "GET",
            "path": "/get",
            "repetition_count": 5,
            "concurrency_limit": 1
        }

        response = self.client.post("/api/v1/performance/benchmark-direct", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["total_requests"], 5)
        self.assertEqual(data["successful_requests"], 5)
        self.assertEqual(len(data["iterations"]), 5)
        self.assertEqual(data["metrics"]["mean_ms"], 45.0)

    @patch("app.services.http_dispatcher.HttpDispatcherService.dispatch_httpx_request", new_callable=AsyncMock)
    def test_endpoint_benchmark_endpoint(self, mock_dispatch):
        mock_dispatch.return_value = ExecutionResultResponse(
            url="https://api.example.com/products",
            method="GET",
            status_code=200,
            status_text="OK",
            headers={"content-type": "application/json"},
            body_raw="[]",
            body_parsed=[],
            elapsed_ms=62.5
        )

        payload = {
            "repetition_count": 4,
            "concurrency_limit": 2
        }

        response = self.client.post(f"/api/v1/performance/endpoints/{self.endpoint.id}/benchmark", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["total_requests"], 4)
        self.assertEqual(data["metrics"]["sample_count"], 4)
        self.assertTrue(data["sla_result"]["sla_met"])


if __name__ == "__main__":
    unittest.main()