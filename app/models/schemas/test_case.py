"""Pydantic Schemas and DTOs for TestCase Management."""
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, ConfigDict, Field

from app.models.schemas.request_config import BodyType


class TestCaseSeverity(str, Enum):
    """Business criticality and failure severity level."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ComparisonOperator(str, Enum):
    """Comparison operators for assertion evaluation."""
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    GREATER_EQUAL = "greater_equal"
    LESS_EQUAL = "less_equal"
    EXISTS = "exists"
    NOT_EXISTS = "not_exists"
    TYPE_MATCH = "type_match"
    REGEX_MATCH = "regex_match"
    IS_EMPTY = "is_empty"
    IS_NOT_EMPTY = "is_not_empty"


class HeaderAssertionRule(BaseModel):
    """Expectation rule for a specific HTTP response header."""
    name: str = Field(..., description="Header name (case-insensitive)", examples=["Content-Type", "x-request-id"])
    operator: ComparisonOperator = Field(default=ComparisonOperator.EQUALS, description="Comparison operator")
    expected_value: Optional[str] = Field(default=None, description="Expected header value (or regex/contains pattern)")


class BodyFieldAssertionRule(BaseModel):
    """Expectation rule for a specific field inside the response body payload."""
    path: str = Field(..., description="Dot or bracket notation JSONPath (e.g., 'data.user.id', 'items[0].price')", examples=["data.status", "items[0].id"])
    operator: ComparisonOperator = Field(default=ComparisonOperator.EQUALS, description="Comparison operator")
    expected_value: Optional[Any] = Field(default=None, description="Expected value for comparison")
    description: Optional[str] = Field(default=None, description="Human-readable rule intent")


class TestCaseAssertions(BaseModel):
    """Structured assertion rules and expectations configuration for a TestCase."""
    expected_status: Optional[Union[int, List[int], str]] = Field(
        default=None,
        description="Expected HTTP status code, list of allowed codes, or range (e.g. 200, [200, 201], '2xx', '200-299')",
        examples=[200, [200, 201], "2xx"]
    )
    max_latency_ms: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Maximum acceptable response time threshold in milliseconds",
        examples=[500.0]
    )
    expected_content_type: Optional[str] = Field(
        default=None,
        description="Expected response Content-Type (e.g. 'application/json', 'text/html')",
        examples=["application/json"]
    )
    headers: Optional[List[HeaderAssertionRule]] = Field(
        default=None,
        description="List of header expectation rules"
    )
    body_fields: Optional[List[BodyFieldAssertionRule]] = Field(
        default=None,
        description="List of JSON body field value/presence rules"
    )
    json_schema: Optional[Dict[str, Any]] = Field(
        default=None,
        alias="schema",
        description="JSON Schema Draft-7 for response body validation"
    )

    model_config = ConfigDict(populate_by_name=True)


class AssertionRuleResult(BaseModel):
    """Individual assertion rule outcome."""
    rule_type: str = Field(..., description="Type of assertion (STATUS_CODE, LATENCY_THRESHOLD, CONTENT_TYPE, HEADER, BODY_FIELD, JSON_SCHEMA)")
    target: str = Field(..., description="Target property or path evaluated (e.g. 'HTTP Status', 'Latency', 'Header: Content-Type')")
    operator: str = Field(..., description="Operator used for evaluation")
    expected: Any = Field(default=None, description="Expected value or constraint")
    actual: Any = Field(default=None, description="Actual observed value")
    passed: bool = Field(..., description="Whether the assertion passed")
    message: str = Field(..., description="Human-readable explanation of the assertion result")


class TestCaseAssertionReport(BaseModel):
    """Complete evaluation report for all assertions configured on a TestCase."""
    test_case_id: Optional[int] = Field(default=None, description="ID of the evaluated test case, if applicable")
    test_case_name: Optional[str] = Field(default=None, description="Name of the test case")
    all_passed: bool = Field(..., description="True if 100% of assertion rules passed")
    total_rules: int = Field(..., description="Total assertion rules evaluated")
    passed_rules: int = Field(..., description="Number of passed assertion rules")
    failed_rules: int = Field(..., description="Number of failed assertion rules")
    results: List[AssertionRuleResult] = Field(default_factory=list, description="Granular breakdown per rule")
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Evaluation timestamp")


class AdHocAssertionEvaluationRequest(BaseModel):
    """Request payload for evaluating an assertions specification against raw HTTP telemetry."""
    assertions: TestCaseAssertions = Field(..., description="Assertion rules to evaluate")
    status_code: int = Field(..., description="Observed HTTP status code", examples=[200])
    latency_ms: float = Field(..., ge=0.0, description="Observed response time in ms", examples=[125.4])
    headers: Dict[str, str] = Field(default_factory=dict, description="Observed response headers")
    body: Optional[Any] = Field(default=None, description="Observed response body payload")
    content_type: Optional[str] = Field(default=None, description="Observed response Content-Type")


class TestCaseBase(BaseModel):
    """Base schema for TestCase entity shared across Create, Update, and Response."""
    name: str = Field(
        ...,
        min_length=1,
        max_length=150,
        description="Clear, descriptive name of test scenario",
        examples=["Create Order - Valid Cart with Standard Shipping"]
    )
    description: Optional[str] = Field(
        default=None,
        description="Detailed scenario explanation and execution prerequisites",
        examples=["Verify that standard orders with authenticated customer ID return 201 Created."]
    )
    is_active: bool = Field(
        default=True,
        description="Whether this test case is enabled during automated test runs"
    )
    severity: TestCaseSeverity = Field(
        default=TestCaseSeverity.MEDIUM,
        description="Business impact severity rating"
    )
    tags: List[str] = Field(
        default_factory=list,
        description="Categorization tags (e.g. ['smoke', 'regression', 'security', 'negative'])",
        examples=[["smoke", "regression"]]
    )
    path_params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Path variables mapped to concrete values for this test",
        examples=[{"user_id": "usr-100", "order_id": "ord-200"}]
    )
    query_params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Query parameters for this test scenario",
        examples=[{"notify": "true", "format": "detailed"}]
    )
    headers: Dict[str, str] = Field(
        default_factory=dict,
        description="Scenario-specific HTTP headers",
        examples=[{"Authorization": "Bearer test-user-token"}]
    )
    body_type: BodyType = Field(
        default=BodyType.JSON,
        description="Payload serialization format"
    )
    body: Optional[Any] = Field(
        default=None,
        description="Request body payload data"
    )
    assertions: Dict[str, Any] = Field(
        default_factory=dict,
        description="Assertion rules and expectation specifications"
    )


class TestCaseCreate(TestCaseBase):
    """Payload for creating a new test scenario under an endpoint."""
    pass


class TestCaseUpdate(BaseModel):
    """Payload for updating an existing test scenario (all fields optional)."""
    name: Optional[str] = Field(default=None, min_length=1, max_length=150)
    description: Optional[str] = None
    is_active: Optional[bool] = None
    severity: Optional[TestCaseSeverity] = None
    tags: Optional[List[str]] = None
    path_params: Optional[Dict[str, Any]] = None
    query_params: Optional[Dict[str, Any]] = None
    headers: Optional[Dict[str, str]] = None
    body_type: Optional[BodyType] = None
    body: Optional[Any] = None
    assertions: Optional[Dict[str, Any]] = None


class TestCaseDuplicate(BaseModel):
    """Payload for duplicating an existing test scenario."""
    name: Optional[str] = Field(
        default=None,
        description="Custom name for the duplicated test case (defaults to '[Original Name] (Copy)')"
    )


class TestCaseResponse(TestCaseBase):
    """Complete TestCase response DTO."""
    id: int
    endpoint_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TestCaseExecutionEvaluationResponse(BaseModel):
    """Composite response containing both execution telemetry and assertion verification results."""
    test_case_id: int
    test_case_name: str
    endpoint_id: int
    http_method: str
    target_url: str
    status_code: Optional[int] = None
    latency_ms: float
    response_headers: Dict[str, str] = Field(default_factory=dict)
    response_body: Optional[Any] = None
    assertion_report: TestCaseAssertionReport

