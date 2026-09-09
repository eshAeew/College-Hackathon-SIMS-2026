"""Pydantic DTO models for Test Run Management and Orchestration."""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict


class RunStatus(str, Enum):
    """Lifecycle statuses for a Test Run."""
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class TestResultStatus(str, Enum):
    """Execution status for an individual test case."""
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"
    ERROR = "ERROR"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"


class TestRunCreateRequest(BaseModel):
    """Payload to initiate or schedule a new Test Run."""
    name: Optional[str] = Field(default=None, description="Optional custom name for the test run")
    environment: Optional[str] = Field(default="development", description="Execution environment preset")
    concurrency: int = Field(default=5, ge=1, le=50, description="Max concurrent request workers")
    tag_filter: Optional[str] = Field(default=None, description="Filter test cases by tag (e.g. 'smoke', 'regression')")
    test_case_ids: Optional[List[int]] = Field(default=None, description="Explicit list of test case IDs to run")
    endpoint_ids: Optional[List[int]] = Field(default=None, description="Filter test cases by endpoint IDs")
    execute_immediately: bool = Field(default=True, description="Whether to execute immediately or leave queued")

    model_config = ConfigDict(extra="forbid")


class TestRunCancelRequest(BaseModel):
    """Payload to cancel an ongoing or queued Test Run."""
    reason: Optional[str] = Field(default="Cancelled by user", description="Reason for cancellation")

    model_config = ConfigDict(extra="forbid")


class TestResultResponse(BaseModel):
    """Telemetry report for a single test case execution within a run."""
    id: int
    run_id: int
    test_case_id: Optional[int] = None
    endpoint_id: Optional[int] = None
    test_name: str
    http_method: str
    url: str
    status: TestResultStatus
    response_code: Optional[int] = None
    response_time_ms: Optional[float] = None
    response_body_snippet: Optional[str] = None
    response_headers: Dict[str, str] = Field(default_factory=dict)
    failure_type: Optional[str] = None
    failure_evidence: Dict[str, Any] = Field(default_factory=dict)
    executed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TestRunSummaryResponse(BaseModel):
    """High-level summary KPIs and status for a Test Run."""
    id: int
    project_id: int
    name: str
    status: RunStatus
    environment: str
    concurrency: int
    total_tests: int
    passed_tests: int
    failed_tests: int
    warning_tests: int
    error_tests: int
    pass_rate_pct: float
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_ms: float
    cancellation_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TestRunDetailResponse(TestRunSummaryResponse):
    """Detailed Test Run response including all individual test results."""
    results: List[TestResultResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
