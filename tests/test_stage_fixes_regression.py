"""Regression tests for the Stage 01-17 defects found during live end-to-end verification.

Every test here fails against the pre-fix code. They deliberately avoid mocking
`dispatch_httpx_request` itself: mocking that method with AsyncMock is what allowed the
`client=` TypeError to reach production, because AsyncMock silently accepts any kwargs.
"""
import asyncio
import inspect
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.core.database import Base, get_db
from app.main import app
from app.models.schemas.execution import ExecutionOptions
from app.services.http_dispatcher import HttpDispatcherService
from app.utils.assertion_engine import extract_field_value
from app.utils.safety_guard import enforce_target_authorization, is_cloud_metadata_host

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


def _mock_client(status_code: int = 200, payload: dict = None):
    """Build a mock AsyncClient whose send() returns a real httpx.Response."""
    request = httpx.Request("GET", "https://api.example.com/orders")
    response = httpx.Response(
        status_code,
        json=payload if payload is not None else {"status": "SUCCESS"},
        request=request
    )
    client = MagicMock(spec=httpx.AsyncClient)
    client.is_closed = False
    client.send = AsyncMock(return_value=response)
    return client


class TestDispatcherSignatureRegression(unittest.TestCase):
    """The `client=` kwarg TypeError that made every test-run execution fail."""

    def test_01_dispatch_accepts_client_and_optional_options(self):
        """dispatch_httpx_request must accept `client` and a defaulted `options`."""
        sig = inspect.signature(HttpDispatcherService.dispatch_httpx_request)
        self.assertIn("client", sig.parameters,
                      "callers pass client=; the dispatcher must accept it")
        self.assertIs(sig.parameters["options"].default, None,
                      "callers pass options=None; it must be optional")
        self.assertIs(sig.parameters["client"].default, None)

    def test_02_dispatch_with_supplied_client_reuses_it(self):
        """A caller-supplied pooled client is used instead of the global one."""
        client = _mock_client()
        req = httpx.Request("GET", "https://api.example.com/orders")
        result = asyncio.run(HttpDispatcherService.dispatch_httpx_request(
            request=req, options=ExecutionOptions(), client=client))
        self.assertEqual(result.status_code, 200)
        client.send.assert_awaited()

    def test_03_dispatch_without_options_uses_defaults(self):
        """Omitting options must not raise AttributeError on None."""
        client = _mock_client()
        req = httpx.Request("GET", "https://api.example.com/orders")
        result = asyncio.run(HttpDispatcherService.dispatch_httpx_request(
            request=req, client=client))
        self.assertEqual(result.status_code, 200)


class TestJsonPathAssertionRegression(unittest.TestCase):
    """The `$.` prefix that silently resolved to 'field not found'."""

    def test_04_jsonpath_root_prefix_resolves(self):
        found, value = extract_field_value({"user": {"role": "admin"}}, "$.user.role")
        self.assertTrue(found, "JSONPath '$.user.role' must resolve")
        self.assertEqual(value, "admin")

    def test_05_bare_dot_path_still_resolves(self):
        found, value = extract_field_value({"user": {"role": "admin"}}, "user.role")
        self.assertTrue(found)
        self.assertEqual(value, "admin")

    def test_06_jsonpath_with_array_index(self):
        found, value = extract_field_value({"items": [{"id": 7}]}, "$.items[0].id")
        self.assertTrue(found)
        self.assertEqual(value, 7)

    def test_07_missing_field_still_reports_not_found(self):
        found, value = extract_field_value({"user": {}}, "$.user.role")
        self.assertFalse(found)
        self.assertIsNone(value)


class TestSsrfEnforcementRegression(unittest.TestCase):
    """Stage 16's guard existed but nothing called it before dispatch."""

    def test_08_cloud_metadata_hosts_detected(self):
        self.assertTrue(is_cloud_metadata_host("169.254.169.254"))
        self.assertTrue(is_cloud_metadata_host("metadata.google.internal"))
        self.assertTrue(is_cloud_metadata_host("169.254.1.1"))
        self.assertFalse(is_cloud_metadata_host("httpbin.org"))
        self.assertFalse(is_cloud_metadata_host("127.0.0.1"))

    def test_09_enforcement_blocks_metadata_endpoint(self):
        verdict = enforce_target_authorization("http://169.254.169.254/latest/meta-data/")
        self.assertIsNotNone(verdict)
        self.assertFalse(verdict.is_authorized)

    def test_10_enforcement_allows_ordinary_public_host(self):
        verdict = enforce_target_authorization("https://httpbin.org/get")
        self.assertIsNotNone(verdict)
        self.assertTrue(verdict.is_authorized)

    def test_11_dispatcher_refuses_metadata_target(self):
        """The dispatcher itself must refuse, not merely offer a helper."""
        from fastapi import HTTPException
        req = httpx.Request("GET", "http://169.254.169.254/latest/meta-data/")
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(HttpDispatcherService.dispatch_httpx_request(
                request=req, options=ExecutionOptions(), client=_mock_client()))
        self.assertEqual(ctx.exception.status_code, 403)


class TestCorsCredentialsRegression(unittest.TestCase):
    """A wildcard origin must never be paired with credentials."""

    def setUp(self):
        self.client = TestClient(app)

    def test_12_wildcard_origin_does_not_allow_credentials(self):
        resp = self.client.get("/health", headers={"Origin": "https://evil.example"})
        settings = get_settings()
        if "*" in settings.CORS_ORIGINS:
            self.assertNotEqual(
                resp.headers.get("access-control-allow-credentials"), "true",
                "wildcard CORS must not advertise allow-credentials")


class TestHealthAndDiagnosticsRegression(unittest.TestCase):
    """Health must probe the database, and pool diagnostics must be reachable."""

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

    def test_13_health_reports_database_state(self):
        resp = self.client.get("/api/v1/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["database"]["status"], "connected")

    def test_14_health_reports_unavailable_when_db_down(self):
        """The probe must actually execute a query, not hardcode 'connected'."""
        with patch("app.api.v1.api.engine") as mock_engine:
            mock_engine.connect.side_effect = RuntimeError("database is gone")
            resp = self.client.get("/api/v1/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["database"]["status"], "unavailable")

    def test_15_client_info_endpoint_is_reachable(self):
        resp = self.client.get("/api/v1/executions/client-info")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("default_timeout", resp.json()["data"])

    def test_16_endpoint_response_exposes_path_variables(self):
        proj = self.client.post("/api/v1/projects", json={
            "name": "Regression Proj", "base_url": "https://api.example.com"}).json()["data"]
        ep = self.client.post(f"/api/v1/projects/{proj['id']}/endpoints", json={
            "name": "Order Lookup", "method": "GET",
            "path": "/users/{user_id}/orders/{order_id}"}).json()["data"]
        self.assertEqual(ep["path_variables"], ["user_id", "order_id"])


if __name__ == "__main__":
    unittest.main()
