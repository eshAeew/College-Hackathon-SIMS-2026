"""Service Layer for Stage 21: Run Comparison & Diff Tool."""
import logging
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session

from app.models.entities.test_run import TestRun
from app.models.entities.test_result import TestResult
from app.models.schemas.run_comparison import (
    DeltaStatus,
    DiffCategory,
    MetricDelta,
    RunComparisonMetrics,
    RunComparisonReport,
    RunHeaderSummary,
    TestCaseDiffItem,
)

logger = logging.getLogger("app.services.run_comparison")


class RunComparisonService:
    """Service computing granular execution deltas, side-by-side metric comparisons, and natural language insights."""

    @classmethod
    def compare_runs(
        cls,
        db: Session,
        base_run_id: int,
        target_run_id: int,
        latency_threshold_pct: float = 25.0,
        min_latency_delta_ms: float = 50.0
    ) -> RunComparisonReport:
        """Compare two TestRuns from the database side-by-side and return a comprehensive diff report."""
        base_run = db.query(TestRun).filter(TestRun.id == base_run_id).first()
        if not base_run:
            raise ValueError(f"Base TestRun #{base_run_id} not found.")

        target_run = db.query(TestRun).filter(TestRun.id == target_run_id).first()
        if not target_run:
            raise ValueError(f"Target TestRun #{target_run_id} not found.")

        # 1. Build Header Summaries
        base_header = cls._build_run_header(base_run)
        target_header = cls._build_run_header(target_run)

        # 2. Compute Metric Deltas
        metrics = cls._compute_metrics_table(base_run, target_run)

        # 3. Match & Categorize Individual Test Results
        base_results = db.query(TestResult).filter(TestResult.run_id == base_run_id).all()
        target_results = db.query(TestResult).filter(TestResult.run_id == target_run_id).all()

        diffs, counts = cls._compute_test_diffs(
            base_results=base_results,
            target_results=target_results,
            latency_threshold_pct=latency_threshold_pct,
            min_latency_delta_ms=min_latency_delta_ms
        )

        # 4. Generate Natural Language Insights
        insights = cls._generate_insights(metrics, counts, diffs)

        return RunComparisonReport(
            base_run=base_header,
            target_run=target_header,
            metrics=metrics,
            insights=insights,
            new_failures_count=counts["new_failures"],
            fixed_failures_count=counts["fixed_failures"],
            behavior_changed_count=counts["behavior_changed"],
            latency_degraded_count=counts["latency_degraded"],
            diffs=diffs
        )

    @classmethod
    def _build_run_header(cls, run: TestRun) -> RunHeaderSummary:
        """Construct header metadata DTO for a TestRun."""
        proj_name = run.project.name if run.project else "Unknown Project"
        pr = round((run.passed_tests / run.total_tests * 100.0), 1) if run.total_tests > 0 else 100.0
        avg_lat = round(run.duration_ms / run.total_tests, 1) if (run.duration_ms and run.total_tests > 0) else 0.0
        
        return RunHeaderSummary(
            id=run.id,
            project_id=run.project_id,
            project_name=proj_name,
            name=run.name,
            status=run.status,
            environment=run.environment,
            total_tests=run.total_tests,
            passed_tests=run.passed_tests,
            failed_tests=run.failed_tests,
            pass_rate_pct=pr,
            avg_latency_ms=avg_lat,
            created_at=run.created_at.isoformat() if run.created_at else None
        )

    @classmethod
    def _compute_metrics_table(cls, base: TestRun, target: TestRun) -> RunComparisonMetrics:
        """Calculate side-by-side metric deltas and directional statuses."""
        base_pr = round((base.passed_tests / base.total_tests * 100.0), 1) if base.total_tests > 0 else 100.0
        target_pr = round((target.passed_tests / target.total_tests * 100.0), 1) if target.total_tests > 0 else 100.0

        base_avg_lat = round(base.duration_ms / base.total_tests, 1) if (base.duration_ms and base.total_tests > 0) else 0.0
        target_avg_lat = round(target.duration_ms / target.total_tests, 1) if (target.duration_ms and target.total_tests > 0) else 0.0

        # P95 estimation from duration
        base_p95 = round(base_avg_lat * 1.3, 1) if base_avg_lat > 0 else 0.0
        target_p95 = round(target_avg_lat * 1.3, 1) if target_avg_lat > 0 else 0.0

        def make_delta(name: str, prev: float, curr: float, unit: str, lower_is_better: bool = False) -> MetricDelta:
            d = round(curr - prev, 1)
            pct = round((d / prev * 100.0), 1) if prev != 0 else (100.0 if d > 0 else (0.0 if d == 0 else -100.0))
            if d == 0:
                status = DeltaStatus.UNCHANGED
            elif lower_is_better:
                status = DeltaStatus.IMPROVED if d < 0 else DeltaStatus.DEGRADED
            else:
                status = DeltaStatus.IMPROVED if d > 0 else DeltaStatus.DEGRADED
            
            return MetricDelta(
                metric_name=name,
                previous=prev,
                current=curr,
                delta=d,
                delta_pct=pct,
                status=status,
                unit=unit
            )

        return RunComparisonMetrics(
            total_tests=make_delta("Tests", float(base.total_tests), float(target.total_tests), "tests"),
            passed_tests=make_delta("Passed", float(base.passed_tests), float(target.passed_tests), "tests"),
            failed_tests=make_delta("Failed", float(base.failed_tests), float(target.failed_tests), "tests", lower_is_better=True),
            pass_rate=make_delta("Success rate", base_pr, target_pr, "%"),
            avg_latency=make_delta("Avg latency", base_avg_lat, target_avg_lat, "ms", lower_is_better=True),
            p95_latency=make_delta("P95 latency", base_p95, target_p95, "ms", lower_is_better=True)
        )

    @classmethod
    def _compute_test_diffs(
        cls,
        base_results: List[TestResult],
        target_results: List[TestResult],
        latency_threshold_pct: float,
        min_latency_delta_ms: float
    ) -> Tuple[List[TestCaseDiffItem], Dict[str, int]]:
        """Map tests by key signature and categorize transitions."""
        diff_items: List[TestCaseDiffItem] = []
        counts = {
            "new_failures": 0,
            "fixed_failures": 0,
            "behavior_changed": 0,
            "latency_degraded": 0,
        }

        # Index base results by signature: (test_case_id, http_method, url, test_name)
        def make_key(r: TestResult) -> str:
            if r.test_case_id:
                return f"tc:{r.test_case_id}"
            return f"sig:{r.http_method}:{r.url}:{r.test_name}"

        base_map = {make_key(r): r for r in base_results}
        target_map = {make_key(r): r for r in target_results}

        all_keys = list(dict.fromkeys(list(base_map.keys()) + list(target_map.keys())))

        for k in all_keys:
            base_r = base_map.get(k)
            target_r = target_map.get(k)

            if base_r and not target_r:
                # Removed Test
                diff_items.append(
                    TestCaseDiffItem(
                        test_case_id=base_r.test_case_id,
                        test_name=base_r.test_name,
                        http_method=base_r.http_method,
                        url=base_r.url,
                        previous_status=base_r.status,
                        current_status=None,
                        previous_status_code=base_r.response_code,
                        current_status_code=None,
                        previous_latency_ms=base_r.response_time_ms,
                        current_latency_ms=None,
                        latency_delta_ms=None,
                        category=DiffCategory.REMOVED_TEST,
                        detail_message=f"Test '{base_r.test_name}' was executed in base run but omitted in target run."
                    )
                )
            elif not base_r and target_r:
                # New Test
                category = DiffCategory.NEW_FAILURE if target_r.status in ["FAIL", "ERROR"] else DiffCategory.NEW_TEST
                if category == DiffCategory.NEW_FAILURE:
                    counts["new_failures"] += 1
                diff_items.append(
                    TestCaseDiffItem(
                        test_case_id=target_r.test_case_id,
                        test_name=target_r.test_name,
                        http_method=target_r.http_method,
                        url=target_r.url,
                        previous_status=None,
                        current_status=target_r.status,
                        previous_status_code=None,
                        current_status_code=target_r.response_code,
                        previous_latency_ms=None,
                        current_latency_ms=target_r.response_time_ms,
                        latency_delta_ms=None,
                        category=category,
                        detail_message=f"Newly added test '{target_r.test_name}' executed with status {target_r.status}."
                    )
                )
            else:
                # Present in both runs
                prev_st = base_r.status
                curr_st = target_r.status
                prev_code = base_r.response_code
                curr_code = target_r.response_code
                prev_lat = base_r.response_time_ms or 0.0
                curr_lat = target_r.response_time_ms or 0.0
                lat_delta = round(curr_lat - prev_lat, 2)

                lat_pct_increase = ((curr_lat - prev_lat) / prev_lat * 100.0) if prev_lat > 0 else 0.0

                # 1. Check for New Failure (Regression)
                if prev_st in ["PASS", "WARNING"] and curr_st in ["FAIL", "ERROR"]:
                    counts["new_failures"] += 1
                    diff_items.append(
                        TestCaseDiffItem(
                            test_case_id=target_r.test_case_id,
                            test_name=target_r.test_name,
                            http_method=target_r.http_method,
                            url=target_r.url,
                            previous_status=prev_st,
                            current_status=curr_st,
                            previous_status_code=prev_code,
                            current_status_code=curr_code,
                            previous_latency_ms=prev_lat,
                            current_latency_ms=curr_lat,
                            latency_delta_ms=lat_delta,
                            category=DiffCategory.NEW_FAILURE,
                            detail_message=f"Regression detected: Status changed from {prev_st} ({prev_code}) to {curr_st} ({curr_code})."
                        )
                    )
                # 2. Check for Fixed Failure
                elif prev_st in ["FAIL", "ERROR"] and curr_st in ["PASS", "WARNING"]:
                    counts["fixed_failures"] += 1
                    diff_items.append(
                        TestCaseDiffItem(
                            test_case_id=target_r.test_case_id,
                            test_name=target_r.test_name,
                            http_method=target_r.http_method,
                            url=target_r.url,
                            previous_status=prev_st,
                            current_status=curr_st,
                            previous_status_code=prev_code,
                            current_status_code=curr_code,
                            previous_latency_ms=prev_lat,
                            current_latency_ms=curr_lat,
                            latency_delta_ms=lat_delta,
                            category=DiffCategory.FIXED_FAILURE,
                            detail_message=f"Issue resolved: Status improved from {prev_st} ({prev_code}) to {curr_st} ({curr_code})."
                        )
                    )
                # 3. Check for Behavior Changed (Different response status code or error type)
                elif prev_code != curr_code and prev_code is not None and curr_code is not None:
                    counts["behavior_changed"] += 1
                    diff_items.append(
                        TestCaseDiffItem(
                            test_case_id=target_r.test_case_id,
                            test_name=target_r.test_name,
                            http_method=target_r.http_method,
                            url=target_r.url,
                            previous_status=prev_st,
                            current_status=curr_st,
                            previous_status_code=prev_code,
                            current_status_code=curr_code,
                            previous_latency_ms=prev_lat,
                            current_latency_ms=curr_lat,
                            latency_delta_ms=lat_delta,
                            category=DiffCategory.BEHAVIOR_CHANGED,
                            detail_message=f"Behavior changed: HTTP status code shifted from {prev_code} to {curr_code}."
                        )
                    )
                # 4. Check for Latency Degradation
                elif lat_pct_increase >= latency_threshold_pct and lat_delta >= min_latency_delta_ms:
                    counts["latency_degraded"] += 1
                    diff_items.append(
                        TestCaseDiffItem(
                            test_case_id=target_r.test_case_id,
                            test_name=target_r.test_name,
                            http_method=target_r.http_method,
                            url=target_r.url,
                            previous_status=prev_st,
                            current_status=curr_st,
                            previous_status_code=prev_code,
                            current_status_code=curr_code,
                            previous_latency_ms=prev_lat,
                            current_latency_ms=curr_lat,
                            latency_delta_ms=lat_delta,
                            category=DiffCategory.LATENCY_DEGRADED,
                            detail_message=f"Latency degraded by +{lat_delta:.1f}ms (+{lat_pct_increase:.1f}%)."
                        )
                    )
                # 5. Unchanged State
                elif curr_st in ["FAIL", "ERROR"]:
                    diff_items.append(
                        TestCaseDiffItem(
                            test_case_id=target_r.test_case_id,
                            test_name=target_r.test_name,
                            http_method=target_r.http_method,
                            url=target_r.url,
                            previous_status=prev_st,
                            current_status=curr_st,
                            previous_status_code=prev_code,
                            current_status_code=curr_code,
                            previous_latency_ms=prev_lat,
                            current_latency_ms=curr_lat,
                            latency_delta_ms=lat_delta,
                            category=DiffCategory.UNCHANGED_FAIL,
                            detail_message=f"Persistent failure: Failed in both runs with status {curr_code}."
                        )
                    )
                else:
                    diff_items.append(
                        TestCaseDiffItem(
                            test_case_id=target_r.test_case_id,
                            test_name=target_r.test_name,
                            http_method=target_r.http_method,
                            url=target_r.url,
                            previous_status=prev_st,
                            current_status=curr_st,
                            previous_status_code=prev_code,
                            current_status_code=curr_code,
                            previous_latency_ms=prev_lat,
                            current_latency_ms=curr_lat,
                            latency_delta_ms=lat_delta,
                            category=DiffCategory.UNCHANGED_PASS,
                            detail_message="Stable pass across both runs."
                        )
                    )

        return diff_items, counts

    @classmethod
    def _generate_insights(
        cls,
        metrics: RunComparisonMetrics,
        counts: Dict[str, int],
        diffs: List[TestCaseDiffItem]
    ) -> List[str]:
        """Synthesize natural language insight bullet points."""
        insights: List[str] = []

        # 1. New Failures Insight
        if counts["new_failures"] > 0:
            insights.append(f"{counts['new_failures']} new failure(s) detected (regressions introduced).")
        elif metrics.failed_tests.delta < 0:
            insights.append(f"{int(abs(metrics.failed_tests.delta))} failure(s) resolved since previous run.")
        else:
            insights.append("Zero new regressions detected.")

        # 2. Latency Drift Insight
        lat_delta = metrics.avg_latency.delta
        if lat_delta > 0:
            insights.append(f"Average latency increased by {lat_delta:.1f}ms ({metrics.avg_latency.delta_pct:+.1f}%).")
        elif lat_delta < 0:
            insights.append(f"Average latency improved by {abs(lat_delta):.1f}ms ({metrics.avg_latency.delta_pct:.1f}%).")
        else:
            insights.append("Average latency remained stable across executions.")

        # 3. Behavior Shift Insight
        if counts["behavior_changed"] > 0:
            insights.append(f"{counts['behavior_changed']} existing test(s) changed behavior (HTTP status code drift).")

        # 4. Pass Rate Trend Insight
        pr_delta = metrics.pass_rate.delta
        if pr_delta < 0:
            insights.append(f"Overall test pass rate dropped by {abs(pr_delta):.1f}% (from {metrics.pass_rate.previous}% to {metrics.pass_rate.current}%).")
        elif pr_delta > 0:
            insights.append(f"Overall test pass rate improved by +{pr_delta:.1f}% (from {metrics.pass_rate.previous}% to {metrics.pass_rate.current}%).")

        return insights
