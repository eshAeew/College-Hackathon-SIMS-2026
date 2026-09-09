"""Service Layer for Baseline Comparison & Regression Testing Engine (Stage 13)."""
import logging
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.orm import Session

from app.models.entities.project import Project
from app.models.entities.test_run import TestRun
from app.models.entities.test_result import TestResult
from app.models.schemas.regression import (
    ComparisonExecutionItem,
    DirectRegressionComparisonRequest,
    ProjectRegressionReport,
    RegressionItem,
    RegressionSummaryCard,
    RegressionVerdict,
)
from app.utils.regression_comparator import compare_execution_results

logger = logging.getLogger("app.services.regression")


class RegressionService:
    """Service orchestrating delta comparisons between runs and flagging regressions."""

    @classmethod
    def compare_direct_batches(
        cls,
        req: DirectRegressionComparisonRequest
    ) -> ProjectRegressionReport:
        """Compare arbitrary execution batches directly."""
        summary, regressions, improvements, stable_items = compare_execution_results(
            baseline_items=req.baseline_results,
            current_items=req.current_results,
            latency_threshold_pct=req.latency_degradation_threshold_pct,
            min_latency_delta_ms=req.min_latency_delta_ms
        )

        return ProjectRegressionReport(
            project_id=None,
            baseline_run_id=None,
            baseline_run_name=req.baseline_run_name,
            baseline_run_date=datetime.now(timezone.utc),
            current_run_id=None,
            current_run_name=req.current_run_name,
            current_run_date=datetime.now(timezone.utc),
            summary=summary,
            regressions=regressions,
            improvements=improvements,
            stable_items=stable_items
        )

    @classmethod
    def compare_runs_by_id(
        cls,
        current_run_id: int,
        db: Session,
        baseline_run_id: Optional[int] = None,
        latency_threshold_pct: float = 50.0,
        min_latency_delta_ms: float = 50.0
    ) -> ProjectRegressionReport:
        """
        Compare a current TestRun against an explicit baseline run or the preceding successful run.
        """
        current_run = db.query(TestRun).filter(TestRun.id == current_run_id).first()
        if not current_run:
            raise ValueError(f"Target TestRun #{current_run_id} not found.")

        # Resolve Baseline Run
        baseline_run = None
        if baseline_run_id:
            baseline_run = db.query(TestRun).filter(TestRun.id == baseline_run_id).first()
            if not baseline_run:
                raise ValueError(f"Specified Baseline TestRun #{baseline_run_id} not found.")
        else:
            # Auto-detect previous successful completed run in the same project
            baseline_run = db.query(TestRun).filter(
                TestRun.project_id == current_run.project_id,
                TestRun.id < current_run.id,
                TestRun.status == "COMPLETED",
                TestRun.passed_tests > 0
            ).order_by(TestRun.id.desc()).first()

        # Convert TestResults into ComparisonExecutionItems
        current_items = [
            ComparisonExecutionItem(
                test_case_id=r.test_case_id,
                endpoint_id=r.endpoint_id,
                test_name=r.test_name,
                status=r.status,
                status_code=r.response_code,
                response_time_ms=r.response_time_ms or 0.0,
                failure_type=r.failure_type,
                failure_message=str(r.failure_evidence.get("summary")) if r.failure_evidence else None
            )
            for r in current_run.test_results
        ]

        baseline_items = []
        if baseline_run:
            baseline_items = [
                ComparisonExecutionItem(
                    test_case_id=r.test_case_id,
                    endpoint_id=r.endpoint_id,
                    test_name=r.test_name,
                    status=r.status,
                    status_code=r.response_code,
                    response_time_ms=r.response_time_ms or 0.0,
                    failure_type=r.failure_type,
                    failure_message=str(r.failure_evidence.get("summary")) if r.failure_evidence else None
                )
                for r in baseline_run.test_results
            ]

        summary, regressions, improvements, stable_items = compare_execution_results(
            baseline_items=baseline_items,
            current_items=current_items,
            latency_threshold_pct=latency_threshold_pct,
            min_latency_delta_ms=min_latency_delta_ms
        )

        return ProjectRegressionReport(
            project_id=current_run.project_id,
            baseline_run_id=baseline_run.id if baseline_run else None,
            baseline_run_name=baseline_run.name if baseline_run else "No Prior Baseline",
            baseline_run_date=baseline_run.finished_at if baseline_run else None,
            current_run_id=current_run.id,
            current_run_name=current_run.name,
            current_run_date=current_run.finished_at or current_run.created_at,
            summary=summary,
            regressions=regressions,
            improvements=improvements,
            stable_items=stable_items
        )

    @classmethod
    def get_latest_project_regression(
        cls,
        project_id: int,
        db: Session,
        latency_threshold_pct: float = 50.0
    ) -> ProjectRegressionReport:
        """Find the most recent run for a project and compare against its baseline."""
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError(f"Project #{project_id} not found.")

        latest_run = db.query(TestRun).filter(
            TestRun.project_id == project_id
        ).order_by(TestRun.id.desc()).first()

        if not latest_run:
            raise ValueError(f"No test runs exist for Project #{project_id}.")

        return cls.compare_runs_by_id(
            current_run_id=latest_run.id,
            db=db,
            latency_threshold_pct=latency_threshold_pct
        )
