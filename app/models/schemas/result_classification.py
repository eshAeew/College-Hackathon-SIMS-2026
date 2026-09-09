"""Pydantic Schemas and DTOs for Result Classification Engine (Stage 17)."""
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ExecutionOutcomeTier(str, Enum):
    """Standardized 4-tier execution outcome classification."""
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"
    ERROR = "ERROR"
    SKIPPED = "SKIPPED"


class ClassificationSeverity(str, Enum):
    """Impact severity rating for classified outcomes and failures."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NONE = "NONE"


class FailureSubCategory(str, Enum):
    """Granular failure category classification."""
    HTTP_500_SERVER_CRASH = "HTTP_500_SERVER_CRASH"
    STATUS_CODE_MISMATCH = "STATUS_CODE_MISMATCH"
    SCHEMA_VIOLATION = "SCHEMA_VIOLATION"
    FIELD_ASSERTION_FAILED = "FIELD_ASSERTION_FAILED"
    LATENCY_SLA_BREACH = "LATENCY_SLA_BREACH"
    NETWORK_CONNECTIVITY_ERROR = "NETWORK_CONNECTIVITY_ERROR"
    AUTH_SECURITY_FAILURE = "AUTH_SECURITY_FAILURE"
    PROTOCOL_MALFORMED = "PROTOCOL_MALFORMED"
    NONE = "NONE"


class ExecutionClassificationInput(BaseModel):
    """Input parameters representing a single execution to be classified."""
    test_name: Optional[str] = Field(default="Ad-Hoc Request", description="Scenario or test name")
    http_method: str = Field(default="GET", description="HTTP method")
    url: str = Field(..., description="Target URL")
    status_code: Optional[int] = Field(default=None, description="Observed HTTP status code")
    expected_status: Optional[int] = Field(default=None, description="Expected HTTP status code")
    latency_ms: float = Field(default=0.0, ge=0.0, description="Observed latency in milliseconds")
    max_latency_ms: Optional[float] = Field(default=None, description="Latency SLA threshold in milliseconds")
    assertions_passed: bool = Field(default=True, description="Whether all functional assertions succeeded")
    assertion_errors: List[str] = Field(default_factory=list, description="List of failed assertion messages")
    network_error: Optional[str] = Field(default=None, description="Network exception message if request failed")
    is_negative_test: bool = Field(default=False, description="Whether the test is an adversarial/negative probe")
    endpoint_severity: Optional[str] = Field(default="medium", description="Criticality rating of the endpoint")


class ClassifiedResultReport(BaseModel):
    """Standardized outcome classification and severity assessment for a single test."""
    test_name: str
    http_method: str
    url: str
    outcome: ExecutionOutcomeTier
    severity: ClassificationSeverity
    sub_category: FailureSubCategory
    priority_rank: int = Field(..., description="Numerical sorting priority (1=Critical, 2=High, 3=Medium, 4=Low, 5=None)")
    title: str = Field(..., description="Concise human-readable classification summary")
    diagnostic_details: List[str] = Field(default_factory=list, description="Detailed diagnostic reasons")
    suggested_action: str = Field(..., description="Actionable remediation recommendation")
    classified_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class BatchClassificationRequest(BaseModel):
    """Request payload to classify a batch of execution results."""
    items: List[ExecutionClassificationInput] = Field(..., description="List of execution items to classify")


class ClassificationSummaryCards(BaseModel):
    """Aggregated metrics and health score from classified executions."""
    total_executions: int
    pass_count: int
    fail_count: int
    warning_count: int
    error_count: int
    skipped_count: int
    critical_severity_count: int
    high_severity_count: int
    medium_severity_count: int
    low_severity_count: int
    health_score_index: float = Field(..., ge=0.0, le=100.0, description="Overall health score (0-100%)")
    pass_rate_pct: float = Field(..., ge=0.0, le=100.0, description="Functional pass rate (0-100%)")


class BatchClassificationReport(BaseModel):
    """Composite report containing batch summary cards and prioritized classified results."""
    summary: ClassificationSummaryCards
    prioritized_failures: List[ClassifiedResultReport] = Field(
        default_factory=list,
        description="Failures sorted by criticality priority rank (highest first)"
    )
    all_results: List[ClassifiedResultReport] = Field(default_factory=list)


class TestRunClassificationReport(BaseModel):
    """Complete classification analysis for a database-backed TestRun."""
    run_id: int
    project_id: int
    run_name: str
    environment: str
    summary: ClassificationSummaryCards
    prioritized_failures: List[ClassifiedResultReport]
    classified_results: List[ClassifiedResultReport]
