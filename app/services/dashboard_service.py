"""Aggregation service powering the dashboard and web interface (Stage 20)."""
import json
import logging
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.entities.endpoint import Endpoint
from app.models.entities.project import Project
from app.models.entities.test_case import TestCase
from app.models.entities.test_result import TestResult
from app.models.entities.test_run import TestRun
from app.models.schemas.dashboard import (
    AlertTone,
    CriticalIssue,
    EndpointHealthRow,
    EndpointInspector,
    GlobalDashboard,
    KpiCard,
    ProjectDashboard,
    RecentRunEntry,
    ResultDetailView,
)
from app.services.ai_recommendation_service import AIRecommendationService
from app.services.failure_analysis_service import FailureAnalysisService
from app.utils.contract_parser import extract_path_variables

logger = logging.getLogger("app.services.dashboard")

PASSING = {"PASS", "PASSED"}
CRITICAL_STATUSES = {"ERROR"}


def _pass_rate(results: List[TestResult]) -> float:
    """Percentage of results whose status counts as a pass."""
    if not results:
        return 0.0
    passed = sum(1 for r in results if (r.status or "").upper() in PASSING)
    return round((passed / len(results)) * 100.0, 2)


def _avg_latency(results: List[TestResult]) -> float:
    """Mean response time across results that recorded one."""
    values = [r.response_time_ms for r in results if r.response_time_ms is not None]
    return round(sum(values) / len(values), 2) if values else 0.0


def _tone_for_rate(rate: float) -> AlertTone:
    """Map a pass rate onto a display tone."""
    if rate >= 95.0:
        return AlertTone.SUCCESS
    if rate >= 75.0:
        return AlertTone.INFO
    if rate >= 50.0:
        return AlertTone.WARNING
    return AlertTone.CRITICAL


def _run_pass_rate(run: TestRun) -> float:
    """Derive a run pass rate from its counters (not a stored column)."""
    total = run.total_tests or 0
    if not total:
        return 0.0
    return round(((run.passed_tests or 0) / total) * 100.0, 2)


def _run_entry(run: TestRun, project_name: Optional[str] = None) -> RecentRunEntry:
    """Convert a TestRun row into a feed entry."""
    return RecentRunEntry(
        run_id=run.id,
        project_id=run.project_id,
        project_name=project_name,
        name=run.name,
        status=run.status,
        total_tests=run.total_tests or 0,
        passed_tests=run.passed_tests or 0,
        failed_tests=run.failed_tests or 0,
        error_tests=run.error_tests or 0,
        pass_rate_pct=_run_pass_rate(run),
        duration_ms=round(run.duration_ms or 0.0, 2),
        started_at=run.started_at,
    )


def _critical_issue(result: TestResult, project_id: Optional[int] = None) -> CriticalIssue:
    """Convert a failing result into an alert-banner entry."""
    code = result.response_code
    if code is not None and code >= 500:
        detail = f"Server crash: HTTP {code}"
        tone = AlertTone.CRITICAL
    elif (result.status or "").upper() == "ERROR":
        detail = f"Execution error: {result.failure_type or 'unknown'}"
        tone = AlertTone.CRITICAL
    else:
        detail = f"{result.status} (HTTP {code})" if code else str(result.status)
        tone = AlertTone.WARNING
    return CriticalIssue(
        result_id=result.id,
        run_id=result.run_id,
        project_id=project_id,
        test_name=result.test_name,
        http_method=result.http_method,
        url=result.url,
        status=result.status,
        response_code=code,
        failure_type=result.failure_type,
        tone=tone,
        detail=detail,
    )


class DashboardService:
    """Builds the aggregated view-models consumed by the web interface."""

    @staticmethod
    def global_dashboard(db: Session, recent_limit: int = 10) -> GlobalDashboard:
        """Aggregate KPIs, recent runs, and critical issues across all projects."""
        projects = db.query(Project).all()
        project_names = {p.id: p.name for p in projects}

        total_endpoints = db.query(Endpoint).count()
        total_test_cases = db.query(TestCase).count()
        runs = db.query(TestRun).order_by(TestRun.created_at.desc()).all()
        results = db.query(TestResult).all()

        pass_rate = _pass_rate(results)
        avg_latency = _avg_latency(results)

        status_distribution: Dict[str, int] = {}
        for row in results:
            key = (row.status or "UNKNOWN").upper()
            status_distribution[key] = status_distribution.get(key, 0) + 1

        active_failures = sum(
            count for status, count in status_distribution.items() if status not in PASSING
        )

        critical_rows = [
            r for r in results
            if (r.status or "").upper() in CRITICAL_STATUSES
            or (r.response_code is not None and r.response_code >= 500)
        ]

        kpi_cards = [
            KpiCard(key="total_tests", label="Total Executions", value=str(len(results)),
                    tone=AlertTone.INFO, hint="Test results recorded across all runs"),
            KpiCard(key="pass_rate", label="Global Pass Rate", value=f"{pass_rate:.1f}%",
                    tone=_tone_for_rate(pass_rate), hint="Share of executions that passed"),
            KpiCard(key="avg_latency", label="Avg Latency", value=f"{avg_latency:.0f} ms",
                    tone=AlertTone.WARNING if avg_latency > 1000 else AlertTone.SUCCESS,
                    hint="Mean response time across all executions"),
            KpiCard(key="active_failures", label="Active Failures", value=str(active_failures),
                    tone=AlertTone.CRITICAL if active_failures else AlertTone.SUCCESS,
                    hint="Executions not currently passing"),
        ]

        return GlobalDashboard(
            total_projects=len(projects),
            total_endpoints=total_endpoints,
            total_test_cases=total_test_cases,
            total_runs=len(runs),
            total_executions=len(results),
            global_pass_rate_pct=pass_rate,
            avg_latency_ms=avg_latency,
            active_failures=active_failures,
            kpi_cards=kpi_cards,
            recent_runs=[
                _run_entry(r, project_names.get(r.project_id)) for r in runs[:recent_limit]
            ],
            critical_issues=[_critical_issue(r) for r in critical_rows[:recent_limit]],
            status_distribution=status_distribution,
        )

    @staticmethod
    def project_dashboard(
        db: Session,
        project_id: int,
        recent_limit: int = 10
    ) -> Optional[ProjectDashboard]:
        """Build the project detail view with per-endpoint health rows."""
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return None

        endpoints = db.query(Endpoint).filter(Endpoint.project_id == project_id).all()
        endpoint_ids = [e.id for e in endpoints]
        runs = (
            db.query(TestRun)
            .filter(TestRun.project_id == project_id)
            .order_by(TestRun.created_at.desc())
            .all()
        )
        run_ids = [r.id for r in runs]
        results = (
            db.query(TestResult).filter(TestResult.run_id.in_(run_ids)).all()
            if run_ids else []
        )

        test_case_count = (
            db.query(TestCase).filter(TestCase.endpoint_id.in_(endpoint_ids)).count()
            if endpoint_ids else 0
        )

        rows: List[EndpointHealthRow] = []
        for endpoint in endpoints:
            ep_results = [r for r in results if r.endpoint_id == endpoint.id]
            rate = _pass_rate(ep_results)
            failures = sum(1 for r in ep_results if (r.status or "").upper() not in PASSING)
            rows.append(EndpointHealthRow(
                endpoint_id=endpoint.id,
                name=endpoint.name,
                method=endpoint.method,
                path=endpoint.path,
                is_active=endpoint.is_active,
                test_case_count=db.query(TestCase).filter(
                    TestCase.endpoint_id == endpoint.id
                ).count(),
                executions=len(ep_results),
                failures=failures,
                pass_rate_pct=rate,
                avg_latency_ms=_avg_latency(ep_results),
                tone=_tone_for_rate(rate) if ep_results else AlertTone.INFO,
            ))

        pass_rate = _pass_rate(results)
        avg_latency = _avg_latency(results)
        critical_rows = [
            r for r in results
            if (r.status or "").upper() in CRITICAL_STATUSES
            or (r.response_code is not None and r.response_code >= 500)
        ]

        kpi_cards = [
            KpiCard(key="endpoints", label="Endpoints", value=str(len(endpoints)),
                    tone=AlertTone.INFO, hint="Registered endpoints in this workspace"),
            KpiCard(key="test_cases", label="Test Cases", value=str(test_case_count),
                    tone=AlertTone.INFO, hint="Scenarios defined across all endpoints"),
            KpiCard(key="pass_rate", label="Pass Rate", value=f"{pass_rate:.1f}%",
                    tone=_tone_for_rate(pass_rate), hint="Across every recorded execution"),
            KpiCard(key="avg_latency", label="Avg Latency", value=f"{avg_latency:.0f} ms",
                    tone=AlertTone.WARNING if avg_latency > 1000 else AlertTone.SUCCESS,
                    hint="Mean response time in this project"),
        ]

        return ProjectDashboard(
            project_id=project.id,
            project_name=project.name,
            base_url=project.base_url,
            environment=project.environment,
            total_endpoints=len(endpoints),
            total_test_cases=test_case_count,
            total_runs=len(runs),
            latest_run=_run_entry(runs[0], project.name) if runs else None,
            pass_rate_pct=pass_rate,
            avg_latency_ms=avg_latency,
            kpi_cards=kpi_cards,
            endpoints=rows,
            recent_runs=[_run_entry(r, project.name) for r in runs[:recent_limit]],
            critical_issues=[
                _critical_issue(r, project_id) for r in critical_rows[:recent_limit]
            ],
        )

    @staticmethod
    def endpoint_inspector(
        db: Session,
        endpoint_id: int,
        recent_limit: int = 15
    ) -> Optional[EndpointInspector]:
        """Build the endpoint drill-down view."""
        endpoint = db.query(Endpoint).filter(Endpoint.id == endpoint_id).first()
        if not endpoint:
            return None

        cases = db.query(TestCase).filter(TestCase.endpoint_id == endpoint_id).all()
        results = (
            db.query(TestResult)
            .filter(TestResult.endpoint_id == endpoint_id)
            .order_by(TestResult.executed_at.desc())
            .limit(recent_limit)
            .all()
        )

        return EndpointInspector(
            endpoint_id=endpoint.id,
            project_id=endpoint.project_id,
            name=endpoint.name,
            method=endpoint.method,
            path=endpoint.path,
            is_active=endpoint.is_active,
            expected_status=endpoint.expected_status,
            headers=endpoint.headers,
            query_params=endpoint.query_params,
            path_variables=extract_path_variables(endpoint.path or ""),
            body_schema=endpoint.body_schema,
            response_schema=endpoint.response_schema,
            test_cases=[
                {
                    "id": c.id,
                    "name": c.name,
                    "tags": c.tags,
                    "severity": c.severity,
                    "is_active": c.is_active,
                    "assertions": c.assertions,
                }
                for c in cases
            ],
            recent_results=[
                {
                    "id": r.id,
                    "run_id": r.run_id,
                    "test_name": r.test_name,
                    "status": r.status,
                    "response_code": r.response_code,
                    "response_time_ms": r.response_time_ms,
                    "failure_type": r.failure_type,
                }
                for r in results
            ],
            pass_rate_pct=_pass_rate(list(results)),
            avg_latency_ms=_avg_latency(list(results)),
        )

    @staticmethod
    def result_detail(
        db: Session,
        result_id: int,
        include_recommendation: bool = True
    ) -> Optional[ResultDetailView]:
        """Combine a result, its evidence bundle, and its AI remediation card."""
        result = db.query(TestResult).filter(TestResult.id == result_id).first()
        if not result:
            return None

        evidence = FailureAnalysisService.package_from_result(db, result_id)
        recommendation = None
        if include_recommendation and evidence is not None:
            card = AIRecommendationService.generate(evidence, db=db, persist=False)
            recommendation = json.loads(card.model_dump_json())

        return ResultDetailView(
            result_id=result.id,
            run_id=result.run_id,
            test_name=result.test_name,
            status=result.status,
            http_method=result.http_method,
            url=result.url,
            response_code=result.response_code,
            response_time_ms=result.response_time_ms,
            failure_type=result.failure_type,
            evidence=json.loads(evidence.model_dump_json()) if evidence else None,
            recommendation=recommendation,
        )
