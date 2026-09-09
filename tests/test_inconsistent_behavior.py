"""Tests for Inconsistent Behavior & Flakiness Detection Engine (Stage 09)."""
import unittest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.core.database import Base, engine, SessionLocal
from app.models.entities.project import Project
from app.models.entities.endpoint import Endpoint
from app.models.schemas.execution import ExecutionResultResponse
from app.models.schemas.inconsistent_behavior import (
    ExecutionMode,
    FlakinessVerdict,
    ExecutionIterationResult,
    MultiExecutionRequest,
    EndpointMultiExecutionRequest,
    AnalyzeBatchRequest,
)
from app.utils.statistics_calculator import (
    compute_latency_stats,
    compute_status_entropy,
    compute_payload_hashes,
    evaluate_flakiness,
)
from app.services.inconsistency_service import InconsistencyService


class TestStatisticsCalculator(unittest.TestCase):
    """Unit tests for statistical math, entropy, and flakiness calculations."""

    def test_latency_statistics_calculation(self):
        latencies = [10.0, 20.0, 30.0, 40.0, 50.0]
        stats = compute_latency_stats(latencies)
        self.assertEqual(stats["min_latency_ms"], 10.0)
        self.assertEqual(stats["max_latency_ms"], 50.0)
        self.assertEqual(stats["mean_latency_ms"], 30.0)
        self.assertEqual(stats["median_latency_ms"], 30.0)
        self.assertEqual(stats["jitter_ms"], 40.0)
        self.assertGreater(stats["std_dev_latency_ms"], 0.0)
        self.assertGreater(stats["p95_latency_ms"], 40.0)
        self.assertGreater(stats["p99_latency_ms"], 40.0)

    def test_latency_statistics_single_and_empty(self):
        empty_stats = compute_latency_stats([])
        self.assertEqual(empty_stats["mean_latency_ms"], 0.0)

        single_stats = compute_latency_stats([25.4])
        self.assertEqual(single_stats["min_latency_ms"], 25.4)
        self.assertEqual(single_stats["max_latency_ms"], 25.4)
        self.assertEqual(single_stats["mean_latency_ms"], 25.4)
        self.assertEqual(single_stats["std_dev_latency_ms"], 0.0)

    def test_status_entropy_deterministic(self):
        # 10 runs of HTTP 200
        codes = [200] * 10
        entropy_res = compute_status_entropy(codes)
        self.assertTrue(entropy_res["is_status_consistent"])
        self.assertEqual(entropy_res["distinct_status_codes_count"], 1)
        self.assertEqual(entropy_res["shannon_entropy"], 0.0)
        self.assertEqual(len(entropy_res["status_transitions"]), 9)
        self.assertTrue(all(t == "200 -> 200" for t in entropy_res["status_transitions"]))

    def test_status_entropy_flaky(self):
        # 5 runs of 200, 5 runs of 500
        codes = [200, 200, 500, 200, 500, 200, 200, 500, 500, 200]
        entropy_res = compute_status_entropy(codes)
        self.assertFalse(entropy_res["is_status_consistent"])
        self.assertEqual(entropy_res["distinct_status_codes_count"], 2)
        self.assertGreater(entropy_res["shannon_entropy"], 0.0)
        self.assertIn("200 -> 500", entropy_res["status_transitions"])
        self.assertIn("500 -> 200", entropy_res["status_transitions"])

    def test_payload_hashes_and_drift(self):
        # Identical payloads
        bodies = [{"id": 1, "name": "Item"}, {"name": "Item", "id": 1}, {"id": 1, "name": "Item"}]
        res_ok = compute_payload_hashes(bodies)
        self.assertTrue(res_ok["is_payload_consistent"])
        self.assertFalse(res_ok["payload_drift_detected"])
        self.assertEqual(res_ok["distinct_payload_hashes_count"], 1)

        # Shifting / drifting payloads
        bodies_drift = [{"id": 1, "status": "pending"}, {"id": 1, "status": "processing"}, {"id": 1, "status": "completed"}]
        res_drift = compute_payload_hashes(bodies_drift)
        self.assertFalse(res_drift["is_payload_consistent"])
        self.assertTrue(res_drift["payload_drift_detected"])
        self.assertEqual(res_drift["distinct_payload_hashes_count"], 3)

    def test_flakiness_scoring_verdicts(self):
        # Perfect run
        score, verdict, findings, recs = evaluate_flakiness(
            total_runs=10,
            status_analysis={"shannon_entropy": 0.0, "distinct_status_codes_count": 1},
            latency_stats={"min_latency_ms": 10.0, "max_latency_ms": 15.0, "coefficient_of_variation_percent": 12.0, "jitter_ms": 5.0},
            payload_analysis={"payload_drift_detected": False, "distinct_payload_hashes_count": 1}
        )
        self.assertEqual(score, 0.0)
        self.assertEqual(verdict, "DETERMINISTIC_PASS")

        # Severe status switching
        score_bad, verdict_bad, findings_bad, recs_bad = evaluate_flakiness(
            total_runs=10,
            status_analysis={"shannon_entropy": 1.0, "distinct_status_codes_count": 2, "status_code_distribution": {200: 5, 503: 5}},
            latency_stats={"min_latency_ms": 10.0, "max_latency_ms": 800.0, "coefficient_of_variation_percent": 120.0, "jitter_ms": 790.0},
            payload_analysis={"payload_drift_detected": True, "distinct_payload_hashes_count": 2}
        )
        self.assertGreaterEqual(score_bad, 60.0)
        self.assertEqual(verdict_bad, "CRITICAL_INTERMITTENT_FAILURE")
        self.assertGreater(len(recs_bad), 0)


class TestInconsistencyServiceAndAPI(unittest.TestCase):
    """Integration tests for Inconsistency Service and REST API routes."""

    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)
        cls.db: Session = SessionLocal()
        cls.client = TestClient(app)

        cls.project = Project(
            name="Inconsistency Test Project",
            base_url="https://api.inconsistency-test.com"
        )
        cls.db.add(cls.project)
        cls.db.commit()
        cls.db.refresh(cls.project)

        cls.endpoint = Endpoint(
            project_id=cls.project.id,
            name="Get Status",
            method="GET",
            path="/status"
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

    @patch("app.services.http_dispatcher.HttpDispatcherService.dispatch_direct", new_callable=AsyncMock)
    def test_api_execute_direct_sequential_deterministic(self, mock_dispatch):
        mock_dispatch.return_value = ExecutionResultResponse(
            url="https://api.inconsistency-test.com/status",
            method="GET",
            status_code=200,
            status_text="OK",
            headers={"content-type": "application/json"},
            body={"service": "up"},
            parsed_body={"service": "up"},
            elapsed_ms=18.5,
            is_success=True,
            redirect_count=0
        )

        res = self.client.post("/api/v1/inconsistency/execute-direct", json={
            "direct_request": {
                "base_url": "https://api.inconsistency-test.com",
                "method": "GET",
                "path": "/status"
            },
            "iterations": 5,
            "mode": "sequential",
            "delay_ms": 0.0
        })
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["success"])
        report = body["data"]
        self.assertEqual(report["total_runs"], 5)
        self.assertEqual(report["successful_runs"], 5)
        self.assertEqual(report["pass_rate_percent"], 100.0)
        self.assertEqual(report["flakiness_score"], 0.0)
        self.assertFalse(report["is_flaky"])
        self.assertEqual(report["verdict"], "DETERMINISTIC_PASS")

    @patch("app.services.http_dispatcher.HttpDispatcherService.dispatch_direct", new_callable=AsyncMock)
    def test_api_execute_direct_concurrent_flaky(self, mock_dispatch):
        # Alternate between 200 OK and 503 Service Unavailable
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count % 2 == 0:
                return ExecutionResultResponse(
                    url="https://api.inconsistency-test.com/status",
                    method="GET",
                    status_code=503,
                    status_text="Service Unavailable",
                    headers={"content-type": "text/plain"},
                    body="Temporarily Overloaded",
                    elapsed_ms=150.0,
                    is_success=False,
                    redirect_count=0
                )
            return ExecutionResultResponse(
                url="https://api.inconsistency-test.com/status",
                method="GET",
                status_code=200,
                status_text="OK",
                headers={"content-type": "application/json"},
                body={"service": "up"},
                elapsed_ms=20.0,
                is_success=True,
                redirect_count=0
            )

        mock_dispatch.side_effect = side_effect

        res = self.client.post("/api/v1/inconsistency/execute-direct", json={
            "direct_request": {
                "base_url": "https://api.inconsistency-test.com",
                "method": "GET",
                "path": "/status"
            },
            "iterations": 6,
            "mode": "concurrent",
            "concurrency_limit": 3
        })
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertFalse(body["success"])  # Flagged as flaky
        report = body["data"]
        self.assertEqual(report["total_runs"], 6)
        self.assertEqual(report["successful_runs"], 3)
        self.assertEqual(report["failed_runs"], 3)
        self.assertGreater(report["flakiness_score"], 0.0)
        self.assertTrue(report["is_flaky"])
        self.assertEqual(report["verdict"], "CRITICAL_INTERMITTENT_FAILURE")

    @patch("app.services.http_dispatcher.HttpDispatcherService.dispatch_endpoint", new_callable=AsyncMock)
    def test_api_execute_endpoint(self, mock_dispatch):
        mock_dispatch.return_value = ExecutionResultResponse(
            url="https://api.inconsistency-test.com/status",
            method="GET",
            status_code=200,
            status_text="OK",
            headers={"content-type": "application/json"},
            body={"status": "healthy"},
            elapsed_ms=15.0,
            is_success=True,
            redirect_count=0
        )

        res = self.client.post(f"/api/v1/inconsistency/endpoints/{self.endpoint.id}/execute", json={
            "iterations": 4,
            "mode": "sequential"
        })
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["total_runs"], 4)

    def test_api_execute_endpoint_not_found(self):
        res = self.client.post("/api/v1/inconsistency/endpoints/99999/execute", json={
            "iterations": 3
        })
        self.assertEqual(res.status_code, 404)

    def test_api_analyze_batch(self):
        iterations = [
            {
                "iteration": 1,
                "timestamp": "2026-09-09T12:00:00Z",
                "status_code": 200,
                "status_text": "OK",
                "elapsed_ms": 12.4,
                "payload_hash": "a1b2c3d4e5f6",
                "is_success": True
            },
            {
                "iteration": 2,
                "timestamp": "2026-09-09T12:00:01Z",
                "status_code": 200,
                "status_text": "OK",
                "elapsed_ms": 14.1,
                "payload_hash": "a1b2c3d4e5f6",
                "is_success": True
            },
            {
                "iteration": 3,
                "timestamp": "2026-09-09T12:00:02Z",
                "status_code": 500,
                "status_text": "Internal Server Error",
                "elapsed_ms": 350.0,
                "payload_hash": "f6e5d4c3b2a1",
                "is_success": False
            }
        ]
        res = self.client.post("/api/v1/inconsistency/analyze", json={
            "iterations": iterations,
            "target_name": "Stored Batch"
        })
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertFalse(body["success"])  # Flaky batch
        self.assertEqual(body["data"]["total_runs"], 3)
        self.assertTrue(body["data"]["is_flaky"])


if __name__ == "__main__":
    unittest.main()
