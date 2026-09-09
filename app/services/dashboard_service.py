"""Dashboard aggregation service powering the Web UI and summary metrics (Stage 20)."""
import logging
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.entities.project import Project
from app.models.entities.endpoint import Endpoint
from app.models.entities.test_case import TestCase
from app.models.entities.test_run import TestRun
from app.models.entities.test_result import TestResult
from app.models.entities.ai_recommendation import AIRecommendation
from app.models.schemas.dashboard import (
    CriticalIssueAlert,
    DashboardOverviewResponse,
    EndpointSummaryCard,
    GlobalKPISummary,
    ProjectDetailView,
    RecentTestRunCard,
)

logger = logging.getLogger("app.services.dashboard")


class DashboardService:
    """Multi-table aggregator delivering high-speed summary telemetry for the Web UI."""

    @classmethod
    def get_global_overview(cls, db: Session) -> DashboardOverviewResponse:
        """Calculate global platform KPIs, recent test runs, critical issues, and project listings."""
        total_projects = db.query(func.count(Project.id)).scalar() or 0
        total_endpoints = db.query(func.count(Endpoint.id)).scalar() or 0
        total_active_endpoints = db.query(func.count(Endpoint.id)).filter(Endpoint.is_active.is_(True)).scalar() or 0
        
        test_cases_all = db.query(TestCase).all()
        total_test_cases = len(test_cases_all)
        total_assertions = sum(len(tc.assertions) for tc in test_cases_all)
        
        total_test_runs = db.query(func.count(TestRun.id)).scalar() or 0
        total_remediations = db.query(func.count(AIRecommendation.id)).scalar() or 0

        # Run-level pass/fail statistics
        completed_runs = db.query(TestRun).filter(TestRun.status == "COMPLETED").all()
        total_tests_executed = sum(r.total_tests for r in completed_runs)
        total_tests_passed = sum(r.passed_tests for r in completed_runs)
        total_tests_failed = sum(r.failed_tests for r in completed_runs)

        if total_tests_executed > 0:
            pass_rate = round((total_tests_passed / total_tests_executed) * 100.0, 1)
        else:
            pass_rate = 100.0

        # Latency statistics from completed runs
        durations = [r.duration_ms for r in completed_runs if r.duration_ms is not None]
        if durations:
            avg_latency = round(sum(durations) / len(durations), 1)
            sorted_durations = sorted(durations)
            p95_idx = int(len(sorted_durations) * 0.95)
            p95_latency = round(sorted_durations[min(p95_idx, len(sorted_durations) - 1)], 1)
        else:
            avg_latency = 0.0
            p95_latency = 0.0

        # Active critical issues (remediations with CRITICAL or HIGH severity)
        crit_records = (
            db.query(AIRecommendation)
            .filter(AIRecommendation.severity.in_(["CRITICAL", "HIGH"]))
            .order_by(AIRecommendation.created_at.desc())
            .limit(10)
            .all()
        )
        critical_alerts: List[CriticalIssueAlert] = []
        for cr in crit_records:
            method = "UNKNOWN"
            url = "Ad-hoc Target"
            if cr.test_result:
                method = cr.test_result.http_method or "UNKNOWN"
                url = cr.test_result.url or "Ad-hoc Target"
            elif cr.test_result and cr.test_result.test_case and cr.test_result.test_case.endpoint:
                ep = cr.test_result.test_case.endpoint
                method = ep.method
                url = ep.path
            critical_alerts.append(
                CriticalIssueAlert(
                    evidence_id=cr.evidence_id,
                    test_result_id=cr.test_result_id,
                    endpoint_method=method,
                    endpoint_url=url,
                    root_cause_category=cr.root_cause_category,
                    severity=cr.severity,
                    likely_cause=cr.likely_cause,
                    suggested_fix=cr.suggested_fix,
                    code_snippet=cr.code_snippet,
                    source=cr.source,
                )
            )

        active_critical_issues = len(critical_alerts) + total_tests_failed

        # Health index computation: 100 - (failed_tests_weight + critical_issues_weight)
        health_penalty = min(total_tests_failed * 5.0 + active_critical_issues * 2.0, 100.0)
        health_index = round(max(100.0 - health_penalty, 0.0), 1)

        # Recent runs (top 10)
        recent_runs_db = db.query(TestRun).order_by(TestRun.created_at.desc()).limit(10).all()
        recent_run_cards: List[RecentTestRunCard] = []
        for r in recent_runs_db:
            proj_name = r.project.name if r.project else "Unknown Project"
            run_pr = round((r.passed_tests / r.total_tests * 100.0), 1) if r.total_tests > 0 else 100.0
            recent_run_cards.append(
                RecentTestRunCard(
                    id=r.id,
                    project_id=r.project_id,
                    project_name=proj_name,
                    name=r.name,
                    status=r.status,
                    environment=r.environment,
                    total_tests=r.total_tests,
                    passed_tests=r.passed_tests,
                    failed_tests=r.failed_tests,
                    pass_rate_pct=run_pr,
                    duration_ms=r.duration_ms,
                    created_at=r.created_at.isoformat() if r.created_at else None,
                )
            )

        # Projects list with detailed endpoints
        projects_db = db.query(Project).all()
        project_views: List[ProjectDetailView] = []
        for p in projects_db:
            ep_cards = [
                EndpointSummaryCard(
                    id=ep.id,
                    project_id=ep.project_id,
                    name=ep.name,
                    http_method=ep.method,
                    path=ep.path,
                    target_sla_ms=500.0,
                    is_active=ep.is_active,
                    test_cases_count=len(ep.test_cases) if ep.test_cases else 0,
                )
                for ep in p.endpoints
            ]
            tc_count = sum(c.test_cases_count for c in ep_cards)
            proj_runs = [r for r in completed_runs if r.project_id == p.id]
            proj_exec = sum(r.total_tests for r in proj_runs)
            proj_pass = sum(r.passed_tests for r in proj_runs)
            proj_pass_rate = round((proj_pass / proj_exec * 100.0), 1) if proj_exec > 0 else 100.0

            project_views.append(
                ProjectDetailView(
                    id=p.id,
                    name=p.name,
                    base_url=p.base_url,
                    environment=p.environment,
                    description=p.description,
                    endpoints=ep_cards,
                    total_endpoints=len(ep_cards),
                    total_test_cases=tc_count,
                    pass_rate_pct=proj_pass_rate,
                )
            )

        from app.core.config import get_settings
        app_settings = get_settings()
        ai_mode = "GEMINI_LLM" if (app_settings.GEMINI_API_KEY and app_settings.GEMINI_API_KEY.strip()) else "RULE_BASED_HEURISTIC"

        kpi = GlobalKPISummary(
            total_projects=total_projects,
            total_endpoints=total_endpoints,
            total_active_endpoints=total_active_endpoints,
            total_test_cases=total_test_cases,
            total_assertions=total_assertions,
            total_test_runs=total_test_runs,
            global_pass_rate_pct=pass_rate,
            avg_latency_ms=avg_latency,
            p95_latency_ms=p95_latency,
            active_critical_issues=active_critical_issues,
            ai_remediations_count=total_remediations,
            health_index_pct=health_index,
            db_engine="SQLite 3",
            ai_engine_status=ai_mode,
        )

        return DashboardOverviewResponse(
            kpi=kpi,
            recent_runs=recent_run_cards,
            critical_issues=critical_alerts,
            projects=project_views,
        )

    @classmethod
    def get_project_detail(cls, db: Session, project_id: int) -> Optional[ProjectDetailView]:
        """Retrieve granular project detail bundle for drill-down inspection."""
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return None

        ep_cards = [
            EndpointSummaryCard(
                id=ep.id,
                project_id=ep.project_id,
                name=ep.name,
                http_method=ep.method,
                path=ep.path,
                target_sla_ms=500.0,
                is_active=ep.is_active,
                test_cases_count=len(ep.test_cases) if ep.test_cases else 0,
            )
            for ep in project.endpoints
        ]
        tc_count = sum(c.test_cases_count for c in ep_cards)

        recent_runs_db = (
            db.query(TestRun)
            .filter(TestRun.project_id == project_id)
            .order_by(TestRun.created_at.desc())
            .limit(5)
            .all()
        )
        recent_runs = [
            RecentTestRunCard(
                id=r.id,
                project_id=r.project_id,
                project_name=project.name,
                name=r.name,
                status=r.status,
                environment=r.environment,
                total_tests=r.total_tests,
                passed_tests=r.passed_tests,
                failed_tests=r.failed_tests,
                pass_rate_pct=round((r.passed_tests / r.total_tests * 100.0), 1) if r.total_tests > 0 else 100.0,
                duration_ms=r.duration_ms,
                created_at=r.created_at.isoformat() if r.created_at else None,
            )
            for r in recent_runs_db
        ]

        proj_runs = (
            db.query(TestRun)
            .filter(TestRun.project_id == project_id, TestRun.status == "COMPLETED")
            .all()
        )
        proj_exec = sum(r.total_tests for r in proj_runs)
        proj_pass = sum(r.passed_tests for r in proj_runs)
        proj_pass_rate = round((proj_pass / proj_exec * 100.0), 1) if proj_exec > 0 else 100.0

        return ProjectDetailView(
            id=project.id,
            name=project.name,
            base_url=project.base_url,
            environment=project.environment,
            description=project.description,
            endpoints=ep_cards,
            recent_runs=recent_runs,
            total_endpoints=len(ep_cards),
            total_test_cases=tc_count,
            pass_rate_pct=proj_pass_rate,
        )
