"""Tests for Stages 18-21: failure analysis, AI recommendations, dashboard, run comparison."""
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.entities.test_result import TestResult
from app.models.entities.test_run import TestRun
from app.models.schemas.failure_analysis import RootCauseCategory
from app.utils.evidence_packager import (
    build_curl_command,
    build_historical_context,
    categorize_root_cause,
    derive_severity,
    mask_sensitive_headers,
    snippet_body,
)
from app.utils.run_comparator import classify_change, decide_verdict, pct_change

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


class TestStage18EvidencePackager(unittest.TestCase):
    """Stage 18.01 - evidence packaging primitives."""

    def test_01_sensitive_headers_are_masked(self):
        masked = mask_sensitive_headers({
            "Authorization": "Bearer secret-token",
            "Cookie": "session=abc",
            "Content-Type": "application/json",
        })
        self.assertEqual(masked["Authorization"], "***REDACTED***")
        self.assertEqual(masked["Cookie"], "***REDACTED***")
        self.assertEqual(masked["Content-Type"], "application/json")

    def test_02_body_snippet_is_bounded(self):
        text = snippet_body("x" * 5000)
        self.assertLess(len(text), 5000)
        self.assertIn("truncated", text)

    def test_03_curl_command_masks_credentials(self):
        cmd = build_curl_command(
            "POST", "https://api.example.com/login",
            {"Authorization": "Bearer leak-me"}, {"email": "a@b.com"}
        )
        self.assertIn("curl -X POST", cmd)
        self.assertNotIn("leak-me", cmd)
        self.assertIn("***REDACTED***", cmd)

    def test_04_history_context_marks_chronic(self):
        history = build_historical_context(previous_failures=5, total_observations=5)
        self.assertEqual(history.persistence_rating, "CHRONIC")
        self.assertEqual(history.failure_rate_pct, 100.0)

    def test_05_history_context_marks_new(self):
        history = build_historical_context(previous_failures=0, total_observations=4)
        self.assertEqual(history.persistence_rating, "NEW")


class TestStage18RootCauseCategorizer(unittest.TestCase):
    """Stage 18.02 - the deterministic failure taxonomy."""

    def test_06_negative_test_500_is_missing_validation(self):
        a = categorize_root_cause(
            status_code=500, expected_status=400, is_negative_test=True,
            response_body="KeyError: password"
        )
        self.assertEqual(a.category, RootCauseCategory.MISSING_INPUT_VALIDATION)
        self.assertEqual(derive_severity(a).value, "CRITICAL")

    def test_07_plain_500_is_server_exception(self):
        a = categorize_root_cause(status_code=500, expected_status=200)
        self.assertEqual(a.category, RootCauseCategory.SERVER_EXCEPTION)

    def test_08_timeout_is_network_timeout(self):
        a = categorize_root_cause(network_error="ConnectTimeout")
        self.assertEqual(a.category, RootCauseCategory.NETWORK_TIMEOUT)

    def test_09_schema_errors_are_contract_mismatch(self):
        a = categorize_root_cause(
            status_code=200, expected_status=200,
            schema_errors=["'stock' is a required property"]
        )
        self.assertEqual(a.category, RootCauseCategory.RESPONSE_CONTRACT_MISMATCH)

    def test_10_latency_breach_is_sla_breach(self):
        a = categorize_root_cause(
            status_code=200, expected_status=200, latency_ms=1800.0, max_latency_ms=500.0
        )
        self.assertEqual(a.category, RootCauseCategory.PERFORMANCE_SLA_BREACH)

    def test_11_auth_and_rate_limit_categories(self):
        self.assertEqual(
            categorize_root_cause(status_code=401).category,
            RootCauseCategory.AUTHENTICATION_FAILURE
        )
        self.assertEqual(
            categorize_root_cause(status_code=403).category,
            RootCauseCategory.AUTHORIZATION_FAILURE
        )
        self.assertEqual(
            categorize_root_cause(status_code=429).category,
            RootCauseCategory.RATE_LIMITED
        )

    def test_12_status_mismatch_when_nothing_else_matches(self):
        a = categorize_root_cause(status_code=418, expected_status=200)
        self.assertEqual(a.category, RootCauseCategory.STATUS_CODE_MISMATCH)


class TestStage21Comparator(unittest.TestCase):
    """Stage 21.01 - pure comparison helpers."""

    def test_13_pass_to_fail_is_broken(self):
        kind, tone, badge = classify_change("PASS", "FAIL", 100.0, 120.0)
        self.assertEqual(kind.value, "BROKEN")
        self.assertEqual(tone.value, "NEGATIVE")

    def test_14_fail_to_pass_is_fixed(self):
        kind, _, _ = classify_change("FAIL", "PASS", 100.0, 90.0)
        self.assertEqual(kind.value, "FIXED")

    def test_15_material_slowdown_is_flagged(self):
        kind, _, badge = classify_change("PASS", "PASS", 100.0, 400.0)
        self.assertEqual(kind.value, "SLOWER")
        self.assertIn("SLOWDOWN", badge)

    def test_16_small_latency_move_is_stable(self):
        kind, _, _ = classify_change("PASS", "PASS", 100.0, 105.0)
        self.assertEqual(kind.value, "STILL_PASSING")

    def test_17_pct_change_guards_zero_baseline(self):
        self.assertIsNone(pct_change(0.0, 0.0))
        self.assertEqual(pct_change(100.0, 150.0), 50.0)

    def test_18_server_crash_forces_critical_verdict(self):
        verdict, headline = decide_verdict(1, 0, -10.0, has_server_crash=True)
        self.assertEqual(verdict.value, "CRITICAL_REGRESSIONS_FOUND")
        self.assertIn("crash", headline)

    def test_19_clean_verdict_when_nothing_changed(self):
        verdict, _ = decide_verdict(0, 0, 0.0, has_server_crash=False)
        self.assertEqual(verdict.value, "CLEAN")


class TestStages18To21Api(unittest.TestCase):
    """End-to-end API coverage across the four new stages."""

    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=test_engine)
        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)

        project = client.post("/api/v1/projects", json={
            "name": "Stage 18-21 Project", "base_url": "https://api.example.com"
        }).json()["data"]
        cls.project_id = project["id"]

        endpoint = client.post(f"/api/v1/projects/{cls.project_id}/endpoints", json={
            "name": "Login", "method": "POST", "path": "/auth/login"
        }).json()["data"]
        cls.endpoint_id = endpoint["id"]

        # Seed two runs so comparison has something real to diff.
        db = TestingSessionLocal()
        baseline = TestRun(
            project_id=cls.project_id, name="Baseline", status="COMPLETED",
            total_tests=2, passed_tests=2, failed_tests=0, warning_tests=0,
            error_tests=0, duration_ms=120.0
        )
        current = TestRun(
            project_id=cls.project_id, name="Current", status="COMPLETED",
            total_tests=2, passed_tests=1, failed_tests=1, warning_tests=0,
            error_tests=0, duration_ms=200.0
        )
        db.add_all([baseline, current])
        db.commit()
        db.refresh(baseline)
        db.refresh(current)
        cls.baseline_run_id = baseline.id
        cls.current_run_id = current.id

        db.add_all([
            TestResult(run_id=baseline.id, endpoint_id=cls.endpoint_id, test_name="login-happy",
                       status="PASS", http_method="POST", url="https://api.example.com/auth/login",
                       response_code=200, response_time_ms=100.0),
            TestResult(run_id=baseline.id, endpoint_id=cls.endpoint_id,
                       test_name="login-missing-password",
                       status="PASS", http_method="POST", url="https://api.example.com/auth/login",
                       response_code=422, response_time_ms=90.0),
            TestResult(run_id=current.id, endpoint_id=cls.endpoint_id, test_name="login-happy",
                       status="PASS", http_method="POST", url="https://api.example.com/auth/login",
                       response_code=200, response_time_ms=110.0),
            TestResult(run_id=current.id, endpoint_id=cls.endpoint_id,
                       test_name="login-missing-password",
                       status="FAIL", http_method="POST", url="https://api.example.com/auth/login",
                       response_code=500, response_time_ms=300.0,
                       response_body_snippet="KeyError: password",
                       failure_type="SERVER_ERROR"),
        ])
        db.commit()
        cls.failing_result_id = (
            db.query(TestResult)
            .filter(TestResult.run_id == current.id, TestResult.status == "FAIL")
            .first().id
        )
        db.close()

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(bind=test_engine)
        app.dependency_overrides.clear()

    def setUp(self):
        self.client = TestClient(app)

    # ---------------------------------------------------------------- Stage 18
    def test_20_package_evidence_endpoint(self):
        resp = self.client.post("/api/v1/failure-analysis/package", json={
            "test_name": "login-missing-password",
            "http_method": "POST",
            "url": "https://api.example.com/auth/login",
            "request_headers": {"Authorization": "Bearer secret"},
            "request_body": {"email": "a@b.com"},
            "status_code": 500,
            "expected_status": 400,
            "is_negative_test": True,
            "response_body": "KeyError: password",
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertTrue(data["evidence_id"].startswith("EV-"))
        self.assertEqual(data["root_cause"]["category"], "MISSING_INPUT_VALIDATION")
        self.assertEqual(data["severity"], "CRITICAL")
        self.assertNotIn("secret", data["request"]["curl_command"])

    def test_21_categorize_endpoint(self):
        resp = self.client.post("/api/v1/failure-analysis/categorize", json={
            "status_code": 500, "expected_status": 200
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["category"], "SERVER_EXCEPTION")

    def test_22_result_evidence_endpoint(self):
        resp = self.client.get(f"/api/v1/results/{self.failing_result_id}/evidence")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["test_name"], "login-missing-password")

    def test_23_run_failure_analysis_endpoint(self):
        resp = self.client.get(f"/api/v1/runs/{self.current_run_id}/failure-analysis")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["total_failures"], 1)
        self.assertIn("SERVER_EXCEPTION", data["category_breakdown"])

    def test_24_missing_result_returns_404(self):
        self.assertEqual(self.client.get("/api/v1/results/99999/evidence").status_code, 404)

    # ---------------------------------------------------------------- Stage 19
    def test_25_ai_status_reports_offline_fallback(self):
        resp = self.client.get("/api/v1/ai/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["active_engine"], "RULE_BASED_HEURISTIC")
        self.assertFalse(data["ai_enabled"])

    def test_26_prompt_synthesizer_enforces_json_contract(self):
        evidence = self.client.post("/api/v1/failure-analysis/package", json={
            "test_name": "t", "url": "https://api.example.com/x",
            "status_code": 500, "expected_status": 400, "is_negative_test": True
        }).json()["data"]
        resp = self.client.post("/api/v1/ai/synthesize-prompt", json=evidence)
        self.assertEqual(resp.status_code, 200)
        prompt = resp.json()["data"]
        self.assertIn("likely_cause", prompt["system_prompt"])
        self.assertIn("EVIDENCE:", prompt["user_prompt"])
        self.assertGreater(prompt["estimated_tokens"], 0)
        self.assertIn("severity", prompt["response_schema"]["properties"])

    def test_27_prompt_never_asks_model_to_decide_pass_fail(self):
        evidence = self.client.post("/api/v1/failure-analysis/package", json={
            "test_name": "t", "url": "https://api.example.com/x", "status_code": 500
        }).json()["data"]
        prompt = self.client.post("/api/v1/ai/synthesize-prompt", json=evidence).json()["data"]
        self.assertIn("Never state whether the test passed or failed", prompt["system_prompt"])

    def test_28_recommend_from_snapshot_offline(self):
        resp = self.client.post("/api/v1/ai/recommend-from-snapshot", json={
            "test_name": "login-missing-password",
            "url": "https://api.example.com/auth/login",
            "status_code": 500, "expected_status": 400, "is_negative_test": True,
            "persist": False
        })
        self.assertEqual(resp.status_code, 200)
        card = resp.json()["data"]
        self.assertEqual(card["source"], "RULE_BASED_HEURISTIC")
        self.assertEqual(card["severity"], "CRITICAL")
        self.assertIn("BaseModel", card["code_snippet"])

    def test_29_recommendation_persists_and_lists(self):
        resp = self.client.post(
            f"/api/v1/results/{self.failing_result_id}/recommendation?persist=true"
        )
        self.assertEqual(resp.status_code, 200)
        listed = self.client.get(f"/api/v1/results/{self.failing_result_id}/recommendations")
        self.assertEqual(listed.status_code, 200)
        self.assertGreaterEqual(len(listed.json()["data"]), 1)

    # ---------------------------------------------------------------- Stage 20
    def test_30_global_dashboard(self):
        resp = self.client.get("/api/v1/dashboard")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertGreaterEqual(data["total_projects"], 1)
        self.assertEqual(len(data["kpi_cards"]), 4)
        self.assertGreaterEqual(len(data["recent_runs"]), 2)

    def test_31_project_dashboard_has_endpoint_health(self):
        resp = self.client.get(f"/api/v1/dashboard/projects/{self.project_id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["project_id"], self.project_id)
        self.assertGreaterEqual(len(data["endpoints"]), 1)

    def test_32_endpoint_inspector(self):
        resp = self.client.get(f"/api/v1/dashboard/endpoints/{self.endpoint_id}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["path"], "/auth/login")

    def test_33_result_detail_includes_evidence_and_card(self):
        resp = self.client.get(f"/api/v1/dashboard/results/{self.failing_result_id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertIsNotNone(data["evidence"])
        self.assertIsNotNone(data["recommendation"])

    def test_34_web_ui_pages_render(self):
        self.assertEqual(self.client.get("/ui").status_code, 200)
        self.assertEqual(
            self.client.get(f"/ui/projects/{self.project_id}").status_code, 200
        )
        self.assertEqual(
            self.client.get(f"/ui/endpoints/{self.endpoint_id}").status_code, 200
        )
        self.assertEqual(
            self.client.get(f"/ui/results/{self.failing_result_id}").status_code, 200
        )

    def test_35_web_ui_is_excluded_from_openapi(self):
        schema = self.client.get("/openapi.json").json()
        self.assertNotIn("/ui", schema["paths"])

    # ---------------------------------------------------------------- Stage 21
    def test_36_compare_runs_detects_regression(self):
        resp = self.client.get(
            f"/api/v1/projects/{self.project_id}/compare-runs"
            f"?run_a={self.baseline_run_id}&run_b={self.current_run_id}"
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["broken_count"], 1)
        self.assertEqual(data["fixed_count"], 0)
        self.assertEqual(data["verdict"], "CRITICAL_REGRESSIONS_FOUND")
        self.assertLess(data["net_quality_delta_pct"], 0)

    def test_37_comparison_marks_server_crash_badge(self):
        data = self.client.get(
            f"/api/v1/projects/{self.project_id}/compare-runs"
            f"?run_a={self.baseline_run_id}&run_b={self.current_run_id}"
        ).json()["data"]
        broken = [c for c in data["changes"] if c["change"] == "BROKEN"]
        self.assertEqual(broken[0]["badge"], "CRITICAL CRASH")

    def test_38_visualize_returns_badges(self):
        resp = self.client.get(
            f"/api/v1/projects/{self.project_id}/compare-runs/visualize"
            f"?run_a={self.baseline_run_id}&run_b={self.current_run_id}"
        )
        self.assertEqual(resp.status_code, 200)
        view = resp.json()["data"]
        self.assertEqual(len(view["badges"]), 6)
        self.assertGreaterEqual(len(view["regressions"]), 1)

    def test_39_compare_latest_runs(self):
        resp = self.client.get(f"/api/v1/projects/{self.project_id}/compare-runs/latest")
        self.assertEqual(resp.status_code, 200)

    def test_40_compare_missing_run_returns_404(self):
        resp = self.client.get(
            f"/api/v1/projects/{self.project_id}/compare-runs?run_a=1&run_b=99999"
        )
        self.assertEqual(resp.status_code, 404)

    def test_41_compare_ui_page_renders(self):
        resp = self.client.get(f"/ui/projects/{self.project_id}/compare")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Run Comparison", resp.text)


if __name__ == "__main__":
    unittest.main()
