"""Pydantic DTOs for the Failure Analysis Engine (Stage 18)."""
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RootCauseCategory(str, Enum):
    """Standardized failure taxonomy assigned to every analyzed failure."""
    MISSING_INPUT_VALIDATION = "MISSING_INPUT_VALIDATION"
    SERVER_EXCEPTION = "SERVER_EXCEPTION"
    RESPONSE_CONTRACT_MISMATCH = "RESPONSE_CONTRACT_MISMATCH"
    STATUS_CODE_MISMATCH = "STATUS_CODE_MISMATCH"
    PERFORMANCE_SLA_BREACH = "PERFORMANCE_SLA_BREACH"
    NETWORK_TIMEOUT = "NETWORK_TIMEOUT"
    NETWORK_CONNECTIVITY = "NETWORK_CONNECTIVITY"
    AUTHENTICATION_FAILURE = "AUTHENTICATION_FAILURE"
    AUTHORIZATION_FAILURE = "AUTHORIZATION_FAILURE"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    RATE_LIMITED = "RATE_LIMITED"
    MALFORMED_PAYLOAD = "MALFORMED_PAYLOAD"
    UNKNOWN = "UNKNOWN"


class EvidenceSeverity(str, Enum):
    """Severity attached to a packaged failure evidence bundle."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NONE = "NONE"


class AssertionFailureDetail(BaseModel):
    """A single failed assertion rendered for human and LLM consumption."""
    rule: str = Field(..., description="Human readable assertion target")
    expected: Any = Field(default=None, description="Expected value")
    actual: Any = Field(default=None, description="Observed value")
    message: str = Field(default="", description="Explanation of the mismatch")


class RequestEvidence(BaseModel):
    """Request-side reproduction detail with sensitive headers masked."""
    http_method: str = Field(default="GET")
    url: str = Field(default="")
    headers: Dict[str, str] = Field(default_factory=dict)
    query_params: Dict[str, Any] = Field(default_factory=dict)
    path_params: Dict[str, Any] = Field(default_factory=dict)
    body: Optional[Any] = Field(default=None)
    curl_command: Optional[str] = Field(default=None, description="Copy-paste reproduction command")


class ResponseEvidence(BaseModel):
    """Response-side observation captured at failure time."""
    status_code: Optional[int] = Field(default=None)
    status_text: Optional[str] = Field(default=None)
    headers: Dict[str, str] = Field(default_factory=dict)
    body_snippet: Optional[str] = Field(default=None)
    content_type: Optional[str] = Field(default=None)
    latency_ms: Optional[float] = Field(default=None)
    network_error: Optional[str] = Field(default=None)


class HistoricalContext(BaseModel):
    """Prior-occurrence context so a reviewer knows if this is new or chronic."""
    total_observations: int = Field(default=0)
    previous_failures: int = Field(default=0)
    consecutive_failures: int = Field(default=0)
    failure_rate_pct: float = Field(default=0.0)
    persistence_rating: str = Field(default="NEW")


class RootCauseAssessment(BaseModel):
    """Rule-based categorization of why the failure happened."""
    category: RootCauseCategory = Field(default=RootCauseCategory.UNKNOWN)
    title: str = Field(default="Unclassified failure")
    summary: str = Field(default="")
    confidence_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    remediation_hint: str = Field(default="")
    matched_signals: List[str] = Field(default_factory=list)


class FailureEvidence(BaseModel):
    """Self-contained diagnostic package for a single failed execution."""
    evidence_id: str = Field(..., description="Deterministic identifier for this evidence bundle")
    test_name: str = Field(default="Ad-Hoc Execution")
    test_case_id: Optional[int] = Field(default=None)
    endpoint_id: Optional[int] = Field(default=None)
    run_id: Optional[int] = Field(default=None)
    is_negative_test: bool = Field(default=False)
    expected_status: Optional[int] = Field(default=None)
    max_latency_ms: Optional[float] = Field(default=None)
    request: RequestEvidence = Field(default_factory=RequestEvidence)
    response: ResponseEvidence = Field(default_factory=ResponseEvidence)
    assertion_failures: List[AssertionFailureDetail] = Field(default_factory=list)
    root_cause: RootCauseAssessment = Field(default_factory=RootCauseAssessment)
    severity: EvidenceSeverity = Field(default=EvidenceSeverity.MEDIUM)
    history: HistoricalContext = Field(default_factory=HistoricalContext)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PackageEvidenceRequest(BaseModel):
    """Ad-hoc evidence packaging input (no database record required)."""
    test_name: str = Field(default="Ad-Hoc Execution")
    http_method: str = Field(default="GET")
    url: str = Field(..., description="Target URL under test")
    request_headers: Dict[str, str] = Field(default_factory=dict)
    query_params: Dict[str, Any] = Field(default_factory=dict)
    path_params: Dict[str, Any] = Field(default_factory=dict)
    request_body: Optional[Any] = Field(default=None)
    status_code: Optional[int] = Field(default=None)
    expected_status: Optional[int] = Field(default=None)
    response_headers: Dict[str, str] = Field(default_factory=dict)
    response_body: Optional[Any] = Field(default=None)
    latency_ms: Optional[float] = Field(default=None)
    max_latency_ms: Optional[float] = Field(default=None)
    network_error: Optional[str] = Field(default=None)
    is_negative_test: bool = Field(default=False)
    assertion_failures: List[AssertionFailureDetail] = Field(default_factory=list)
    previous_failures: int = Field(default=0, ge=0)
    total_observations: int = Field(default=0, ge=0)


class CategorizeFailureRequest(BaseModel):
    """Minimal input for standalone root-cause categorization."""
    status_code: Optional[int] = Field(default=None)
    expected_status: Optional[int] = Field(default=None)
    response_body: Optional[Any] = Field(default=None)
    latency_ms: Optional[float] = Field(default=None)
    max_latency_ms: Optional[float] = Field(default=None)
    network_error: Optional[str] = Field(default=None)
    is_negative_test: bool = Field(default=False)
    schema_errors: List[str] = Field(default_factory=list)


class RunFailureAnalysisReport(BaseModel):
    """Aggregated evidence for every failure inside one test run."""
    run_id: int
    run_name: str
    total_results: int = 0
    total_failures: int = 0
    category_breakdown: Dict[str, int] = Field(default_factory=dict)
    severity_breakdown: Dict[str, int] = Field(default_factory=dict)
    evidence: List[FailureEvidence] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
