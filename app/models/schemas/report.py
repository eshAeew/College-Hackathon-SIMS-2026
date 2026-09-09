"""Pydantic schemas and DTOs for the Reporting & Export Engine (Stage 22)."""
from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field, ConfigDict


class ReportFormat(str, Enum):
    """Supported export report formats."""
    JSON = "JSON"
    HTML = "HTML"
    MARKDOWN = "MARKDOWN"


class ReportVerdict(str, Enum):
    """Overall executive verdict for a test run report."""
    PASS = "PASS"
    FAIL = "FAIL"
    DEGRADED = "DEGRADED"


class ExecutiveSummary(BaseModel):
    """Top-level executive summary of the test execution."""
    project_id: int = Field(..., description="Project workspace ID")
    project_name: str = Field(..., description="Project workspace name")
    run_id: int = Field(..., description="Test run ID")
    run_name: str = Field(..., description="Test run suite name")
    environment: str = Field(default="development", description="Execution environment")
    started_at: Optional[str] = Field(default=None, description="ISO timestamp of run start")
    finished_at: Optional[str] = Field(default=None, description="ISO timestamp of run finish")
    duration_ms: Optional[float] = Field(default=None, description="Total execution duration in milliseconds")
    total_tests: int = Field(default=0, ge=0, description="Total test cases executed")
    passed_tests: int = Field(default=0, ge=0, description="Passed test cases count")
    failed_tests: int = Field(default=0, ge=0, description="Failed test cases count")
    pass_rate_pct: float = Field(default=100.0, ge=0.0, le=100.0, description="Overall pass rate percentage")
    verdict: ReportVerdict = Field(default=ReportVerdict.PASS, description="Executive verdict (PASS/FAIL/DEGRADED)")

    model_config = ConfigDict(from_attributes=True)


class FunctionalFailureItem(BaseModel):
    """Detailed summary of an individual test failure."""
    test_result_id: int = Field(..., description="TestResult record ID")
    test_name: str = Field(..., description="Test scenario name")
    endpoint_method: str = Field(..., description="HTTP Method")
    endpoint_path: str = Field(..., description="Endpoint route path")
    url: str = Field(..., description="Final URL requested")
    status: str = Field(..., description="PASS | FAIL | WARNING | ERROR")
    response_code: Optional[int] = Field(default=None, description="HTTP status code received")
    latency_ms: Optional[float] = Field(default=None, description="Response time in milliseconds")
    failure_type: Optional[str] = Field(default=None, description="High-level failure classification")
    failure_summary: Optional[str] = Field(default=None, description="Assertion failure detail summary")

    model_config = ConfigDict(from_attributes=True)


class FunctionalReportSection(BaseModel):
    """Functional test results section breakdown."""
    total_tests: int = Field(default=0, ge=0)
    passed_count: int = Field(default=0, ge=0)
    failed_count: int = Field(default=0, ge=0)
    warning_count: int = Field(default=0, ge=0)
    error_count: int = Field(default=0, ge=0)
    skipped_count: int = Field(default=0, ge=0)
    pass_rate_pct: float = Field(default=100.0, ge=0.0, le=100.0)
    failures: List[FunctionalFailureItem] = Field(default_factory=list, description="List of all failed tests")

    model_config = ConfigDict(from_attributes=True)


class SlowEndpointItem(BaseModel):
    """Details of an endpoint breaching SLA thresholds."""
    endpoint_method: str = Field(..., description="HTTP Method")
    endpoint_path: str = Field(..., description="Endpoint path")
    latency_ms: float = Field(..., description="Recorded latency in ms")
    target_sla_ms: float = Field(default=500.0, description="Target SLA limit in ms")
    sla_breach_ms: float = Field(..., description="Latency overrun in ms")

    model_config = ConfigDict(from_attributes=True)


class PerformanceReportSection(BaseModel):
    """Statistical latency percentiles and SLA performance metrics."""
    avg_latency_ms: float = Field(default=0.0, ge=0.0)
    p50_latency_ms: float = Field(default=0.0, ge=0.0)
    p90_latency_ms: float = Field(default=0.0, ge=0.0)
    p95_latency_ms: float = Field(default=0.0, ge=0.0)
    p99_latency_ms: float = Field(default=0.0, ge=0.0)
    max_latency_ms: float = Field(default=0.0, ge=0.0)
    min_latency_ms: float = Field(default=0.0, ge=0.0)
    sla_breach_count: int = Field(default=0, ge=0, description="Number of test cases exceeding SLA limit")
    slow_endpoints: List[SlowEndpointItem] = Field(default_factory=list, description="List of endpoints breaching SLA")

    model_config = ConfigDict(from_attributes=True)


class RecurringFailureItem(BaseModel):
    """Recurring or chronic failure pattern item."""
    fingerprint: str = Field(..., description="Normalized failure fingerprint")
    endpoint_method: str = Field(..., description="HTTP Method")
    endpoint_path: str = Field(..., description="Endpoint route path")
    occurrence_count: int = Field(default=1, ge=1, description="Number of times observed across runs")
    persistence_rating: str = Field(default="INTERMITTENT", description="CHRONIC | INTERMITTENT | NEW")
    root_cause_hint: Optional[str] = Field(default=None, description="Diagnostic hint")

    model_config = ConfigDict(from_attributes=True)


class RecurringFailuresSection(BaseModel):
    """Section documenting repeated failure patterns across historical runs."""
    total_recurring_patterns: int = Field(default=0, ge=0)
    patterns: List[RecurringFailureItem] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class RegressionItem(BaseModel):
    """Individual regression delta against baseline execution."""
    test_case_id: Optional[int] = Field(default=None)
    test_name: str = Field(...)
    endpoint_method: str = Field(...)
    endpoint_path: str = Field(...)
    baseline_status: str = Field(default="PASS")
    current_status: str = Field(default="FAIL")
    category: str = Field(default="NEW_FAILURE", description="NEW_FAILURE | LATENCY_DEGRADED | BEHAVIOR_CHANGED")
    details: Optional[str] = Field(default=None)

    model_config = ConfigDict(from_attributes=True)


class RegressionReportSection(BaseModel):
    """Regression and health drift section comparing against baseline."""
    baseline_run_id: Optional[int] = Field(default=None)
    new_failures_count: int = Field(default=0, ge=0)
    latency_regressions_count: int = Field(default=0, ge=0)
    regressions: List[RegressionItem] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ActionableRecommendationItem(BaseModel):
    """Developer action item with AI diagnosis and code fix."""
    evidence_id: str = Field(..., description="Diagnostic evidence hash")
    test_result_id: Optional[int] = Field(default=None)
    endpoint_method: str = Field(..., description="HTTP Method")
    endpoint_path: str = Field(..., description="Target endpoint")
    root_cause_category: str = Field(..., description="13-category root cause taxonomy")
    severity: str = Field(default="HIGH", description="CRITICAL | HIGH | MEDIUM | LOW")
    likely_cause: str = Field(..., description="Diagnostic assessment summary")
    suggested_fix: str = Field(..., description="Actionable remediation steps")
    reproducible_curl: Optional[str] = Field(default=None, description="Copyable cURL command")
    code_snippet: Optional[str] = Field(default=None, description="Copyable Python/FastAPI code snippet")
    source: str = Field(default="RULE_BASED_HEURISTIC", description="GEMINI_LLM | RULE_BASED_HEURISTIC")

    model_config = ConfigDict(from_attributes=True)


class RecommendationsSection(BaseModel):
    """Curated list of developer remediation proposals."""
    total_recommendations: int = Field(default=0, ge=0)
    critical_count: int = Field(default=0, ge=0)
    high_count: int = Field(default=0, ge=0)
    recommendations: List[ActionableRecommendationItem] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ComprehensiveTestReport(BaseModel):
    """Top-level report bundle integrating all 6 diagnostic sections."""
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO timestamp of report generation"
    )
    summary: ExecutiveSummary = Field(..., description="Executive summary section")
    functional: FunctionalReportSection = Field(..., description="Functional results section")
    performance: PerformanceReportSection = Field(..., description="Performance & SLA section")
    recurring_failures: RecurringFailuresSection = Field(..., description="Recurring failure patterns section")
    regressions: RegressionReportSection = Field(..., description="Regression drift section")
    recommendations: RecommendationsSection = Field(..., description="Developer recommendations section")

    model_config = ConfigDict(from_attributes=True)
