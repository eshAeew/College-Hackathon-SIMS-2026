"""Pydantic DTOs and Enums for the Failure Analysis Engine (Stage 18)."""
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class RootCauseCategory(str, Enum):
    """Standardized root-cause taxonomy for execution failures."""
    MISSING_INPUT_VALIDATION = "MISSING_INPUT_VALIDATION"
    SERVER_EXCEPTION = "SERVER_EXCEPTION"
    RESPONSE_CONTRACT_MISMATCH = "RESPONSE_CONTRACT_MISMATCH"
    PERFORMANCE_SLA_BREACH = "PERFORMANCE_SLA_BREACH"
    NETWORK_TIMEOUT = "NETWORK_TIMEOUT"
    AUTHENTICATION_FAILURE = "AUTHENTICATION_FAILURE"
    AUTHORIZATION_FAILURE = "AUTHORIZATION_FAILURE"
    RATE_LIMITED = "RATE_LIMITED"
    ENDPOINT_NOT_FOUND = "ENDPOINT_NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    STATUS_CODE_MISMATCH = "STATUS_CODE_MISMATCH"
    BODY_ASSERTION_FAILURE = "BODY_ASSERTION_FAILURE"
    UNKNOWN_FAILURE = "UNKNOWN_FAILURE"


class FailureSeverity(str, Enum):
    """Impact severity rating for a categorized failure."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class HistoricalRecurrenceContext(BaseModel):
    """Historical context describing failure frequency and persistence."""
    persistence_rating: str = Field(
        ...,
        description="Rating: CHRONIC, INTERMITTENT, NEW, RESOLVED, or HEALTHY"
    )
    failure_rate_pct: float = Field(
        ..., ge=0.0, le=100.0, description="Percentage of past runs that failed"
    )
    consecutive_failure_streak: int = Field(
        default=0, ge=0, description="Consecutive failure streak length"
    )
    total_observations: int = Field(
        default=1, ge=1, description="Total number of recorded observations"
    )


class RequestEvidence(BaseModel):
    """Sanitized and reproducible request evidence bundle."""
    http_method: str = Field(..., description="HTTP Method used")
    url: str = Field(..., description="Target URL")
    headers: Dict[str, str] = Field(default_factory=dict, description="Sanitized headers with masked credentials")
    query_params: Dict[str, Any] = Field(default_factory=dict, description="Query parameters")
    path_params: Dict[str, Any] = Field(default_factory=dict, description="Path parameters")
    body_snippet: Optional[str] = Field(default=None, description="Bounded request body snippet")
    curl_command: str = Field(..., description="Reproducible cURL command with masked secrets")


class ResponseEvidence(BaseModel):
    """Captured response telemetry and diagnostic payload."""
    status_code: Optional[int] = Field(default=None, description="HTTP status code")
    headers: Dict[str, str] = Field(default_factory=dict, description="Response headers received")
    body_snippet: Optional[str] = Field(default=None, description="Bounded response body snippet")
    latency_ms: Optional[float] = Field(default=None, description="Execution elapsed latency in ms")
    network_error: Optional[str] = Field(default=None, description="Network or socket exception if any")


class AssertionFailureDetail(BaseModel):
    """Structured detail of a failed assertion rule."""
    target: str = Field(..., description="Target evaluated: status, header, body, latency")
    path: Optional[str] = Field(default=None, description="JSONPath or header name")
    operator: str = Field(..., description="Comparison operator")
    expected: Optional[Any] = Field(default=None, description="Expected value")
    actual: Optional[Any] = Field(default=None, description="Actual value encountered")
    message: str = Field(..., description="Human-readable explanation of the mismatch")


class RootCauseAssessment(BaseModel):
    """Categorized diagnosis and remediation hint."""
    category: RootCauseCategory = Field(..., description="Root cause taxonomy category")
    confidence_pct: float = Field(..., ge=0.0, le=100.0, description="Confidence in this diagnosis (0-100%)")
    description: str = Field(..., description="Clear explanation of the failure")
    troubleshooting_hint: str = Field(..., description="Actionable recommendation to resolve the issue")


class FailureEvidence(BaseModel):
    """Self-contained diagnostic evidence package for a test failure."""
    evidence_id: str = Field(..., description="Deterministic evidence ID (EV-...)")
    test_name: str = Field(..., description="Name of the test case")
    test_case_id: Optional[int] = Field(default=None, description="Associated TestCase ID if persisted")
    endpoint_id: Optional[int] = Field(default=None, description="Associated Endpoint ID if persisted")
    run_id: Optional[int] = Field(default=None, description="Associated TestRun ID if persisted")
    is_negative_test: bool = Field(default=False, description="Whether this was an adversarial/negative test")
    expected_status: Optional[int] = Field(default=None, description="Expected HTTP status code")
    max_latency_ms: Optional[float] = Field(default=None, description="SLA latency ceiling in ms")
    request: RequestEvidence = Field(..., description="Sanitized request details")
    response: ResponseEvidence = Field(..., description="Captured response details")
    assertion_failures: List[AssertionFailureDetail] = Field(default_factory=list, description="Assertion failure list")
    root_cause: RootCauseAssessment = Field(..., description="Root cause diagnosis")
    severity: FailureSeverity = Field(..., description="Assessed impact severity")
    history: HistoricalRecurrenceContext = Field(..., description="Recurrence context")


class PackageEvidenceRequest(BaseModel):
    """Payload for packaging ad-hoc execution telemetry into an evidence bundle."""
    test_name: str = Field(..., description="Name of the test scenario")
    http_method: str = Field(default="GET", description="HTTP Method")
    url: str = Field(..., description="Full URL executed")
    request_headers: Dict[str, str] = Field(default_factory=dict, description="Request headers")
    query_params: Dict[str, Any] = Field(default_factory=dict, description="Query parameters")
    path_params: Dict[str, Any] = Field(default_factory=dict, description="Path parameters")
    request_body: Optional[Any] = Field(default=None, description="Request body")
    status_code: Optional[int] = Field(default=None, description="Actual HTTP response status")
    response_headers: Dict[str, str] = Field(default_factory=dict, description="Response headers")
    response_body: Optional[str] = Field(default=None, description="Raw response body string")
    latency_ms: Optional[float] = Field(default=None, description="Execution latency in ms")
    network_error: Optional[str] = Field(default=None, description="Exception string if execution failed")
    expected_status: Optional[int] = Field(default=None, description="Expected HTTP status code")
    max_latency_ms: Optional[float] = Field(default=None, description="Max allowed latency in ms")
    is_negative_test: bool = Field(default=False, description="Whether this was a negative test case")
    assertion_failures: List[AssertionFailureDetail] = Field(default_factory=list, description="List of assertion failures")
    previous_failures: int = Field(default=0, ge=0, description="Count of historical failures for this test")
    total_observations: int = Field(default=1, ge=1, description="Total historical runs observed")


class CategorizeFailureRequest(BaseModel):
    """Payload for categorizing failure signals into a RootCauseAssessment."""
    status_code: Optional[int] = Field(default=None, description="Actual status code")
    expected_status: Optional[int] = Field(default=None, description="Expected status code")
    response_body: Optional[str] = Field(default=None, description="Response body snippet")
    latency_ms: Optional[float] = Field(default=None, description="Actual latency in ms")
    max_latency_ms: Optional[float] = Field(default=None, description="Max allowed latency in ms")
    network_error: Optional[str] = Field(default=None, description="Network exception name")
    is_negative_test: bool = Field(default=False, description="True if this was an adversarial test")
    schema_errors: List[str] = Field(default_factory=list, description="Schema validation error messages")


class RunFailureAnalysisReport(BaseModel):
    """Aggregated failure analysis report for an entire TestRun."""
    run_id: int = Field(..., description="ID of the analyzed TestRun")
    run_name: str = Field(..., description="Name of the TestRun")
    total_results: int = Field(..., description="Total executions in the run")
    total_failures: int = Field(..., description="Count of failing/erroring executions")
    category_breakdown: Dict[str, int] = Field(default_factory=dict, description="Failures per RootCauseCategory")
    severity_breakdown: Dict[str, int] = Field(default_factory=dict, description="Failures per FailureSeverity")
    evidence: List[FailureEvidence] = Field(default_factory=list, description="List of packaged failure evidence bundles")
