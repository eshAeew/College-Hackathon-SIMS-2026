"""Unit and Integration Tests for Assertion Rules & Expectation Setup (Stage 06 Sub-Stage 02)."""
import json
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
from app.models.entities.test_case import TestCase
from app.models.schemas.execution import ExecutionResultResponse
from app.models.schemas.test_case import (
    BodyFieldAssertionRule,
    ComparisonOperator,
    HeaderAssertionRule,
    TestCaseAssertions,
)
from app.utils.assertion_engine import (
    evaluate_assertions,
    evaluate_operator,
    extract_field_value,
)


class TestAssertionEngine(unittest.TestCase):
    """Unit tests for the standalone assertion evaluator utility."""

    def test_extract_field_value_dot_and_bracket(self):
        data = {
            "user": {
                "id": "u-123",
                "profile": {
                    "firstName": "John",
                    "roles": ["admin", "developer"]
                }
            },
            "items": [
                {"id": 1, "name": "Item A", "tags": ["hot", "sale"]},
                {"id": 2, "name": "Item B", "tags": ["cold"]}
            ],
            "count": 42
        }

        # Dot notation
        found, val = extract_field_value(data, "user.id")
        self.assertTrue(found)
        self.assertEqual(val, "u-123")

        found, val = extract_field_value(data, "user.profile.firstName")
        self.assertTrue(found)
        self.assertEqual(val, "John")

        # Bracket notation
        found, val = extract_field_value(data, "user.profile.roles[1]")
        self.assertTrue(found)
        self.assertEqual(val, "developer")

        found, val = extract_field_value(data, "items[0].name")
        self.assertTrue(found)
        self.assertEqual(val, "Item A")

        found, val = extract_field_value(data, "items[1].tags[0]")
        self.assertTrue(found)
        self.assertEqual(val, "cold")

        # Non-existent paths
        found, val = extract_field_value(data, "user.profile.lastName")
        self.assertFalse(found)
        self.assertIsNone(val)

        found, val = extract_field_value(data, "items[99].name")
        self.assertFalse(found)
        self.assertIsNone(val)

        found, val = extract_field_value(None, "user.id")
        self.assertFalse(found)

    def test_evaluate_operators(self):
        # Equals / Not Equals
        passed, _ = evaluate_operator(ComparisonOperator.EQUALS, 100, 100)
        self.assertTrue(passed)
        passed, _ = evaluate_operator(ComparisonOperator.NOT_EQUALS, 100, 200)
        self.assertTrue(passed)

        # Contains / Not Contains
        passed, _ = evaluate_operator(ComparisonOperator.CONTAINS, "hello world", "world")
        self.assertTrue(passed)
        passed, _ = evaluate_operator(ComparisonOperator.CONTAINS, ["admin", "user"], "admin")
        self.assertTrue(passed)
        passed, _ = evaluate_operator(ComparisonOperator.NOT_CONTAINS, ["admin", "user"], "guest")
        self.assertTrue(passed)

        # Relational
        passed, _ = evaluate_operator(ComparisonOperator.GREATER_THAN, 150, 100)
        self.assertTrue(passed)
        passed, _ = evaluate_operator(ComparisonOperator.LESS_THAN, 50, 100)
        self.assertTrue(passed)
        passed, _ = evaluate_operator(ComparisonOperator.GREATER_EQUAL, 100, 100)
        self.assertTrue(passed)
        passed, _ = evaluate_operator(ComparisonOperator.LESS_EQUAL, 100, 100)
        self.assertTrue(passed)

        # Type Match
        passed, _ = evaluate_operator(ComparisonOperator.TYPE_MATCH, "test", "string")
        self.assertTrue(passed)
        passed, _ = evaluate_operator(ComparisonOperator.TYPE_MATCH, 42, "int")
        self.assertTrue(passed)
        passed, _ = evaluate_operator(ComparisonOperator.TYPE_MATCH, 3.14, "float")
        self.assertTrue(passed)
        passed, _ = evaluate_operator(ComparisonOperator.TYPE_MATCH, True, "bool")
        self.assertTrue(passed)
        passed, _ = evaluate_operator(ComparisonOperator.TYPE_MATCH, ["a", "b"], "list")
        self.assertTrue(passed)
        passed, _ = evaluate_operator(ComparisonOperator.TYPE_MATCH, {"k": "v"}, "dict")
        self.assertTrue(passed)

        # Regex Match
        passed, _ = evaluate_operator(ComparisonOperator.REGEX_MATCH, "order_12345", r"^order_\d+$")
        self.assertTrue(passed)
        passed, _ = evaluate_operator(ComparisonOperator.REGEX_MATCH, "invalid_code", r"^order_\d+$")
        self.assertFalse(passed)

        # Empty / Not Empty
        passed, _ = evaluate_operator(ComparisonOperator.IS_EMPTY, [], None)
        self.assertTrue(passed)
        passed, _ = evaluate_operator(ComparisonOperator.IS_NOT_EMPTY, [1], None)
        self.assertTrue(passed)

        # Exists / Not Exists
        passed, _ = evaluate_operator(ComparisonOperator.EXISTS, "val", None)
        self.assertTrue(passed)
        passed, _ = evaluate_operator(ComparisonOperator.NOT_EXISTS, None, None)
        self.assertTrue(passed)

    def test_composite_assertion_evaluation(self):
        assertions = TestCaseAssertions(
            expected_status=[200, 201],
            max_latency_ms=500.0,
            expected_content_type="application/json",
            headers=[
                HeaderAssertionRule(name="X-Request-Id", operator=ComparisonOperator.EXISTS),
                HeaderAssertionRule(name="Server", operator=ComparisonOperator.CONTAINS, expected_value="uvicorn")
            ],
            body_fields=[
                BodyFieldAssertionRule(path="success", operator=ComparisonOperator.EQUALS, expected_value=True),
                BodyFieldAssertionRule(path="data.user.id", operator=ComparisonOperator.TYPE_MATCH, expected_value="int"),
                BodyFieldAssertionRule(path="data.items", operator=ComparisonOperator.IS_NOT_EMPTY),
                BodyFieldAssertionRule(path="deleted_field", operator=ComparisonOperator.NOT_EXISTS)
            ],
            schema={
                "type": "object",
                "required": ["success", "data"],
                "properties": {
                    "success": {"type": "boolean"},
                    "data": {"type": "object"}
                }
            }
        )

        headers = {
            "content-type": "application/json; charset=utf-8",
            "x-request-id": "req-9999",
            "server": "uvicorn-asgi"
        }
        body = {
            "success": True,
            "data": {
                "user": {"id": 101, "name": "Alice"},
                "items": ["book", "pen"]
            }
        }

        report = evaluate_assertions(
            assertions=assertions,
            status_code=200,
            latency_ms=120.5,
            headers=headers,
            body=body,
            test_case_id=1,
            test_case_name="Comprehensive Test"
        )

        self.assertTrue(report.all_passed)
        self.assertEqual(report.total_rules, 10)
        self.assertEqual(report.passed_rules, 10)
        self.assertEqual(report.failed_rules, 0)

    def test_assertion_failure_breakdown(self):
        assertions = TestCaseAssertions(
            expected_status=200,
            max_latency_ms=100.0,
            body_fields=[
                BodyFieldAssertionRule(path="status", operator=ComparisonOperator.EQUALS, expected_value="active")
            ]
        )

        report = evaluate_assertions(
            assertions=assertions,
            status_code=200,
            latency_ms=250.0,
            headers={"content-type": "application/json"},
            body={"status": "pending"}
        )

        self.assertFalse(report.all_passed)
        self.assertEqual(report.total_rules, 3)
        self.assertEqual(report.passed_rules, 1)
        self.assertEqual(report.failed_rules, 2)


class TestAssertionAPIIntegration(unittest.TestCase):
    """Integration tests for assertion endpoints in FastAPI router."""

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
        # Seed Project and Endpoint
        self.project = Project(name="Assertion Test Suite", base_url="https://api.example.com")
        self.db.add(self.project)
        self.db.commit()

        self.endpoint = Endpoint(
            project_id=self.project.id,
            name="Get Orders",
            method="GET",
            path="/orders/{order_id}"
        )
        self.db.add(self.endpoint)
        self.db.commit()

        # Seed TestCase
        self.test_case = TestCase(
            endpoint_id=self.endpoint.id,
            name="Get Valid Order",
            path_params_json=json.dumps({"order_id": "ord-123"}),
            assertions_json=json.dumps({
                "expected_status": 200,
                "max_latency_ms": 300.0,
                "expected_content_type": "application/json"
            })
        )
        self.db.add(self.test_case)
        self.db.commit()

    def tearDown(self):
        self.db.query(TestCase).delete()
        self.db.query(Endpoint).delete()
        self.db.query(Project).delete()
        self.db.commit()
        self.db.close()

    def test_adhoc_assertion_evaluate_endpoint(self):
        payload = {
            "assertions": {
                "expected_status": "2xx",
                "max_latency_ms": 500.0,
                "headers": [
                    {"name": "Content-Type", "operator": "contains", "expected_value": "application/json"}
                ],
                "body_fields": [
                    {"path": "status", "operator": "equals", "expected_value": "SUCCESS"}
                ]
            },
            "status_code": 200,
            "latency_ms": 145.2,
            "headers": {"Content-Type": "application/json; charset=utf-8"},
            "body": {"status": "SUCCESS"}
        }

        response = self.client.post("/api/v1/assertions/evaluate", json=payload)
        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertTrue(json_data["success"])
        report = json_data["data"]
        self.assertTrue(report["all_passed"])
        self.assertEqual(report["total_rules"], 4)

    def test_get_and_update_test_case_assertions_endpoints(self):
        # 1. GET assertions
        res_get = self.client.get(f"/api/v1/test-cases/{self.test_case.id}/assertions")
        self.assertEqual(res_get.status_code, 200)
        assertions_data = res_get.json()["data"]
        self.assertEqual(assertions_data["expected_status"], 200)
        self.assertEqual(assertions_data["max_latency_ms"], 300.0)

        # 2. PUT update assertions
        new_assertions = {
            "expected_status": [200, 201],
            "max_latency_ms": 400.0,
            "expected_content_type": "application/json",
            "body_fields": [
                {"path": "id", "operator": "exists"}
            ]
        }
        res_put = self.client.put(f"/api/v1/test-cases/{self.test_case.id}/assertions", json=new_assertions)
        self.assertEqual(res_put.status_code, 200)
        updated_tc = res_put.json()["data"]
        self.assertEqual(updated_tc["assertions"]["max_latency_ms"], 400.0)
        self.assertEqual(len(updated_tc["assertions"]["body_fields"]), 1)

    @patch("app.services.http_dispatcher.HttpDispatcherService.dispatch_httpx_request", new_callable=AsyncMock)
    def test_live_execute_and_evaluate_test_case(self, mock_dispatch):
        mock_dispatch.return_value = ExecutionResultResponse(
            url="https://api.example.com/orders/ord-123",
            method="GET",
            status_code=200,
            status_text="OK",
            headers={"content-type": "application/json"},
            body_raw='{"id": "ord-123", "status": "COMPLETED"}',
            body_parsed={"id": "ord-123", "status": "COMPLETED"},
            latency_ms=115.5
        )

        response = self.client.post(f"/api/v1/test-cases/{self.test_case.id}/evaluate")
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["test_case_id"], self.test_case.id)
        self.assertEqual(data["status_code"], 200)
        self.assertTrue(data["assertion_report"]["all_passed"])
        self.assertEqual(data["assertion_report"]["passed_rules"], 3)


if __name__ == "__main__":
    unittest.main()