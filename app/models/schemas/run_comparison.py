"""Pydantic DTO schemas for Stage 21: Run Comparison & Diff Tool."""
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict


class DeltaStatus(str, Enum):
    """Directional evaluation status of a metric delta."""
    IMPROVED = "IMPROVED"
    DEGRADED = "DEGRADED"
    UNCHANGED = "UNCHANGED"


class DiffCategory(str, Enum):
    """Categorization of individual test result transitions between runs."""
    NEW_FAILURE = "NEW_FAILURE"            # Passed/Missing in base -> Failed in target (Regression)
    FIXED_FAILURE = "FIXED_FAILURE"        # Failed in base -> Passed in target (Resolved bug)
    BEHAVIOR_CHANGED = "BEHAVIOR_CHANGED"  # Status code or failure type changed
    LATENCY_DEGRADED = "LATENCY_DEGRADED"  # Response latency increased past threshold
    LATENCY_IMPROVED = "LATENCY_IMPROVED"  # Response latency decreased past threshold
    UNCHANGED_PASS = "UNCHANGED_PASS"      # Passed in both runs
    UNCHANGED_FAIL = "UNCHANGED_FAIL"      # Failed in both runs
    NEW_TEST = "NEW_TEST"                  # Only present in target run
    REMOVED_TEST = "REMOVED_TEST"          # Only present in base run


class MetricDelta(BaseModel):
    """Side-by-side metric delta representation."""
    metric_name: str
    previous: float = Field(..., description="Value in previous/base run")
    current: float = Field(..., description="Value in current/target run")
    delta: float = Field(..., description="Absolute change (current - previous)")
    delta_pct: float = Field(..., description="Percentage change ((current - previous) / previous * 100)")
    status: DeltaStatus = Field(default=DeltaStatus.UNCHANGED, description="Evaluation status")
    unit: str = Field(default="", description="Unit of measurement (e.g., ms, %, tests)")

    model_config = ConfigDict(from_attributes=True)


class RunComparisonMetrics(BaseModel):
    """Aggregated side-by-side metrics table between two runs."""
    total_tests: MetricDelta
    passed_tests: MetricDelta
    failed_tests: MetricDelta
    pass_rate: MetricDelta
    avg_latency: MetricDelta
    p95_latency: MetricDelta

    model_config = ConfigDict(from_attributes=True)


class TestCaseDiffItem(BaseModel):
    """Granular comparison record for a single test case across both runs."""
    test_case_id: Optional[int] = Field(default=None, description="Test Case ID")
    test_name: str = Field(..., description="Test scenario name")
    http_method: str = Field(..., description="HTTP Method")
    url: str = Field(..., description="Target endpoint URL")
    
    previous_status: Optional[str] = Field(default=None, description="Status in base run (e.g. PASS, FAIL, None)")
    current_status: Optional[str] = Field(default=None, description="Status in target run (e.g. PASS, FAIL, None)")
    
    previous_status_code: Optional[int] = Field(default=None, description="HTTP status code in base run")
    current_status_code: Optional[int] = Field(default=None, description="HTTP status code in target run")
    
    previous_latency_ms: Optional[float] = Field(default=None, description="Latency in base run")
    current_latency_ms: Optional[float] = Field(default=None, description="Latency in target run")
    latency_delta_ms: Optional[float] = Field(default=None, description="Latency change (current - previous)")
    
    category: DiffCategory = Field(..., description="Transition classification")
    detail_message: str = Field(..., description="Human-readable explanation of the transition")

    model_config = ConfigDict(from_attributes=True)


class RunHeaderSummary(BaseModel):
    """Header metadata for a compared TestRun."""
    id: int
    project_id: int
    project_name: str
    name: str
    status: str
    environment: str
    total_tests: int
    passed_tests: int
    failed_tests: int
    pass_rate_pct: float
    avg_latency_ms: float
    created_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class RunComparisonRequest(BaseModel):
    """Payload to request a comparison between two test runs."""
    base_run_id: int = Field(..., description="Previous / baseline TestRun ID")
    target_run_id: int = Field(..., description="Current / target TestRun ID")
    latency_threshold_pct: float = Field(default=25.0, ge=1.0, description="Percentage threshold to flag latency drift")
    min_latency_delta_ms: float = Field(default=50.0, ge=0.0, description="Minimum absolute ms delta required to flag latency drift")

    model_config = ConfigDict(extra="forbid")


class RunComparisonReport(BaseModel):
    """Complete execution delta and side-by-side comparison report."""
    base_run: RunHeaderSummary = Field(..., description="Previous / base run metadata")
    target_run: RunHeaderSummary = Field(..., description="Current / target run metadata")
    metrics: RunComparisonMetrics = Field(..., description="Side-by-side metric comparison table")
    insights: List[str] = Field(default_factory=list, description="Synthesized natural language bullet insights")
    
    new_failures_count: int = Field(default=0, ge=0, description="Count of new regressions")
    fixed_failures_count: int = Field(default=0, ge=0, description="Count of resolved failures")
    behavior_changed_count: int = Field(default=0, ge=0, description="Count of behavior changes")
    latency_degraded_count: int = Field(default=0, ge=0, description="Count of latency regressions")
    
    diffs: List[TestCaseDiffItem] = Field(default_factory=list, description="Granular per-test diff items")

    model_config = ConfigDict(from_attributes=True)
