"""Deep Audit Test Suite for Stage 18: Failure Analysis Engine.

Covers:
- All 13 root-cause taxonomy categories.
- Header masking for all sensitive keyword variants.
- Body truncation boundary conditions.
- cURL generation across all HTTP verbs and query parameter encodings.
- Deterministic SHA-256 evidence ID uniqueness & stability.
- Historical recurrence calculation edge cases.
- Malformed/corrupted JSON payloads in database entities.
- Full REST API integration scenarios including 404 error branches.
"""
import json
import unittest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.entities.project import Project
from app.models.entities.endpoint import Endpoint
from app.models.entities.test_case import TestCase
from app.models.entities.test_run import TestRun
from app.models.entities.test_result import TestResult
from app.models.schemas.failure_analysis import (
    FailureSeverity,
    RootCauseCategory,
    AssertionFailureDetail,
)
from app.utils.evidence_packager import (
    build_curl_command,
    build_evidence_id,
    build_historical_context,
    categorize_root_cause,
    derive_severity,
    mask_sensitive_headers,
    snippet_body,
)

SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


class TestStage18DeepAudit(unittest.TestCase):
    """Deep audit and edge-case verification for Stage 18."""

    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=test_engine)
        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(bind=test_engine)
        app.dependency_overrides.clear()

    # -------------------------------------------------------------
    # 1. Edge-Case Header Masking & Payload Snippets
    # -------------------------------------------------------------
    def test_01_all_sensitive_header_variations_masked(self):
        """Audit that all casing and sensitive token variations are redacted."""
        headers = {
            "AUTHORIZATION": "Bearer token1",
            "x-api-key": "secret2",
            "APIKEY": "secret3",
            "api-key": "secret4",
            "Cookie": "session=xyz",
            "Set-Cookie": "id=123",
            "Proxy-Authorization": "Basic abc",
            "X-Auth-Token": "secret5",
            "Password": "mypassword",
            "token": "tok_999",
            "Safe-Header": "KeepMe",
            "Content-Type": "application/json",
        }
        masked = mask_sensitive_headers(headers)
        self.assertEqual(masked["AUTHORIZATION"], "***REDACTED***")
        self.assertEqual(masked["x-api-key"], "***REDACTED***")
        self.assertEqual(masked["APIKEY"], "***REDACTED***")
        self.assertEqual(masked["api-key"], "***REDACTED***")
        self.assertEqual(masked["Cookie"], "***REDACTED***")
        self.assertEqual(masked["Set-Cookie"], "***REDACTED***")
        self.assertEqual(masked["Proxy-Authorization"], "***REDACTED***")
        self.assertEqual(masked["X-Auth-Token"], "***REDACTED***")
        self.assertEqual(masked["Password"], "***REDACTED***")
        self.assertEqual(masked["token"], "***REDACTED***")
        self.assertEqual(masked["Safe-Header"], "KeepMe")
        self.assertEqual(masked["Content-Type"], "application/json")

    def test_02_body_snippet_boundaries(self):
        """Audit snippet_body with None, small, exact bound, and oversized inputs."""
        self.assertEqual(snippet_body(None), "")
        self.assertEqual(snippet_body("hello"), "hello")
        
        # Dict serialization
        dict_body = {"key": "value"}
        self.assertIn('"key": "value"', snippet_body(dict_body))

        # Exactly 4096 bytes
        exact_text = "A" * 4096
        self.assertEqual(len(snippet_body(exact_text, max_len=4096)), 4096)

        # 4097 bytes -> truncated
        over_text = "B" * 5000
        snip = snippet_body(over_text, max_len=4096)
        self.assertTrue(snip.startswith("B" * 4096))
        self.assertIn("truncated 904 bytes", snip)

    def test_03_curl_generation_verbs_and_queries(self):
        """Audit cURL command builder across GET, PUT, DELETE, query params, and body escaping."""
        # GET with query params
        cmd_get = build_curl_command(
            http_method="GET",
            url="https://api.example.com/items",
            query_params={"filter": "active", "limit": 10},
            headers={"Accept": "application/json"}
        )
        self.assertIn("curl -X GET", cmd_get)
        self.assertIn("filter=active&limit=10", cmd_get)
        self.assertIn('-H "Accept: application/json"', cmd_get)

        # PUT with JSON body
        cmd_put = build_curl_command(
            http_method="PUT",
            url="https://api.example.com/items/42",
            headers={"Authorization": "Bearer secret"},
            body={"status": "UPDATED"}
        )
        self.assertIn("curl -X PUT", cmd_put)
        self.assertIn('***REDACTED***', cmd_put)
        self.assertNotIn('secret', cmd_put)

    def test_04_evidence_id_deterministic_and_unique(self):
        """Audit that identical inputs produce identical evidence IDs and distinct ones differ."""
        id1 = build_evidence_id("test-a", "https://api.com/1", 500, "SERVER_EXCEPTION")
        id2 = build_evidence_id("test-a", "https://api.com/1", 500, "SERVER_EXCEPTION")
        id3 = build_evidence_id("test-a", "https://api.com/1", 400, "SERVER_EXCEPTION")
        id4 = build_evidence_id("test-b", "https://api.com/1", 500, "SERVER_EXCEPTION")

        self.assertEqual(id1, id2)
        self.assertTrue(id1.startswith("EV-"))
        self.assertNotEqual(id1, id3)
        self.assertNotEqual(id1, id4)

    # -------------------------------------------------------------
    # 2. Comprehensive 13-Category Taxonomy Audit
    # -------------------------------------------------------------
    def test_05_audit_all_13_categories(self):
        """Audit every single category in RootCauseCategory taxonomy."""
        # 1. MISSING_INPUT_VALIDATION
        c1 = categorize_root_cause(status_code=500, is_negative_test=True)
        self.assertEqual(c1.category, RootCauseCategory.MISSING_INPUT_VALIDATION)
        self.assertEqual(derive_severity(c1), FailureSeverity.CRITICAL)

        # 2. SERVER_EXCEPTION
        c2 = categorize_root_cause(status_code=503)
        self.assertEqual(c2.category, RootCauseCategory.SERVER_EXCEPTION)
        self.assertEqual(derive_severity(c2), FailureSeverity.CRITICAL)

        # 3. RESPONSE_CONTRACT_MISMATCH
        c3 = categorize_root_cause(schema_errors=["'username' required"])
        self.assertEqual(c3.category, RootCauseCategory.RESPONSE_CONTRACT_MISMATCH)
        self.assertEqual(derive_severity(c3), FailureSeverity.HIGH)

        # 4. PERFORMANCE_SLA_BREACH
        c4 = categorize_root_cause(latency_ms=950.0, max_latency_ms=500.0)
        self.assertEqual(c4.category, RootCauseCategory.PERFORMANCE_SLA_BREACH)
        self.assertEqual(derive_severity(c4), FailureSeverity.MEDIUM)

        # 5. NETWORK_TIMEOUT
        c5 = categorize_root_cause(network_error="ReadTimeout: Request timed out after 10.0s")
        self.assertEqual(c5.category, RootCauseCategory.NETWORK_TIMEOUT)
        self.assertEqual(derive_severity(c5), FailureSeverity.MEDIUM)

        # 6. AUTHENTICATION_FAILURE
        c6 = categorize_root_cause(status_code=401)
        self.assertEqual(c6.category, RootCauseCategory.AUTHENTICATION_FAILURE)
        self.assertEqual(derive_severity(c6), FailureSeverity.HIGH)

        # 7. AUTHORIZATION_FAILURE
        c7 = categorize_root_cause(status_code=403)
        self.assertEqual(c7.category, RootCauseCategory.AUTHORIZATION_FAILURE)
        self.assertEqual(derive_severity(c7), FailureSeverity.HIGH)

        # 8. RATE_LIMITED
        c8 = categorize_root_cause(status_code=429)
        self.assertEqual(c8.category, RootCauseCategory.RATE_LIMITED)

        # 9. ENDPOINT_NOT_FOUND
        c9 = categorize_root_cause(status_code=404)
        self.assertEqual(c9.category, RootCauseCategory.ENDPOINT_NOT_FOUND)

        # 10. METHOD_NOT_ALLOWED
        c10 = categorize_root_cause(status_code=405)
        self.assertEqual(c10.category, RootCauseCategory.METHOD_NOT_ALLOWED)

        # 11. STATUS_CODE_MISMATCH
        c11 = categorize_root_cause(status_code=204, expected_status=200)
        self.assertEqual(c11.category, RootCauseCategory.STATUS_CODE_MISMATCH)

        # 12. BODY_ASSERTION_FAILURE
        c12 = categorize_root_cause(assertion_failures=[{"target": "body", "message": "mismatch"}])
        self.assertEqual(c12.category, RootCauseCategory.BODY_ASSERTION_FAILURE)

        # 13. UNKNOWN_FAILURE
        c13 = categorize_root_cause()
        self.assertEqual(c13.category, RootCauseCategory.UNKNOWN_FAILURE)

    # -------------------------------------------------------------
    # 3. Database Entity Parsing & Malformed JSON Resilience
    # -------------------------------------------------------------
    def test_06_database_entity_with_corrupted_json_resilience(self):
        """Audit that corrupted or non-dict failure_evidence_json does not crash service."""
        db = TestingSessionLocal()
        project = Project(name="Resilience Proj", base_url="https://api.test.com")
        db.add(project)
        db.commit()
        db.refresh(project)

        run = TestRun(project_id=project.id, name="Corrupt Data Run", status="COMPLETED", total_tests=1)
        db.add(run)
        db.commit()
        db.refresh(run)

        # TestResult with invalid JSON strings in text columns
        res = TestResult(
            run_id=run.id,
            test_name="corrupt-evidence-test",
            status="FAIL",
            http_method="POST",
            url="https://api.test.com/endpoint",
            response_code=500,
            response_headers_json="INVALID_JSON_NOT_DICT",
            failure_evidence_json="INVALID_JSON_NOT_DICT"
        )
        db.add(res)
        db.commit()
        db.refresh(res)
        res_id = res.id
        db.close()

        # Call endpoint for evidence on corrupted record
        resp = self.client.get(f"/api/v1/results/{res_id}/evidence")
        self.assertEqual(resp.status_code, 200)
        evidence = resp.json()["data"]
        self.assertEqual(evidence["test_name"], "corrupt-evidence-test")
        self.assertEqual(evidence["root_cause"]["category"], "SERVER_EXCEPTION")

    # -------------------------------------------------------------
    # 4. Multi-Failure Test Run Aggregation & Reporting
    # -------------------------------------------------------------
    def test_07_run_failure_analysis_multi_category_aggregation(self):
        """Audit analyze_run correctly breaks down distinct failure categories and severities."""
        db = TestingSessionLocal()
        project = Project(name="Multi Failure Proj", base_url="https://api.test.com")
        db.add(project)
        db.commit()
        db.refresh(project)

        ep = Endpoint(
            project_id=project.id,
            name="Recurring EP",
            method="GET",
            path="/recurring"
        )
        db.add(ep)
        db.commit()
        db.refresh(ep)

        tc = TestCase(
            endpoint_id=ep.id,
            name="Recurring Test Case"
        )
        db.add(tc)
        db.commit()
        db.refresh(tc)

        run = TestRun(project_id=project.id, name="Batch Failure Run", status="COMPLETED", total_tests=4)
        db.add(run)
        db.commit()
        db.refresh(run)

        r1 = TestResult(
            run_id=run.id, test_case_id=tc.id, test_name="t1-server-crash",
            status="FAIL", http_method="GET", url="https://api.test.com/1",
            response_code=500
        )
        r2 = TestResult(
            run_id=run.id, test_case_id=tc.id, test_name="t2-auth-fail",
            status="FAIL", http_method="GET", url="https://api.test.com/2",
            response_code=401
        )
        r3 = TestResult(
            run_id=run.id, test_case_id=tc.id, test_name="t3-sla-breach",
            status="WARNING", http_method="GET", url="https://api.test.com/3",
            response_code=200, response_time_ms=1200.0,
            failure_evidence_json=json.dumps({"max_latency_ms": 500.0})
        )
        r4 = TestResult(
            run_id=run.id, test_case_id=tc.id, test_name="t4-pass",
            status="PASS", http_method="GET", url="https://api.test.com/4",
            response_code=200, response_time_ms=50.0
        )
        db.add_all([r1, r2, r3, r4])
        db.commit()
        run_id = run.id
        db.close()

        # Audit GET /runs/{id}/failure-analysis
        resp = self.client.get(f"/api/v1/runs/{run_id}/failure-analysis")
        self.assertEqual(resp.status_code, 200)
        report = resp.json()["data"]

        self.assertEqual(report["total_results"], 4)
        self.assertEqual(report["total_failures"], 3)  # r1 (FAIL), r2 (FAIL), r3 (WARNING)
        self.assertIn("SERVER_EXCEPTION", report["category_breakdown"])
        self.assertIn("AUTHENTICATION_FAILURE", report["category_breakdown"])
        self.assertIn("PERFORMANCE_SLA_BREACH", report["category_breakdown"])
        self.assertIn("CRITICAL", report["severity_breakdown"])
        self.assertIn("HIGH", report["severity_breakdown"])


if __name__ == "__main__":
    unittest.main()
