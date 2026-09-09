"""Adversarial Testing Schemas: DTOs for Payload Mutation, 4xx vs 500 Evaluation, and Endpoint Scanning."""
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class MutationStrategy(str, Enum):
    """Supported payload mutation strategies."""
    MISSING_REQUIRED_FIELD = "missing_required_field"
    TYPE_INVERSION = "type_inversion"
    BOUNDARY_EXTREME_VALUE = "boundary_extreme_value"
    NULL_INJECTION = "null_injection"
    ALL = "all"


class MutatedPayload(BaseModel):
    """Representation of an individual adversarial payload mutation."""
    mutation_id: str = Field(..., description="Unique mutation identifier", example="MUT-MISS-001")
    strategy: str = Field(..., description="Mutation technique applied", example="missing_required_field")
    target_field: str = Field(..., description="Target payload field modified or omitted", example="email")
    description: str = Field(..., description="Human-readable explanation of mutation", example="Omitted mandatory key 'email' from payload")
    original_value: Optional[Any] = Field(None, description="Original baseline value")
    mutated_value: Optional[Any] = Field(None, description="Injected corrupted/adversarial value")
    payload: Dict[str, Any] = Field(..., description="Mutated JSON payload object")
    expected_status_category: str = Field(default="4xx", description="Expected HTTP response class")


class PayloadMutationRequest(BaseModel):
    """Request payload for generating combinatorial adversarial mutations."""
    baseline_payload: Dict[str, Any] = Field(
        ...,
        description="Valid baseline JSON dictionary",
        example={"username": "alice", "email": "alice@test.com", "age": 25}
    )
    schema_definition: Optional[Dict[str, Any]] = Field(
        None,
        description="Optional JSON Schema Draft-7 definition highlighting required fields and types"
    )
    strategies: Optional[List[MutationStrategy]] = Field(
        None,
        description="List of mutation strategies to apply (defaults to all)",
        example=["missing_required_field", "type_inversion", "boundary_extreme_value", "null_injection"]
    )
    max_mutations: int = Field(default=50, ge=1, le=200, description="Maximum number of unique mutations to generate")


class PayloadMutationResponse(BaseModel):
    """Response containing generated combinatorial adversarial mutations."""
    total_mutations: int = Field(..., description="Number of mutations generated")
    strategies_used: List[str] = Field(..., description="Strategies applied")
    mutations: List[MutatedPayload] = Field(..., description="List of mutated payloads")


class NegativeTestEvaluationRequest(BaseModel):
    """Request payload for evaluating an individual negative test response."""
    status_code: int = Field(..., ge=100, le=599, description="Actual HTTP response status code", example=500)
    response_body: Optional[Any] = Field(None, description="Response payload returned by server")
    target_field: Optional[str] = Field(default="input_payload", description="Field targeted by the negative test")
    strategy: Optional[str] = Field(default="negative_test", description="Mutation or negative technique used")


class NegativeTestEvaluationReport(BaseModel):
    """Evaluation report classifying whether the server properly rejected or crashed on invalid input."""
    passed: bool = Field(..., description="True if server properly rejected input with 4xx, False if vulnerability detected")
    status_code: int = Field(..., description="HTTP status code received")
    classification: str = Field(..., description="PROPERLY_HANDLED_4XX, UNHANDLED_SERVER_EXCEPTION_5XX, or UNVALIDATED_ACCEPTANCE_2XX")
    severity: str = Field(..., description="NONE, CRITICAL, HIGH, or MEDIUM")
    verdict: str = Field(..., description="PASS, FAIL_CRITICAL, FAIL_HIGH, or WARN")
    message: str = Field(..., description="Detailed diagnostic explanation")
    defect_type: Optional[str] = Field(None, description="Categorized defect if vulnerability detected")
    recommendation: Optional[str] = Field(None, description="Actionable remediation advice for backend developers")


class AdversarialEndpointScanRequest(BaseModel):
    """Request payload for running automated adversarial fuzz scan on a stored endpoint."""
    strategies: Optional[List[MutationStrategy]] = Field(
        None,
        description="Strategies to execute (defaults to all)"
    )
    max_mutations: int = Field(default=20, ge=1, le=100, description="Maximum number of mutations to execute against endpoint")
    timeout_seconds: float = Field(default=5.0, ge=0.5, le=30.0, description="Per-request timeout in seconds")


class AdversarialScanItemResult(BaseModel):
    """Result of an individual mutated request execution during an endpoint scan."""
    mutation_id: str = Field(..., description="Mutation identifier")
    strategy: str = Field(..., description="Strategy used")
    target_field: str = Field(..., description="Target field tested")
    description: str = Field(..., description="Description of mutation")
    mutated_payload: Dict[str, Any] = Field(..., description="Payload sent to server")
    status_code: Optional[int] = Field(None, description="HTTP status code received")
    latency_ms: Optional[float] = Field(None, description="Response latency in milliseconds")
    evaluation: NegativeTestEvaluationReport = Field(..., description="Classification outcome")


class AdversarialScanReport(BaseModel):
    """Comprehensive vulnerability audit report for an endpoint adversarial fuzz scan."""
    endpoint_id: int = Field(..., description="ID of scanned endpoint")
    endpoint_name: str = Field(..., description="Name of scanned endpoint")
    endpoint_path: str = Field(..., description="Path of scanned endpoint")
    total_mutations_tested: int = Field(..., description="Total mutation test cases executed")
    properly_handled_4xx_count: int = Field(..., description="Count of properly rejected requests (HTTP 4xx)")
    unhandled_5xx_crashes_count: int = Field(..., description="Count of unhandled server crashes (HTTP 5xx)")
    unvalidated_2xx_leaks_count: int = Field(..., description="Count of silent corrupted acceptances (HTTP 2xx)")
    safety_score: float = Field(..., description="Safety percentage score (0-100%)", example=95.0)
    critical_vulnerabilities: List[AdversarialScanItemResult] = Field(..., description="List of identified 5xx and 2xx vulnerabilities")
    all_results: List[AdversarialScanItemResult] = Field(..., description="Full log of all executed mutation tests")
    summary: str = Field(..., description="Executive summary of the adversarial vulnerability scan")
