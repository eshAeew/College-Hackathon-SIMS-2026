"""Pydantic schemas and DTOs for the Dashboard & Web Interface (Stage 20)."""
from typing import List, Optional
from pydantic import BaseModel, Field


class GlobalKPISummary(BaseModel):
    """Aggregated global KPI metrics across all workspaces."""
    total_projects: int = Field(..., ge=0, description="Total registered projects / workspaces")
    total_endpoints: int = Field(..., ge=0, description="Total registered API endpoints")
    total_active_endpoints: int = Field(default=0, ge=0, description="Total active API endpoints")
    total_test_cases: int = Field(..., ge=0, description="Total registered test scenarios")
    total_assertions: int = Field(default=0, ge=0, description="Total active assertion checks across all test cases")
    total_test_runs: int = Field(..., ge=0, description="Total executed test runs")
    global_pass_rate_pct: float = Field(..., ge=0.0, le=100.0, description="Global test pass rate percentage")
    avg_latency_ms: float = Field(..., ge=0.0, description="Average response latency in milliseconds")
    p95_latency_ms: float = Field(..., ge=0.0, description="P95 response latency in milliseconds")
    active_critical_issues: int = Field(..., ge=0, description="Active 500 server crashes and broken tests")
    ai_remediations_count: int = Field(..., ge=0, description="Total AI & heuristic remediations generated")
    health_index_pct: float = Field(..., ge=0.0, le=100.0, description="Overall system health index")
    db_engine: str = Field(default="SQLite 3", description="Active database engine")
    ai_engine_status: str = Field(default="RULE_BASED_HEURISTIC", description="Current AI diagnostic mode")


class RecentTestRunCard(BaseModel):
    """Compact summary card for a recently executed test run."""
    id: int = Field(..., description="Test run ID")
    project_id: int = Field(..., description="Associated project ID")
    project_name: str = Field(..., description="Associated project name")
    name: str = Field(..., description="Test run suite name")
    status: str = Field(..., description="QUEUED | RUNNING | COMPLETED | CANCELLED | FAILED")
    environment: str = Field(..., description="Execution environment")
    total_tests: int = Field(..., ge=0, description="Total tests in run")
    passed_tests: int = Field(..., ge=0, description="Passed tests count")
    failed_tests: int = Field(..., ge=0, description="Failed tests count")
    pass_rate_pct: float = Field(..., ge=0.0, le=100.0, description="Run pass rate percentage")
    duration_ms: Optional[float] = Field(default=None, description="Execution duration in milliseconds")
    created_at: Optional[str] = Field(default=None, description="ISO timestamp of creation")


class CriticalIssueAlert(BaseModel):
    """High-priority failure or crash alert for dashboard feed."""
    evidence_id: str = Field(..., description="Diagnostic evidence ID")
    test_result_id: Optional[int] = Field(default=None, description="TestResult record ID")
    endpoint_method: str = Field(..., description="HTTP Method")
    endpoint_url: str = Field(..., description="Target URL")
    root_cause_category: str = Field(..., description="Root cause taxonomy category")
    severity: str = Field(..., description="CRITICAL | HIGH | MEDIUM | LOW")
    likely_cause: str = Field(..., description="Concise cause summary")
    suggested_fix: str = Field(..., description="Remediation instructions")
    code_snippet: Optional[str] = Field(default=None, description="Code fix snippet")
    source: str = Field(..., description="GEMINI_LLM | RULE_BASED_HEURISTIC")


class EndpointSummaryCard(BaseModel):
    """Compact summary of an endpoint for dashboard explorer."""
    id: int = Field(..., description="Endpoint ID")
    project_id: int = Field(..., description="Project ID")
    name: str = Field(..., description="Endpoint display name")
    http_method: str = Field(..., description="GET | POST | PUT | DELETE | PATCH")
    path: str = Field(..., description="Route path")
    target_sla_ms: float = Field(default=500.0, description="Configured SLA latency limit")
    is_active: bool = Field(default=True, description="Active toggle state")
    test_cases_count: int = Field(default=0, description="Number of registered test scenarios")


class ProjectDetailView(BaseModel):
    """Complete project detail bundle for drill-down views."""
    id: int = Field(..., description="Project ID")
    name: str = Field(..., description="Project name")
    base_url: str = Field(..., description="Base URL")
    environment: str = Field(..., description="Environment preset")
    description: Optional[str] = Field(default=None, description="Project description")
    endpoints: List[EndpointSummaryCard] = Field(default_factory=list, description="Registered endpoints")
    recent_runs: List[RecentTestRunCard] = Field(default_factory=list, description="Recent test runs for project")
    total_endpoints: int = Field(default=0, ge=0)
    total_test_cases: int = Field(default=0, ge=0)
    pass_rate_pct: float = Field(default=100.0, ge=0.0, le=100.0)


class DashboardOverviewResponse(BaseModel):
    """Top-level aggregated dashboard response payload."""
    kpi: GlobalKPISummary = Field(..., description="Global KPI summary metrics")
    recent_runs: List[RecentTestRunCard] = Field(default_factory=list, description="Recent test run cards")
    critical_issues: List[CriticalIssueAlert] = Field(default_factory=list, description="Active critical alerts")
    projects: List[ProjectDetailView] = Field(default_factory=list, description="All registered projects with endpoint counts")
