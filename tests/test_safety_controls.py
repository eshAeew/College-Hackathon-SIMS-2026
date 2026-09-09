"""Unit and Integration Tests for Safety & Execution Controls (Stage 16)."""
import json
import unittest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.entities.endpoint import Endpoint
from app.models.entities.project import Project
from app.models.schemas.safety import (
    AuditTestRunRequest,
    EnvironmentTier,
    EvaluateOperationRequest,
    OperationRiskLevel,
    SafetyPolicy,
    TargetHostAuthorizationStatus,
    ValidateTargetRequest,
)
from app.utils.safety_guard import (
    classify_operation_risk,
    evaluate_execution_safety,
    generate_confirmation_token,
    is_localhost_host,
    is_private_ip,
    match_host_pattern,
    validate_target_host,
)


class TestSafetyGuardUnit(unittest.TestCase):
    """Unit tests for host allowlisting, pattern matching, and risk classification."""

    def test_localhost_and_private_ip_detection(self):
        """Verify localhost and RFC-1918 private network identification."""
        self.assertTrue(is_localhost_host("localhost"))
        self.assertTrue(is_localhost_host("127.0.0.1"))
        self.assertTrue(is_localhost_host("localhost:8000"))
        self.assertFalse(is_localhost_host("api.external.com"))

        self.assertTrue(is_private_ip("10.0.1.50"))
        self.assertTrue(is_private_ip("192.168.1.1:8080"))
        self.assertTrue(is_private_ip("172.20.0.1"))
        self.assertFalse(is_private_ip("8.8.8.8"))

    def test_pattern_matching_wildcards(self):
        """Verify domain wildcard and exact pattern matching."""
        self.assertTrue(match_host_pattern("api.staging.example.com", "*.example.com"))
        self.assertTrue(match_host_pattern("example.com", "*.example.com"))
        self.assertTrue(match_host_pattern("sub.domain.org", "sub.domain.org"))
        self.assertFalse(match_host_pattern("malicious.com", "*.example.com"))

    def test_validate_target_host(self):
        """Verify host authorization under default and strict policies."""
        pol = SafetyPolicy(
            allowed_hosts=["localhost", "127.0.0.1", "*.mycompany.internal"],
            blocked_hosts=["forbidden.com"],
            strict_host_allowlist=True
        )

        # Localhost allowed
        r1 = validate_target_host("http://localhost:3000/api", pol)
        self.assertTrue(r1.is_authorized)
        self.assertEqual(r1.authorization_status, TargetHostAuthorizationStatus.AUTHORIZED)

        # Wildcard allowed
        r2 = validate_target_host("https://service.mycompany.internal/health", pol)
        self.assertTrue(r2.is_authorized)

        # Blocked host
        r3 = validate_target_host("https://forbidden.com/api", pol)
        self.assertFalse(r3.is_authorized)
        self.assertEqual(r3.authorization_status, TargetHostAuthorizationStatus.BLOCKED_DISALLOWED_HOST)

        # Non-whitelisted under strict
        r4 = validate_target_host("https://unauthorized-bank.com/api", pol)
        self.assertFalse(r4.is_authorized)

    def test_classify_operation_risk(self):
        """Verify risk classification across GET, POST, DELETE, and purge routes."""
        self.assertEqual(classify_operation_risk("GET", "/users"), OperationRiskLevel.SAFE_READ_ONLY)
        self.assertEqual(classify_operation_risk("POST", "/users"), OperationRiskLevel.SAFE_IDEMPOTENT_WRITE)
        self.assertEqual(classify_operation_risk("DELETE", "/users/123"), OperationRiskLevel.POTENTIALLY_DESTRUCTIVE)
        self.assertEqual(classify_operation_risk("POST", "/database/truncate"), OperationRiskLevel.CRITICAL_DATA_PURGE)
        self.assertEqual(classify_operation_risk("DELETE", "/orders/purge-all"), OperationRiskLevel.CRITICAL_DATA_PURGE)
        self.assertEqual(classify_operation_risk("POST", "/items", tags=["destructive"]), OperationRiskLevel.CRITICAL_DATA_PURGE)

    def test_evaluate_execution_safety_gating(self):
        """Verify destructive execution gating and confirmation tokens."""
        # Safe GET
        r1 = evaluate_execution_safety("GET", "/users")
        self.assertTrue(r1.is_permitted)
        self.assertFalse(r1.is_destructive)

        # Destructive DELETE without allow_destructive -> Blocked
        r2 = evaluate_execution_safety("DELETE", "/users/42", allow_destructive=False)
        self.assertFalse(r2.is_permitted)
        self.assertTrue(r2.is_destructive)

        # Destructive DELETE with allow_destructive -> Permitted
        r3 = evaluate_execution_safety("DELETE", "/users/42", allow_destructive=True)
        self.assertTrue(r3.is_permitted)

        # Critical Purge without confirmation token -> Blocked
        token = generate_confirmation_token("POST", "/system/reset")
        r4 = evaluate_execution_safety("POST", "/system/reset", allow_destructive=True)
        self.assertFalse(r4.is_permitted)
        self.assertEqual(r4.generated_confirmation_token, token)

        # Critical Purge with valid token -> Permitted
        r5 = evaluate_execution_safety("POST", "/system/reset", allow_destructive=True, confirmation_token=token)
        self.assertTrue(r5.is_permitted)


class TestSafetyAPIIntegration(unittest.TestCase):
    """Integration tests for Safety & Execution Controls REST APIs."""

    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool
        )
        Base.metadata.create_all(bind=self.engine)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

        def override_get_db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

        db = self.SessionLocal()
        self.project = Project(
            name="FinTech Microservice",
            description="Testing safety policy",
            base_url="https://api.fintech.test",
            environment="production"
        )
        db.add(self.project)
        db.commit()
        db.refresh(self.project)
        self.project_id = self.project.id
        db.close()

    def tearDown(self):
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=self.engine)

    def test_api_validate_target(self):
        """Verify POST /api/v1/safety/validate-target."""
        payload = {
            "url": "http://localhost:8080/health",
            "policy": {
                "allowed_hosts": ["localhost"],
                "allow_localhost": True
            }
        }
        resp = self.client.post("/api/v1/safety/validate-target", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertTrue(data["is_authorized"])
        self.assertEqual(data["authorization_status"], "AUTHORIZED")

    def test_api_evaluate_operation(self):
        """Verify POST /api/v1/safety/evaluate-operation."""
        # Unapproved DELETE
        resp1 = self.client.post("/api/v1/safety/evaluate-operation", json={
            "method": "DELETE",
            "url": "/api/v1/accounts/999",
            "allow_destructive": False
        })
        self.assertEqual(resp1.status_code, 200)
        d1 = resp1.json()["data"]
        self.assertFalse(d1["is_permitted"])
        self.assertTrue(d1["is_destructive"])

        # Approved DELETE
        resp2 = self.client.post("/api/v1/safety/evaluate-operation", json={
            "method": "DELETE",
            "url": "/api/v1/accounts/999",
            "allow_destructive": True
        })
        self.assertEqual(resp2.status_code, 200)
        d2 = resp2.json()["data"]
        self.assertTrue(d2["is_permitted"])

    def test_api_audit_test_run(self):
        """Verify POST /api/v1/safety/audit-test-run."""
        payload = {
            "test_operations": [
                {"method": "GET", "url": "/items"},
                {"method": "POST", "url": "/items"},
                {"method": "DELETE", "url": "/items/1"},
                {"method": "POST", "url": "/admin/truncate-db"}
            ],
            "allow_destructive": False
        }
        resp = self.client.post("/api/v1/safety/audit-test-run", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["total_operations"], 4)
        self.assertEqual(data["safe_operations"], 2)
        self.assertEqual(data["destructive_operations"], 1)
        self.assertEqual(data["critical_purge_operations"], 1)
        self.assertEqual(data["blocked_operations"], 2)
        self.assertFalse(data["is_run_permitted"])

    def test_api_project_safety_policy_get_and_update(self):
        """Verify GET & PUT /api/v1/safety/projects/{id}/policy."""
        # GET
        get_resp = self.client.get(f"/api/v1/safety/projects/{self.project_id}/policy")
        self.assertEqual(get_resp.status_code, 200)
        pol = get_resp.json()["data"]
        self.assertEqual(pol["project_id"], self.project_id)
        self.assertEqual(pol["environment"], "production")

        # PUT
        pol["strict_host_allowlist"] = True
        pol["allow_destructive_operations"] = True
        put_resp = self.client.put(f"/api/v1/safety/projects/{self.project_id}/policy", json=pol)
        self.assertEqual(put_resp.status_code, 200)
        updated = put_resp.json()["data"]
        self.assertTrue(updated["strict_host_allowlist"])
        self.assertTrue(updated["allow_destructive_operations"])


if __name__ == "__main__":
    unittest.main()
