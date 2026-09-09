"""Pydantic schemas and DTOs for Recurring Failure Detection & Pattern Clustering (Stage 11)."""
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class PersistenceRating(str, Enum):
    """Failure persistence and recurrence severity rating."""
    CHRONIC = "CHRONIC"              # Continuous or heavy failure rate (>= 70% or >= 3 consecutive)
    INTERMITTENT = "INTERMITTENT"    # Flapping / alternating between pass and fail
    NEW = "NEW"                      # Recently emerged failure with low sample history
    RESOLVED = "RESOLVED"            # Previously failing but passing in latest run(s)
    HEALTHY = "HEALTHY"              # Consistently passing (0% failure rate)


class FailureCategory(str, Enum):
    """Categorization of failure root causes."""
    SERVER_CRASH = "SERVER_CRASH_5XX"
    AUTH_FAILURE = "AUTH_FAILURE_401_403"
    VALIDATION_ERROR = "VALIDATION_ERROR_422_400"
    TIMEOUT = "TIMEOUT_LATENCY"
    SCHEMA_MISMATCH = "SCHEMA_VIOLATION"
    ASSERTION_FAILED = "ASSERTION_FAILURE"
    NETWORK_ERROR = "NETWORK_CONNECTIVITY"
    UNKNOWN = "UNKNOWN"


class HistoricalExecutionSample(BaseModel):
    """A single historical execution outcome for a test or endpoint."""
    run_id: Optional[str] = Field(default=None, description="Test run ID or UUID")
    endpoint_id: Optional[int] = Field(default=None, description="Associated endpoint ID")
    test_case_id: Optional[int] = Field(default=None, description="Associated test case ID")
    passed: bool = Field(..., description="True if test/execution passed")
    status_code: Optional[int] = Field(default=None, description="HTTP response status code")
    error_message: Optional[str] = Field(default=None, description="Error message or exception text")
    latency_ms: Optional[float] = Field(default=None, description="Observed latency in ms")
    assertion_failures: List[str] = Field(default_factory=list, description="Failed assertion descriptions")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Execution timestamp")


class EndpointFailureRecurrence(BaseModel):
    """Historical failure metrics and persistence rating for an individual endpoint."""
    endpoint_id: int = Field(..., description="Endpoint ID")
    endpoint_name: str = Field(..., description="Endpoint Name")
    http_method: str = Field(..., description="HTTP Method")
    path: str = Field(..., description="Endpoint Path")
    total_recorded_runs: int = Field(..., description="Total runs in analysis window")
    failed_runs: int = Field(..., description="Number of failed executions")
    passed_runs: int = Field(..., description="Number of passed executions")
    failure_rate_pct: float = Field(..., ge=0.0, le=100.0, description="Percentage of runs that failed")
    consecutive_failures: int = Field(..., ge=0, description="Current streak of consecutive failures")
    persistence_rating: PersistenceRating = Field(..., description="Persistence classification")
    is_flapping: bool = Field(..., description="True if test status alternates frequently")
    last_executed_at: Optional[datetime] = Field(default=None, description="Timestamp of latest run")
    recent_history: List[bool] = Field(default_factory=list, description="Recent execution outcomes (True=Pass, False=Fail)")


class TestCaseFailureRecurrence(BaseModel):
    """Historical failure metrics for a specific test scenario."""
    test_case_id: int = Field(..., description="Test case ID")
    test_case_name: str = Field(..., description="Test scenario name")
    endpoint_id: int = Field(..., description="Parent endpoint ID")
    total_runs: int = Field(..., description="Total evaluated runs")
    failed_runs: int = Field(..., description="Failed run count")
    failure_rate_pct: float = Field(..., ge=0.0, le=100.0, description="Failure rate percentage")
    consecutive_failures: int = Field(..., description="Consecutive failure streak")
    persistence_rating: PersistenceRating = Field(..., description="Persistence classification")
    last_error_message: Optional[str] = Field(default=None, description="Latest error message")


class FailureCluster(BaseModel):
    """Group of similar failures across endpoints clustered by normalized root-cause fingerprint."""
    cluster_id: str = Field(..., description="Unique cluster identifier (e.g. 'FC-500-DB-CONN-a8f1')")
    fingerprint: str = Field(..., description="SHA-256 fingerprint hash of normalized error signature")
    category: FailureCategory = Field(..., description="Root cause category")
    title: str = Field(..., description="Human-readable title describing the common failure pattern")
    description: str = Field(..., description="Detailed explanation of the failure symptoms")
    affected_endpoint_ids: List[int] = Field(default_factory=list, description="List of endpoint IDs encountering this issue")
    affected_test_case_ids: List[int] = Field(default_factory=list, description="List of test case IDs affected")
    occurrence_count: int = Field(..., description="Total occurrences across runs")
    first_seen_at: Optional[datetime] = Field(default=None, description="Timestamp of first observed occurrence")
    last_seen_at: Optional[datetime] = Field(default=None, description="Timestamp of most recent occurrence")
    sample_error_message: Optional[str] = Field(default=None, description="Representative raw error message")
    suggested_action: str = Field(..., description="Actionable recommendation to fix the root cause")


class ProjectRecurringFailureReport(BaseModel):
    """Complete recurring failure report for a project workspace."""
    project_id: Optional[int] = Field(default=None, description="Project ID")
    project_name: Optional[str] = Field(default=None, description="Project Name")
    total_analyzed_runs: int = Field(..., description="Total historical runs analyzed")
    total_endpoints: int = Field(..., description="Total endpoints inspected")
    chronic_failure_count: int = Field(..., description="Endpoints with CHRONIC failures")
    intermittent_failure_count: int = Field(..., description="Endpoints with INTERMITTENT (flapping) failures")
    new_failure_count: int = Field(..., description="Endpoints with NEW failures")
    healthy_count: int = Field(..., description="Consistently HEALTHY endpoints")
    top_recurring_failures: List[EndpointFailureRecurrence] = Field(default_factory=list, description="Endpoints ranked by failure severity")
    failure_clusters: List[FailureCluster] = Field(default_factory=list, description="Discovered common root-cause clusters")
    analyzed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Analysis generation timestamp")


class AnalyzeHistoricalFailuresRequest(BaseModel):
    """Request payload for clustering and analyzing raw historical test samples."""
    samples: List[HistoricalExecutionSample] = Field(..., min_length=1, description="Historical execution records")
    project_name: Optional[str] = Field(default="Custom Dataset", description="Project or workspace label")
    window_size: int = Field(default=10, ge=2, le=100, description="Number of recent runs to evaluate for streaks")