"""Unit & Integration tests for Asynchronous HTTP Dispatcher & Execution Engine."""
import asyncio
import json
import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core.database import Base, get_db
from app.core.http_client import create_async_client, get_async_client, init_async_client, close_async_client
from app.models.schemas.endpoint import HTTPMethod
from app.models.schemas.execution import (
    DirectExecutionRequest,
    EndpointExecutionRequest,
    ExecutionOptions,
    ExecutionResultResponse
)
from app.models.schemas.request_config import BodyType
from app.services.http_dispatcher import HttpDispatcherService
from app.models.entities.project import Project
from app.models.entities.endpoint import Endpoint

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


class TestAsyncHttpDispatcher(unittest.TestCase):
    """Test suite verifying async HTTP client, connection pooling, timeout handling, and dispatch API."""

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

    def tearDown(self):
        self.db.close()

    def test_01_http_client_creation_and_limits(self):
        """Verify custom async client creation, connection limits, and timeouts."""
        custom_client = create_async_client(
            timeout_seconds=5.0,
            max_connections=50,
            max_keepalive=10
        )
        self.assertIsInstance(custom_client, httpx.AsyncClient)
        self.assertEqual(custom_client.timeout.read, 5.0)
        self.assertEqual(custom_client.timeout.connect, 5.0)

        # Global client getter
        global_client = get_async_client()
        self.assertIsNotNone(global_client)
        self.assertFalse(global_client.is_closed)

    def test_02_dispatch_httpx_request_success(self):
        """Verify dispatching httpx.Request against a mocked HTTP transport."""
        def mock_handler(request: httpx.Request):
            return httpx.Response(
                status_code=200,
                headers={"content-type": "application/json", "x-powered-by": "mock"},
                json={"status": "ok", "received_method": request.method},
                request=request
            )

        transport = httpx.MockTransport(mock_handler)
        mock_client = httpx.AsyncClient(transport=transport)

        async def run_test():
            req = httpx.Request("GET", "https://api.mocktest.internal/v1/ping")
            with patch("app.services.http_dispatcher.get_async_client", return_value=mock_client):
                result = await HttpDispatcherService.dispatch_httpx_request(
                    req,
                    ExecutionOptions(timeout_seconds=5.0)
                )
                return result

        result = asyncio.run(run_test())
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.status_text, "OK")
        self.assertTrue(result.is_success)
        self.assertFalse(result.is_client_error)
        self.assertEqual(result.body, {"status": "ok", "received_method": "GET"})
        self.assertEqual(result.headers.get("x-powered-by"), "mock")
        self.assertGreater(result.elapsed_ms, 0)
        self.assertEqual(result.error, None)

    def test_03_dispatch_direct_with_body_and_query(self):
        """Verify direct request compilation and execution with JSON payload."""
        def mock_handler(request: httpx.Request):
            body_json = json.loads(request.read().decode())
            return httpx.Response(
                status_code=201,
                headers={"content-type": "application/json"},
                json={"created": True, "data": body_json, "query": str(request.url.query)},
                request=request
            )

        transport = httpx.MockTransport(mock_handler)
        mock_client = httpx.AsyncClient(transport=transport)

        direct_req = DirectExecutionRequest(
            base_url="https://api.orders.internal",
            method=HTTPMethod.POST,
            path="/api/v1/users/{user_id}/items",
            path_params={"user_id": "usr-888"},
            query_params={"notify": "true"},
            headers={"Authorization": "Bearer sample-token"},
            body_type=BodyType.JSON,
            body={"item_id": "ITM-99", "qty": 3},
            options=ExecutionOptions(timeout_seconds=5.0)
        )

        async def run_test():
            with patch("app.services.http_dispatcher.get_async_client", return_value=mock_client):
                return await HttpDispatcherService.dispatch_direct(direct_req)

        result = asyncio.run(run_test())
        self.assertEqual(result.status_code, 201)
        self.assertEqual(result.status_text, "Created")
        self.assertTrue(result.is_success)
        self.assertEqual(result.body["data"], {"item_id": "ITM-99", "qty": 3})
        self.assertIn("notify=true", result.url)

    def test_04_timeout_handling(self):
        """Verify timeout exception is gracefully caught and returned in ExecutionResultResponse."""
        def mock_handler(request: httpx.Request):
            raise httpx.ReadTimeout("Read operation timed out", request=request)

        transport = httpx.MockTransport(mock_handler)
        mock_client = httpx.AsyncClient(transport=transport)

        direct_req = DirectExecutionRequest(
            base_url="https://slow-api.internal",
            method=HTTPMethod.GET,
            path="/slow",
            options=ExecutionOptions(timeout_seconds=2.0)
        )

        async def run_test():
            with patch("app.services.http_dispatcher.get_async_client", return_value=mock_client):
                return await HttpDispatcherService.dispatch_direct(direct_req)

        result = asyncio.run(run_test())
        self.assertIsNone(result.status_code)
        self.assertFalse(result.is_success)
        self.assertIn(result.error_type, ("ReadTimeout", "TimeoutException"))
        self.assertIn("timed out", result.error.lower())

    def test_05_connection_error_handling(self):
        """Verify network/connection errors are captured without raising uncaught exceptions."""
        def mock_handler(request: httpx.Request):
            raise httpx.ConnectError("Failed to resolve hostname", request=request)

        transport = httpx.MockTransport(mock_handler)
        mock_client = httpx.AsyncClient(transport=transport)

        direct_req = DirectExecutionRequest(
            base_url="https://unreachable-host.internal",
            method=HTTPMethod.GET,
            path="/data",
            options=ExecutionOptions(timeout_seconds=5.0)
        )

        async def run_test():
            with patch("app.services.http_dispatcher.get_async_client", return_value=mock_client):
                return await HttpDispatcherService.dispatch_direct(direct_req)

        result = asyncio.run(run_test())
        self.assertIsNone(result.status_code)
        self.assertFalse(result.is_success)
        self.assertEqual(result.error_type, "ConnectError")
        self.assertIn("connect", result.error.lower())

    def test_06_redirect_following(self):
        """Verify redirect count and response when follow_redirects is enabled."""
        def mock_handler(request: httpx.Request):
            if "/old-path" in str(request.url):
                return httpx.Response(
                    status_code=301,
                    headers={"location": "https://redirect.internal/new-path"},
                    request=request
                )
            return httpx.Response(
                status_code=200,
                headers={"content-type": "text/plain"},
                text="Welcome to new path",
                request=request
            )

        transport = httpx.MockTransport(mock_handler)
        mock_client = httpx.AsyncClient(transport=transport)

        async def run_test():
            with patch("app.services.http_dispatcher.get_async_client", return_value=mock_client):
                return await HttpDispatcherService.dispatch_direct(
                    DirectExecutionRequest(
                        base_url="https://redirect.internal",
                        method=HTTPMethod.GET,
                        path="/old-path",
                        options=ExecutionOptions(follow_redirects=True)
                    )
                )

        result = asyncio.run(run_test())
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.redirect_count, 1)
        self.assertEqual(result.body, "Welcome to new path")

    def test_07_dispatch_endpoint_with_db_persistence(self):
        """Verify executing a stored Project + Endpoint entity with database overrides."""
        # Create Project in DB
        proj = Project(
            name="Execution Project",
            base_url="https://api.execution-test.com",
            global_headers_json=json.dumps({"X-Workspace": "WS-EXEC"})
        )
        self.db.add(proj)
        self.db.commit()
        self.db.refresh(proj)

        # Create Endpoint in DB
        ep = Endpoint(
            project_id=proj.id,
            name="Get Customer Invoices",
            method="GET",
            path="/api/v1/customers/{cust_id}/invoices",
            path_params_json=json.dumps({"cust_id": "CUST-DEFAULT"}),
            headers_json=json.dumps({"Accept": "application/json"})
        )
        self.db.add(ep)
        self.db.commit()
        self.db.refresh(ep)

        def mock_handler(request: httpx.Request):
            return httpx.Response(
                status_code=200,
                headers={"content-type": "application/json"},
                json={
                    "url": str(request.url),
                    "headers": dict(request.headers),
                    "invoices": [101, 102]
                },
                request=request
            )

        transport = httpx.MockTransport(mock_handler)
        mock_client = httpx.AsyncClient(transport=transport)

        exec_req = EndpointExecutionRequest(
            path_params={"cust_id": "CUST-OVERRIDE-99"},
            query_params={"limit": "10"},
            options=ExecutionOptions(timeout_seconds=5.0)
        )

        async def run_test():
            with patch("app.services.http_dispatcher.get_async_client", return_value=mock_client):
                return await HttpDispatcherService.dispatch_endpoint(proj.id, ep.id, exec_req, self.db)

        result = asyncio.run(run_test())
        self.assertEqual(result.status_code, 200)
        self.assertIn("CUST-OVERRIDE-99", result.url)
        self.assertEqual(result.body["headers"].get("x-workspace"), "WS-EXEC")

    def test_08_api_dispatch_direct_endpoint(self):
        """Verify POST /api/v1/executions/dispatch REST API."""
        def mock_handler(request: httpx.Request):
            return httpx.Response(
                status_code=200,
                headers={"content-type": "application/json"},
                json={"echo": "success", "method": request.method},
                request=request
            )

        mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

        with patch("app.services.http_dispatcher.get_async_client", return_value=mock_client):
            response = self.client.post(
                "/api/v1/executions/dispatch",
                json={
                    "base_url": "https://api.testapi.com",
                    "method": "POST",
                    "path": "/echo",
                    "body_type": "json",
                    "body": {"message": "hello world"},
                    "options": {
                        "timeout_seconds": 15.0,
                        "follow_redirects": True
                    }
                }
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["status_code"], 200)
        self.assertEqual(payload["data"]["body"], {"echo": "success", "method": "POST"})

    def test_09_api_execute_stored_endpoint(self):
        """Verify POST /api/v1/projects/{p_id}/endpoints/{e_id}/execute REST API."""
        # Create Project
        proj_resp = self.client.post(
            "/api/v1/projects",
            json={"name": "API Exec WS", "base_url": "https://api.ws-exec.com"}
        )
        p_id = proj_resp.json()["data"]["id"]

        # Create Endpoint
        ep_resp = self.client.post(
            f"/api/v1/projects/{p_id}/endpoints",
            json={
                "name": "Health Check",
                "method": "GET",
                "path": "/healthz"
            }
        )
        e_id = ep_resp.json()["data"]["id"]

        def mock_handler(request: httpx.Request):
            return httpx.Response(
                status_code=200,
                headers={"content-type": "application/json"},
                json={"status": "healthy"},
                request=request
            )

        mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

        with patch("app.services.http_dispatcher.get_async_client", return_value=mock_client):
            exec_resp = self.client.post(
                f"/api/v1/projects/{p_id}/endpoints/{e_id}/execute",
                json={}
            )

        self.assertEqual(exec_resp.status_code, 200)
        payload = exec_resp.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["status_code"], 200)
        self.assertEqual(payload["data"]["body"], {"status": "healthy"})

    def test_10_api_client_info(self):
        """Verify GET /api/v1/executions/client-info returns connection pool diagnostics."""
        response = self.client.get("/api/v1/executions/client-info")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertTrue(payload["data"]["is_active"])
        self.assertGreater(payload["data"]["default_timeout"], 0)
        self.assertGreater(payload["data"]["max_concurrency"], 0)

    def test_11_preflight_failure_blocks_execution(self):
        """Verify that malformed requests are blocked by pre-flight validation with HTTP 400."""
        response = self.client.post(
            "/api/v1/executions/dispatch",
            json={
                "base_url": "ftp://invalid-scheme.internal:99999",
                "method": "GET",
                "path": "/test"
            }
        )
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
