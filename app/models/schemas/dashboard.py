"""Pydantic DTOs backing the dashboard and web interface (Stage 20)."""
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AlertTone(str, Enum):
    """Severity tone for dashboard banners and badges."""
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    INFO = "INFO"
    SUCCESS = "SUCCESS"


class KpiCard(BaseModel):
    """A single headline metric tile."""
    key: str
    label: str
    value: str
    tone: AlertTone = AlertTone.INFO
    hint: str = ""


class RecentRunEntry(BaseModel):
    """One row in the recent-runs feed."""
    run_id: int
    project_id: Optional[int] = None
    project_name: Optional[str] = None
    name: str
    status: str
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    error_tests: int = 0
    pass_rate_pct: float = 0.0
    duration_ms: float = 0.0
    started_at: Optional[datetime] = None


class CriticalIssue(BaseModel):
    """An entry in the critical-issues alert banner."""
    result_id: Optional[int] = None
    run_id: Optional[int] = None
    project_id: Optional[int] = None
    test_name: str
    http_method: str = "GET"
    url: str = ""
    status: str = "ERROR"
    response_code: Optional[int] = None
    failure_type: Optional[str] = None
    tone: AlertTone = AlertTone.CRITICAL
    detail: str = ""


class GlobalDashboard(BaseModel):
    """Aggregate view across every registered project (sub-stage 20.01)."""
    total_projects: int = 0
    total_endpoints: int = 0
    total_test_cases: int = 0
    total_runs: int = 0
    total_executions: int = 0
    global_pass_rate_pct: float = 0.0
    avg_latency_ms: float = 0.0
    active_failures: int = 0
    kpi_cards: List[KpiCard] = Field(default_factory=list)
    recent_runs: List[RecentRunEntry] = Field(default_factory=list)
    critical_issues: List[CriticalIssue] = Field(default_factory=list)
    status_distribution: Dict[str, int] = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EndpointHealthRow(BaseModel):
    """Per-endpoint health summary inside a project view."""
    endpoint_id: int
    name: str
    method: str
    path: str
    is_active: bool = True
    test_case_count: int = 0
    executions: int = 0
    failures: int = 0
    pass_rate_pct: float = 0.0
    avg_latency_ms: float = 0.0
    tone: AlertTone = AlertTone.SUCCESS


class ProjectDashboard(BaseModel):
    """Deep-dive view for a single project (sub-stage 20.02)."""
    project_id: int
    project_name: str
    base_url: str = ""
    environment: str = "development"
    total_endpoints: int = 0
    total_test_cases: int = 0
    total_runs: int = 0
    latest_run: Optional[RecentRunEntry] = None
    pass_rate_pct: float = 0.0
    avg_latency_ms: float = 0.0
    kpi_cards: List[KpiCard] = Field(default_factory=list)
    endpoints: List[EndpointHealthRow] = Field(default_factory=list)
    recent_runs: List[RecentRunEntry] = Field(default_factory=list)
    critical_issues: List[CriticalIssue] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ResultDetailView(BaseModel):
    """Test-result inspector combining evidence and the AI remediation card."""
    result_id: int
    run_id: Optional[int] = None
    test_name: str
    status: str
    http_method: str = "GET"
    url: str = ""
    response_code: Optional[int] = None
    response_time_ms: Optional[float] = None
    failure_type: Optional[str] = None
    evidence: Optional[Dict[str, Any]] = None
    recommendation: Optional[Dict[str, Any]] = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EndpointInspector(BaseModel):
    """Endpoint drill-down: configuration, assertions, and historical results."""
    endpoint_id: int
    project_id: int
    name: str
    method: str
    path: str
    is_active: bool = True
    expected_status: int = 200
    headers: Dict[str, Any] = Field(default_factory=dict)
    query_params: Dict[str, Any] = Field(default_factory=dict)
    path_variables: List[str] = Field(default_factory=list)
    body_schema: Dict[str, Any] = Field(default_factory=dict)
    response_schema: Dict[str, Any] = Field(default_factory=dict)
    test_cases: List[Dict[str, Any]] = Field(default_factory=list)
    recent_results: List[Dict[str, Any]] = Field(default_factory=list)
    pass_rate_pct: float = 0.0
    avg_latency_ms: float = 0.0
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
