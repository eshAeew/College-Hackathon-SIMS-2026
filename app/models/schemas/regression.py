"""Pydantic DTO models for Regression Testing Engine & Delta Comparator (Stage 13)."""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict


class RegressionType(str, Enum):
    """Classification of detected regression anomaly."""
    FUNCTIONAL_REGRESSION = "FUNCTIONAL_REGRESSION"      # Passed previously, now Failed
    PERFORMANCE_REGRESSION = "PERFORMANCE_REGRESSION"    # Significant latency spike (>50%)
    SCHEMA_REGRESSION = "SCHEMA_REGRESSION"              # New schema violation
    NEW_FAILURE = "NEW_FAILURE"                          # New test introduced that fails
    RESOLVED_IMPROVEMENT = "RESOLVED_IMPROVEMENT"        # Previously failed, now passed
    NO_REGRESSION = "NO_REGRESSION"                      # Stable test status


class RegressionSeverity(str, Enum):
    """Criticality level of regression."""
    CRITICAL = "CRITICAL"    # Status 500 crash or critical business test functional regression
    HIGH = "HIGH"            # Functional failure on high-severity test or >200% latency spike
    MEDIUM = "MEDIUM"        # Performance regression (>50% latency increase)
    LOW = "LOW"              # Minor warning or non-critical change
    NONE = "NONE"            # No negative regression


class RegressionVerdict(str, Enum):
    """High-level regression health score of a run comparison."""
    CLEAN = "CLEAN"                                      # Zero regressions, all stable or improved
    DEGRADED = "DEGRADED"                                # Performance or minor regressions detected
    CRITICAL_REGRESSIONS_FOUND = "CRITICAL_REGRESSIONS_FOUND"  # Functional breaks or severe crashes


class ComparisonExecutionItem(BaseModel):
    """Execution telemetry record used for direct ad-hoc delta comparisons."""
    test_case_id: Optional[int] = None
    endpoint_id: Optional[int] = None
    test_name: str
    status: str                                          # PASS, FAIL, ERROR, etc.
    status_code: Optional[int] = None
    response_time_ms: float = 0.0
    failure_type: Optional[str] = None
    failure_message: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class RegressionItem(BaseModel):
    """Detailed differential report for an individual test case."""
    test_case_id: Optional[int] = None
    endpoint_id: Optional[int] = None
    test_name: str
    regression_type: RegressionType
    severity: RegressionSeverity
    
    # Baseline vs Current state comparison
    baseline_status: Optional[str] = None
    current_status: str
    baseline_status_code: Optional[int] = None
    current_status_code: Optional[int] = None
    
    # Latency comparison
    baseline_latency_ms: Optional[float] = None
    current_latency_ms: float
    latency_delta_ms: float
    latency_change_pct: float                            # e.g. +75.4%
    
    # Failure details & suggestions
    failure_type: Optional[str] = None
    failure_message: Optional[str] = None
    badge_label: str
    suggested_remediation: str

    model_config = ConfigDict(from_attributes=True)


class RegressionSummaryCard(BaseModel):
    """High-level statistical overview of regressions between two runs."""
    total_compared_tests: int
    total_regressions: int
    functional_regressions: int
    performance_regressions: int
    schema_regressions: int
    resolved_improvements: int
    stable_passing: int
    verdict: RegressionVerdict
    regression_rate_pct: float

    model_config = ConfigDict(from_attributes=True)


class DirectRegressionComparisonRequest(BaseModel):
    """Payload for comparing two arbitrary lists of execution results."""
    baseline_run_name: str = "Baseline Run"
    current_run_name: str = "Current Run"
    latency_degradation_threshold_pct: float = Field(default=50.0, ge=5.0, le=1000.0, description="Latency increase percentage to trigger regression alert")
    min_latency_delta_ms: float = Field(default=50.0, ge=0.0, description="Minimum absolute ms increase required to flag performance regression")
    baseline_results: List[ComparisonExecutionItem]
    current_results: List[ComparisonExecutionItem]

    model_config = ConfigDict(extra="forbid")


class ProjectRegressionReport(BaseModel):
    """Complete regression evaluation report comparing two runs."""
    project_id: Optional[int] = None
    baseline_run_id: Optional[int] = None
    baseline_run_name: Optional[str] = None
    baseline_run_date: Optional[datetime] = None
    
    current_run_id: Optional[int] = None
    current_run_name: Optional[str] = None
    current_run_date: Optional[datetime] = None
    
    summary: RegressionSummaryCard
    regressions: List[RegressionItem]
    improvements: List[RegressionItem]
    stable_items: List[RegressionItem]

    model_config = ConfigDict(from_attributes=True)
