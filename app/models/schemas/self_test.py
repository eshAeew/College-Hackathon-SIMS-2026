"""Pydantic schemas and DTOs for Platform Self-Testing Suite."""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SubsystemCategory(str, Enum):
    """Subsystem architectural categories for targeted self-testing."""
    CORE_FOUNDATION = "core_foundation"
    EXECUTION_ENGINE = "execution_engine"
    VALIDATION_ENGINE = "validation_engine"
    ANALYSIS_AI = "analysis_ai"
    RESILIENCE_DATA_AUDIT = "resilience_data_audit"
    FULL_SUITE = "full_suite"


class TestCaseResultDTO(BaseModel):
    """Execution outcome for an individual test case."""
    test_id: str = Field(..., description="Qualified method/test name")
    status: str = Field(..., description="Outcome: PASSED, FAILED, ERROR, SKIPPED")
    duration_ms: float = Field(..., description="Execution duration in milliseconds")
    error_message: Optional[str] = Field(None, description="Failure or error message if any")
    traceback: Optional[str] = Field(None, description="Traceback stack trace if failed")


class SubsystemSummaryDTO(BaseModel):
    """Aggregated test execution summary for a specific architectural subsystem."""
    subsystem: str
    total_tests: int
    passed: int
    failed: int
    errors: int
    skipped: int
    pass_rate: float
    duration_ms: float
    status: str  # HEALTHY, DEGRADED, FAILING


class SelfTestRunRequest(BaseModel):
    """Request payload to trigger self-testing execution."""
    subsystem: SubsystemCategory = Field(default=SubsystemCategory.FULL_SUITE, description="Target subsystem to test")
    stop_on_first_error: bool = Field(default=False, description="Whether to abort on first failure")
    include_tracebacks: bool = Field(default=True, description="Whether to include full error tracebacks")


class SelfTestRunResponse(BaseModel):
    """Comprehensive test execution report returned by SelfTestService."""
    run_id: str
    subsystem: str
    verdict: str  # ALL_PASSED, DEGRADED, FAILED
    total_tests: int
    passed: int
    failed: int
    errors: int
    skipped: int
    pass_rate: float
    total_duration_ms: float
    subsystems_breakdown: List[SubsystemSummaryDTO]
    failures: List[TestCaseResultDTO]
    executed_at: str


class SuiteMetadata(BaseModel):
    """Metadata describing an available subsystem test suite."""
    id: str
    name: str
    description: str
    test_files_count: int
    estimated_tests: int


class SubsystemHealthMatrixResponse(BaseModel):
    """Matrix of system readiness and test coverage across all architectural subsystems."""
    overall_system_status: str
    total_subsystems: int
    healthy_subsystems: int
    subsystems: List[SubsystemSummaryDTO]
    generated_at: str
