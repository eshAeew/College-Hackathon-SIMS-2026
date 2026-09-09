"""Side-by-side run comparison and delta visualization service (Stage 21)."""
import logging
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.entities.test_result import TestResult
from app.models.entities.test_run import TestRun
from app.models.schemas.run_comparison import (
    ChangeKind,
    DeltaVisualization,
    RunComparisonReport,
    RunSnapshot,
)
from app.utils.run_comparator import (
    build_badges,
    build_latency_shift,
    build_metric_delta,
    build_test_change,
    decide_verdict,
)

logger = logging.getLogger("app.services.run_comparison")


def _run_pass_rate(run) -> float:
    """Derive a run pass rate from its counters (not a stored column)."""
    total = run.total_tests or 0
    if not total:
        return 0.0
    return round(((run.passed_tests or 0) / total) * 100.0, 2)


class RunComparisonService:
    """Compares two stored runs and renders the delta for the UI."""

    @staticmethod
    def _snapshot(run: TestRun, results: List[TestResult]) -> RunSnapshot:
        """Summarize one run into headline comparison metrics."""
        latencies = [r.response_time_ms for r in results if r.response_time_ms is not None]
        avg = round(sum(latencies) / len(latencies), 3) if latencies else 0.0
        return RunSnapshot(
            run_id=run.id,
            name=run.name,
            status=run.status,
            total_tests=run.total_tests or 0,
            passed_tests=run.passed_tests or 0,
            failed_tests=run.failed_tests or 0,
            warning_tests=run.warning_tests or 0,
            error_tests=run.error_tests or 0,
            pass_rate_pct=_run_pass_rate(run),
            avg_latency_ms=avg,
            duration_ms=round(run.duration_ms or 0.0, 2),
            executed_at=run.started_at,
        )

    @staticmethod
    def _index_results(results: List[TestResult]) -> Dict[str, Dict]:
        """Key results by test name so the two runs can be aligned."""
        indexed: Dict[str, Dict] = {}
        for row in results:
            indexed[row.test_name] = {
                "status": row.status,
                "status_code": row.response_code,
                "latency_ms": row.response_time_ms,
                "test_case_id": row.test_case_id,
                "endpoint_id": row.endpoint_id,
            }
        return indexed

    @classmethod
    def compare_runs(
        cls,
        db: Session,
        baseline_run_id: int,
        current_run_id: int,
        project_id: Optional[int] = None
    ) -> Optional[RunComparisonReport]:
        """Build the full comparison report between two persisted runs."""
        baseline_run = db.query(TestRun).filter(TestRun.id == baseline_run_id).first()
        current_run = db.query(TestRun).filter(TestRun.id == current_run_id).first()
        if not baseline_run or not current_run:
            return None

        baseline_results = db.query(TestResult).filter(TestResult.run_id == baseline_run_id).all()
        current_results = db.query(TestResult).filter(TestResult.run_id == current_run_id).all()

        baseline_index = cls._index_results(baseline_results)
        current_index = cls._index_results(current_results)

        changes = [
            build_test_change(name, baseline_index.get(name), current_index.get(name))
            for name in sorted(set(baseline_index) | set(current_index))
        ]

        broken = [c for c in changes if c.change == ChangeKind.BROKEN]
        fixed = [c for c in changes if c.change == ChangeKind.FIXED]
        slower = [c for c in changes if c.change == ChangeKind.SLOWER]
        faster = [c for c in changes if c.change == ChangeKind.FASTER]
        added = [c for c in changes if c.change == ChangeKind.ADDED]
        removed = [c for c in changes if c.change == ChangeKind.REMOVED]

        baseline_snapshot = cls._snapshot(baseline_run, baseline_results)
        current_snapshot = cls._snapshot(current_run, current_results)
        net_delta = round(current_snapshot.pass_rate_pct - baseline_snapshot.pass_rate_pct, 2)

        latency_shift = build_latency_shift(
            [r.response_time_ms for r in baseline_results if r.response_time_ms is not None],
            [r.response_time_ms for r in current_results if r.response_time_ms is not None],
        )

        has_crash = any(c.current_code is not None and c.current_code >= 500 for c in broken)
        verdict, headline = decide_verdict(len(broken), len(fixed), net_delta, has_crash)

        metric_deltas = [
            build_metric_delta("pass_rate_pct", baseline_snapshot.pass_rate_pct,
                               current_snapshot.pass_rate_pct, higher_is_better=True),
            build_metric_delta("passed_tests", baseline_snapshot.passed_tests,
                               current_snapshot.passed_tests, higher_is_better=True),
            build_metric_delta("failed_tests", baseline_snapshot.failed_tests,
                               current_snapshot.failed_tests, higher_is_better=False),
            build_metric_delta("error_tests", baseline_snapshot.error_tests,
                               current_snapshot.error_tests, higher_is_better=False),
            build_metric_delta("avg_latency_ms", baseline_snapshot.avg_latency_ms,
                               current_snapshot.avg_latency_ms, higher_is_better=False),
        ]

        logger.info(
            f"Compared Run #{baseline_run_id} -> #{current_run_id}: "
            f"{len(broken)} broken, {len(fixed)} fixed, verdict {verdict.value}"
        )

        return RunComparisonReport(
            project_id=project_id or current_run.project_id,
            baseline=baseline_snapshot,
            current=current_snapshot,
            metric_deltas=metric_deltas,
            changes=changes,
            latency_shift=latency_shift,
            broken_count=len(broken),
            fixed_count=len(fixed),
            slower_count=len(slower),
            faster_count=len(faster),
            added_count=len(added),
            removed_count=len(removed),
            net_quality_delta_pct=net_delta,
            verdict=verdict,
            headline=headline,
        )

    @classmethod
    def visualize(
        cls,
        db: Session,
        baseline_run_id: int,
        current_run_id: int
    ) -> Optional[DeltaVisualization]:
        """Render the comparison as the view-model consumed by the diff UI."""
        report = cls.compare_runs(db, baseline_run_id, current_run_id)
        if report is None:
            return None

        regressions = [
            c for c in report.changes
            if c.change in (ChangeKind.BROKEN, ChangeKind.STILL_FAILING, ChangeKind.SLOWER)
        ]
        improvements = [
            c for c in report.changes
            if c.change in (ChangeKind.FIXED, ChangeKind.FASTER)
        ]

        status_matrix: Dict[str, int] = {}
        for change in report.changes:
            status_matrix[change.change.value] = status_matrix.get(change.change.value, 0) + 1

        return DeltaVisualization(
            baseline_label=f"#{report.baseline.run_id} {report.baseline.name}",
            current_label=f"#{report.current.run_id} {report.current.name}",
            verdict=report.verdict,
            headline=report.headline,
            badges=build_badges(
                report.broken_count,
                report.fixed_count,
                report.slower_count,
                report.faster_count,
                report.net_quality_delta_pct,
                report.latency_shift,
            ),
            regressions=regressions,
            improvements=improvements,
            latency_shift=report.latency_shift,
            pass_rate_series={
                report.baseline.name: report.baseline.pass_rate_pct,
                report.current.name: report.current.pass_rate_pct,
            },
            status_matrix=status_matrix,
        )

    @staticmethod
    def latest_two_run_ids(db: Session, project_id: int) -> Optional[Tuple[int, int]]:
        """Return (baseline_id, current_id) for the two most recent runs of a project."""
        runs = (
            db.query(TestRun)
            .filter(TestRun.project_id == project_id)
            .order_by(TestRun.created_at.desc())
            .limit(2)
            .all()
        )
        if len(runs) < 2:
            return None
        return runs[1].id, runs[0].id
