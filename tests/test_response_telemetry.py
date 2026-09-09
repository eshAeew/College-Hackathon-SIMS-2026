"""Unit & Integration tests for Response & Network Telemetry Capture Engine."""
import asyncio
import base64
import json
import ssl
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core.database import Base, get_db
from app.models.schemas.endpoint import HTTPMethod
from app.models.schemas.execution import (
    DirectExecutionRequest,
    ExecutionOptions,
    ExecutionResultResponse
)
from app.models.schemas.request_config import BodyType
from app.services.http_dispatcher import HttpDispatcherService
from app.utils.telemetry_extractor import (
    classify_network_exception,
    extract_cookies,
    extract_redirect_history,
    parse_response_payload
)

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


class TestResponseTelemetry(unittest.TestCase):
    """Test suite verifying latency precision, payload parsing, cookie capture, redirect history, and error categorization."""

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

    def test_01_submillisecond_latency_measurement(self):
        """Verify elapsed_ms captures sub-millisecond precision float."""
        def mock_handler(request: httpx.Request):
            return httpx.Response(200, json={"status": "ok"}, request=request)

        mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

        async def run():
            req = httpx.Request("GET", "https://api.telemetry.test/ping")
            with patch("app.services.http_dispatcher.get_async_client", return_value=mock_client):
                return await HttpDispatcherService.dispatch_httpx_request(req, ExecutionOptions())

        result = asyncio.run(run())
        self.assertEqual(result.status_code, 200)
        self.assertIsInstance(result.elapsed_ms, float)
        self.assertGreater(result.elapsed_ms, 0.0)

    def test_02_json_response_parsing(self):
        """Verify structured JSON payload is parsed into native Python dictionary."""
        def mock_handler(request: httpx.Request):
            return httpx.Response(
                200,
                headers={"content-type": "application/json; charset=utf-8"},
                json={"user": {"id": 42, "role": "admin"}},
                request=request
            )

        mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

        async def run():
            req = httpx.Request("GET", "https://api.telemetry.test/user")
            with patch("app.services.http_dispatcher.get_async_client", return_value=mock_client):
                return await HttpDispatcherService.dispatch_httpx_request(req, ExecutionOptions())

        result = asyncio.run(run())
        self.assertFalse(result.is_binary)
        self.assertIsNone(result.raw_body_base64)
        self.assertEqual(result.body, {"user": {"id": 42, "role": "admin"}})
        self.assertIn("application/json", result.content_type)

    def test_03_text_response_parsing(self):
        """Verify plain text and XML payloads are preserved as text strings."""
        xml_content = "<response><status>healthy</status></response>"

        def mock_handler(request: httpx.Request):
            return httpx.Response(
                200,
                headers={"content-type": "application/xml"},
                text=xml_content,
                request=request
            )

        mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

        async def run():
            req = httpx.Request("GET", "https://api.telemetry.test/health.xml")
            with patch("app.services.http_dispatcher.get_async_client", return_value=mock_client):
                return await HttpDispatcherService.dispatch_httpx_request(req, ExecutionOptions())

        result = asyncio.run(run())
        self.assertFalse(result.is_binary)
        self.assertEqual(result.body, xml_content)
        self.assertEqual(result.content_type, "application/xml")

    def test_04_binary_response_base64_encoding(self):
        """Verify binary media (images, PDFs) sets is_binary=True and encodes raw_body_base64."""
        sample_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"

        def mock_handler(request: httpx.Request):
            return httpx.Response(
                200,
                headers={"content-type": "image/png"},
                content=sample_bytes,
                request=request
            )

        mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

        async def run():
            req = httpx.Request("GET", "https://api.telemetry.test/logo.png")
            with patch("app.services.http_dispatcher.get_async_client", return_value=mock_client):
                return await HttpDispatcherService.dispatch_httpx_request(req, ExecutionOptions())

        result = asyncio.run(run())
        self.assertTrue(result.is_binary)
        self.assertIsNone(result.body)
        self.assertIsNotNone(result.raw_body_base64)
        decoded = base64.b64decode(result.raw_body_base64)
        self.assertEqual(decoded, sample_bytes)
        self.assertEqual(result.content_length, len(sample_bytes))

    def test_05_cookies_extraction(self):
        """Verify Set-Cookie response headers are extracted into structured cookies dictionary."""
        def mock_handler(request: httpx.Request):
            return httpx.Response(
                200,
                headers=[
                    ("set-cookie", "session_id=sess_abc123; Path=/; HttpOnly"),
                    ("set-cookie", "theme=dark; Path=/"),
                    ("content-type", "application/json")
                ],
                json={"logged_in": True},
                request=request
            )

        mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

        async def run():
            req = httpx.Request("POST", "https://api.telemetry.test/login")
            with patch("app.services.http_dispatcher.get_async_client", return_value=mock_client):
                return await HttpDispatcherService.dispatch_httpx_request(req, ExecutionOptions())

        result = asyncio.run(run())
        self.assertEqual(result.cookies.get("session_id"), "sess_abc123")
        self.assertEqual(result.cookies.get("theme"), "dark")

    def test_06_redirect_chain_telemetry(self):
        """Verify multi-hop redirect chains populate redirect_count and redirect_history list."""
        def mock_handler(request: httpx.Request):
            url_str = str(request.url)
            if url_str == "https://api.telemetry.test/hop1":
                return httpx.Response(
                    301,
                    headers={"location": "https://api.telemetry.test/hop2"},
                    request=request
                )
            elif url_str == "https://api.telemetry.test/hop2":
                return httpx.Response(
                    302,
                    headers={"location": "https://api.telemetry.test/final"},
                    request=request
                )
            else:
                return httpx.Response(
                    200,
                    headers={"content-type": "text/plain"},
                    text="Arrived at final destination",
                    request=request
                )

        mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

        async def run():
            req = httpx.Request("GET", "https://api.telemetry.test/hop1")
            with patch("app.services.http_dispatcher.get_async_client", return_value=mock_client):
                return await HttpDispatcherService.dispatch_httpx_request(
                    req,
                    ExecutionOptions(follow_redirects=True)
                )

        result = asyncio.run(run())
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.redirect_count, 2)
        self.assertEqual(len(result.redirect_history), 2)
        self.assertEqual(result.redirect_history[0].status_code, 301)
        self.assertEqual(result.redirect_history[0].location, "https://api.telemetry.test/hop2")
        self.assertEqual(result.redirect_history[1].status_code, 302)
        self.assertEqual(result.redirect_history[1].location, "https://api.telemetry.test/final")

    def test_07_dns_lookup_error_categorization(self):
        """Verify DNS resolution failure is classified into 'dns' category with troubleshooting hints."""
        dns_exc = httpx.ConnectError("[Errno 11001] getaddrinfo failed: non-existent-domain.internal")
        err_detail = classify_network_exception(dns_exc, "https://non-existent-domain.internal/v1", 10.0)

        self.assertEqual(err_detail.error_type, "DNSLookupError")
        self.assertEqual(err_detail.error_category, "dns")
        self.assertTrue(err_detail.is_retryable)
        self.assertIn("typographical errors", err_detail.troubleshooting_hint)

    def test_08_connection_refused_error_categorization(self):
        """Verify Connection Refused is classified into 'network' category with troubleshooting hints."""
        refused_exc = httpx.ConnectError("[WinError 10061] No connection could be made because the target machine actively refused it")
        err_detail = classify_network_exception(refused_exc, "http://localhost:59999", 5.0)

        self.assertEqual(err_detail.error_type, "ConnectionRefused")
        self.assertEqual(err_detail.error_category, "network")
        self.assertTrue(err_detail.is_retryable)
        self.assertIn("no process is listening", err_detail.troubleshooting_hint)

    def test_09_connect_and_read_timeout_categorization(self):
        """Verify ConnectTimeout and ReadTimeout exceptions are classified under 'timeout' category."""
        connect_to = httpx.ConnectTimeout("Connection timed out", request=httpx.Request("GET", "https://api.slow.io"))
        connect_detail = classify_network_exception(connect_to, "https://api.slow.io", 5.0)
        self.assertEqual(connect_detail.error_type, "ConnectTimeout")
        self.assertEqual(connect_detail.error_category, "timeout")
        self.assertTrue(connect_detail.is_retryable)

        read_to = httpx.ReadTimeout("Read timed out", request=httpx.Request("GET", "https://api.slow.io"))
        read_detail = classify_network_exception(read_to, "https://api.slow.io", 5.0)
        self.assertEqual(read_detail.error_type, "ReadTimeout")
        self.assertEqual(read_detail.error_category, "timeout")
        self.assertTrue(read_detail.is_retryable)

    def test_10_ssl_validation_error_categorization(self):
        """Verify SSL certificate errors are classified under 'security' category with non-retryable flag."""
        ssl_exc = ssl.SSLCertVerificationError("certificate verify failed: self signed certificate")
        ssl_detail = classify_network_exception(ssl_exc, "https://self-signed.local", 10.0)

        self.assertEqual(ssl_detail.error_type, "SSLValidationError")
        self.assertEqual(ssl_detail.error_category, "security")
        self.assertFalse(ssl_detail.is_retryable)
        self.assertIn("verify_ssl: false", ssl_detail.troubleshooting_hint)

    def test_11_too_many_redirects_categorization(self):
        """Verify redirect loop is classified under 'redirect' category."""
        redirect_exc = httpx.TooManyRedirects("Exceeded maximum allowed redirects")
        redirect_detail = classify_network_exception(redirect_exc, "https://infinite-loop.internal", 10.0)

        self.assertEqual(redirect_detail.error_type, "TooManyRedirects")
        self.assertEqual(redirect_detail.error_category, "redirect")
        self.assertFalse(redirect_detail.is_retryable)
        self.assertIn("circular redirect loop", redirect_detail.troubleshooting_hint)

    def test_12_api_telemetry_in_rest_endpoint(self):
        """Verify /api/v1/executions/dispatch includes complete telemetry payload in REST response."""
        def mock_handler(request: httpx.Request):
            return httpx.Response(
                200,
                headers=[
                    ("content-type", "application/json"),
                    ("set-cookie", "auth=token123")
                ],
                json={"result": "telemetry_verified"},
                request=request
            )

        mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

        with patch("app.services.http_dispatcher.get_async_client", return_value=mock_client):
            response = self.client.post(
                "/api/v1/executions/dispatch",
                json={
                    "base_url": "https://api.resttelemetry.com",
                    "method": "GET",
                    "path": "/stats"
                }
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["status_code"], 200)
        self.assertEqual(data["body"], {"result": "telemetry_verified"})
        self.assertEqual(data["cookies"], {"auth": "token123"})
        self.assertIsInstance(data["elapsed_ms"], float)
        self.assertFalse(data["is_binary"])
        self.assertEqual(data["redirect_count"], 0)


if __name__ == "__main__":
    unittest.main()
