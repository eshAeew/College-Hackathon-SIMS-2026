"""Reporting & Export Engine Service (Stage 22)."""
import logging
from typing import List, Optional
from datetime import datetime, timezone
import numpy as np
from sqlalchemy.orm import Session

from app.models.entities.test_run import TestRun
from app.models.entities.test_result import TestResult
from app.models.entities.project import Project
from app.models.entities.endpoint import Endpoint
from app.models.entities.ai_recommendation import AIRecommendation
from app.models.schemas.report import (
    ActionableRecommendationItem,
    ComprehensiveTestReport,
    ExecutiveSummary,
    FunctionalFailureItem,
    FunctionalReportSection,
    PerformanceReportSection,
    RecommendationsSection,
    RecurringFailureItem,
    RecurringFailuresSection,
    RegressionItem,
    RegressionReportSection,
    ReportVerdict,
    SlowEndpointItem,
)
from app.services.ai_recommendation_service import AIRecommendationService
from app.services.run_comparison_service import RunComparisonService
from app.utils.evidence_packager import build_curl_command

logger = logging.getLogger("app.services.report")


class ReportService:
    """Service generating comprehensive, multi-format test execution reports."""

    @classmethod
    def generate_report(
        cls,
        run_id: int,
        db: Session,
        baseline_run_id: Optional[int] = None
    ) -> ComprehensiveTestReport:
        """
        Synthesize a 6-section comprehensive diagnostic test report for a target TestRun.
        """
        test_run = db.query(TestRun).filter(TestRun.id == run_id).first()
        if not test_run:
            raise ValueError(f"TestRun #{run_id} not found.")

        project = db.query(Project).filter(Project.id == test_run.project_id).first()
        proj_name = project.name if project else f"Project #{test_run.project_id}"

        results = db.query(TestResult).filter(TestResult.run_id == run_id).all()
        total_tests = len(results)

        # 1. Executive Summary
        passed_count = sum(1 for r in results if r.status == "PASS")
        failed_count = sum(1 for r in results if r.status in ["FAIL", "ERROR"])
        warning_count = sum(1 for r in results if r.status == "WARNING")
        error_count = sum(1 for r in results if r.status == "ERROR")
        skipped_count = sum(1 for r in results if r.status in ["SKIPPED", "CANCELLED"])

        pass_rate = round((passed_count / total_tests * 100.0), 1) if total_tests > 0 else 100.0

        if failed_count == 0 and error_count == 0:
            verdict = ReportVerdict.PASS
        elif pass_rate >= 50.0:
            verdict = ReportVerdict.DEGRADED
        else:
            verdict = ReportVerdict.FAIL


        summary = ExecutiveSummary(
            project_id=test_run.project_id,
            project_name=proj_name,
            run_id=test_run.id,
            run_name=test_run.name,
            environment=test_run.environment or "development",
            started_at=test_run.started_at.isoformat() if test_run.started_at else None,
            finished_at=test_run.finished_at.isoformat() if test_run.finished_at else None,
            duration_ms=round(test_run.duration_ms, 1) if test_run.duration_ms is not None else 0.0,
            total_tests=total_tests,
            passed_tests=passed_count,
            failed_tests=failed_count,
            pass_rate_pct=pass_rate,
            verdict=verdict,
        )

        # 2. Functional Results Section
        failure_items: List[FunctionalFailureItem] = []
        for r in results:
            if r.status in ["FAIL", "ERROR", "WARNING"]:
                tc = r.test_case
                ep = tc.endpoint if tc else r.endpoint
                ep_method = r.http_method or (ep.method if ep else "GET")
                ep_path = (ep.path if ep else None) or r.url or "/"

                
                evidence = r.failure_evidence or {}
                fail_summary = evidence.get("summary") or evidence.get("message") or evidence.get("exception") or "Assertion or validation check failed"
                
                failure_items.append(
                    FunctionalFailureItem(
                        test_result_id=r.id,
                        test_name=r.test_name or "Unnamed Test",
                        endpoint_method=ep_method,
                        endpoint_path=ep_path,
                        url=r.url or ep_path,
                        status=r.status,
                        response_code=r.response_code,
                        latency_ms=r.response_time_ms,
                        failure_type=r.failure_type or "FUNCTIONAL_FAILURE",
                        failure_summary=fail_summary
                    )
                )

        functional = FunctionalReportSection(
            total_tests=total_tests,
            passed_count=passed_count,
            failed_count=failed_count,
            warning_count=warning_count,
            error_count=error_count,
            skipped_count=skipped_count,
            pass_rate_pct=pass_rate,
            failures=failure_items
        )

        # 3. Performance Report Section
        durations = [r.response_time_ms for r in results if r.response_time_ms is not None and r.response_time_ms >= 0]
        if durations:
            avg_lat = round(float(np.mean(durations)), 1)
            p50_lat = round(float(np.percentile(durations, 50)), 1)
            p90_lat = round(float(np.percentile(durations, 90)), 1)
            p95_lat = round(float(np.percentile(durations, 95)), 1)
            p99_lat = round(float(np.percentile(durations, 99)), 1)
            max_lat = round(float(np.max(durations)), 1)
            min_lat = round(float(np.min(durations)), 1)
        else:
            avg_lat = p50_lat = p90_lat = p95_lat = p99_lat = max_lat = min_lat = 0.0

        slow_endpoints: List[SlowEndpointItem] = []
        for r in results:
            if r.response_time_ms is not None:
                ep = (r.test_case.endpoint if r.test_case else None) or r.endpoint
                target_sla = 500.0  # Default 500ms
                if r.response_time_ms > target_sla:
                    slow_endpoints.append(
                        SlowEndpointItem(
                            endpoint_method=r.http_method or "GET",
                            endpoint_path=ep.path if ep else r.url,
                            latency_ms=round(r.response_time_ms, 1),
                            target_sla_ms=target_sla,
                            sla_breach_ms=round(r.response_time_ms - target_sla, 1)
                        )
                    )

        performance = PerformanceReportSection(
            avg_latency_ms=avg_lat,
            p50_latency_ms=p50_lat,
            p90_latency_ms=p90_lat,
            p95_latency_ms=p95_lat,
            p99_latency_ms=p99_lat,
            max_latency_ms=max_lat,
            min_latency_ms=min_lat,
            sla_breach_count=len(slow_endpoints),
            slow_endpoints=slow_endpoints
        )

        # 4. Recurring Failures Section
        prior_runs = (
            db.query(TestRun)
            .filter(TestRun.project_id == test_run.project_id, TestRun.id < run_id)
            .order_by(TestRun.id.desc())
            .limit(5)
            .all()
        )
        recurring_items: List[RecurringFailureItem] = []
        if prior_runs:
            prior_run_ids = [pr.id for pr in prior_runs]
            prior_fails = db.query(TestResult).filter(
                TestResult.run_id.in_(prior_run_ids),
                TestResult.status.in_(["FAIL", "ERROR"])
            ).all()

            # Group prior fails by (test_name, http_method)
            prior_fail_map = {}
            for pf in prior_fails:
                key = (pf.test_name, pf.http_method)
                prior_fail_map[key] = prior_fail_map.get(key, 0) + 1

            for curr_fail in failure_items:
                key = (curr_fail.test_name, curr_fail.endpoint_method)
                if key in prior_fail_map:
                    hist_count = prior_fail_map[key] + 1
                    persistence = "CHRONIC" if hist_count >= 3 else "INTERMITTENT"
                    recurring_items.append(
                        RecurringFailureItem(
                            fingerprint=f"REC-{abs(hash(key)) % 100000:05d}",
                            endpoint_method=curr_fail.endpoint_method,
                            endpoint_path=curr_fail.endpoint_path,
                            occurrence_count=hist_count,
                            persistence_rating=persistence,
                            root_cause_hint=f"Observed across {hist_count} test executions in this workspace."
                        )
                    )

        recurring_section = RecurringFailuresSection(
            total_recurring_patterns=len(recurring_items),
            patterns=recurring_items
        )

        # 5. Regression Section
        if baseline_run_id is None and prior_runs:
            baseline_run_id = prior_runs[0].id

        regression_items: List[RegressionItem] = []
        new_fail_count = 0
        latency_reg_count = 0

        if baseline_run_id:
            try:
                diff_report = RunComparisonService.compare_runs(baseline_run_id, run_id, db)
                for d in diff_report.diffs:
                    if d.category in ["NEW_FAILURE", "BEHAVIOR_CHANGED", "LATENCY_DEGRADED"]:
                        if d.category == "NEW_FAILURE":
                            new_fail_count += 1
                        if d.category == "LATENCY_DEGRADED":
                            latency_reg_count += 1

                        regression_items.append(
                            RegressionItem(
                                test_case_id=d.test_case_id,
                                test_name=d.test_name,
                                endpoint_method=d.endpoint_method,
                                endpoint_path=d.endpoint_path,
                                baseline_status=d.previous_status,
                                current_status=d.current_status,
                                category=d.category.value,
                                details=d.insight
                            )
                        )
            except Exception as e:
                logger.warning(f"Could not compute regression diff for run #{run_id}: {e}")

        regression_section = RegressionReportSection(
            baseline_run_id=baseline_run_id,
            new_failures_count=new_fail_count,
            latency_regressions_count=latency_reg_count,
            regressions=regression_items
        )

        # 6. Actionable Recommendations Section
        recommendation_items: List[ActionableRecommendationItem] = []
        for r in results:
            if r.status in ["FAIL", "ERROR", "WARNING"]:
                recs = AIRecommendationService.for_result(db, r.id)
                if not recs:
                    try:
                        rec_dto = AIRecommendationService.recommend_for_result(db, r.id, persist=True)
                        if rec_dto:
                            recs = AIRecommendationService.for_result(db, r.id)
                    except Exception as e:
                        logger.debug(f"Could not generate recommendation for result #{r.id}: {e}")

                for rec in recs:
                    ep = (r.test_case.endpoint if r.test_case else None) or r.endpoint
                    method = r.http_method or (ep.method if ep else "GET")
                    path = (ep.path if ep else None) or r.url or "/"

                    
                    curl_cmd = build_curl_command(
                        http_method=method,
                        url=r.url or path,
                        headers=r.response_headers or {}
                    )

                    recommendation_items.append(
                        ActionableRecommendationItem(
                            evidence_id=rec.evidence_id,
                            test_result_id=r.id,
                            endpoint_method=method,
                            endpoint_path=path,
                            root_cause_category=rec.root_cause_category,
                            severity=rec.severity,
                            likely_cause=rec.likely_cause,
                            suggested_fix=rec.suggested_fix,
                            reproducible_curl=curl_cmd,
                            code_snippet=rec.code_snippet,
                            source=rec.source
                        )
                    )

        crit_recs = sum(1 for rc in recommendation_items if rc.severity == "CRITICAL")
        high_recs = sum(1 for rc in recommendation_items if rc.severity == "HIGH")

        recommendations_section = RecommendationsSection(
            total_recommendations=len(recommendation_items),
            critical_count=crit_recs,
            high_count=high_recs,
            recommendations=recommendation_items
        )

        return ComprehensiveTestReport(
            generated_at=datetime.now(timezone.utc).isoformat(),
            summary=summary,
            functional=functional,
            performance=performance,
            recurring_failures=recurring_section,
            regressions=regression_section,
            recommendations=recommendations_section
        )

    @classmethod
    def generate_markdown_report(cls, report: ComprehensiveTestReport) -> str:
        """Render a GitHub-flavored Markdown test execution report."""
        s = report.summary
        f = report.functional
        p = report.performance
        r = report.regressions
        rec = report.recommendations
        rf = report.recurring_failures

        verdict_badge = "🟢 **PASSED**" if s.verdict == ReportVerdict.PASS else ("🟡 **DEGRADED**" if s.verdict == ReportVerdict.DEGRADED else "🔴 **FAILED**")

        lines = [
            f"# 🛡️ API Sentinel — Test Execution Report",
            f"**Generated:** `{report.generated_at}` | **Verdict:** {verdict_badge}",
            "",
            "## 1. Executive Summary",
            f"- **Project Workspace:** `{s.project_name}` (ID #{s.project_id})",
            f"- **Test Run:** `{s.run_name}` (Run #{s.run_id})",
            f"- **Environment:** `{s.environment.upper()}`",
            f"- **Duration:** `{s.duration_ms}ms`",
            f"- **Success Rate:** **{s.pass_rate_pct}%** ({s.passed_tests}/{s.total_tests} passed)",
            "",
            "| Total Tests | Passed | Failed | Warnings | Errors | Pass Rate |",
            "| :---: | :---: | :---: | :---: | :---: | :---: |",
            f"| **{f.total_tests}** | 🟢 {f.passed_count} | 🔴 {f.failed_count} | 🟡 {f.warning_count} | ⚠️ {f.error_count} | **{f.pass_rate_pct}%** |",
            "",
            "## 2. Performance & SLA Telemetry",
            f"- **Average Latency:** `{p.avg_latency_ms}ms`",
            f"- **P50 (Median):** `{p.p50_latency_ms}ms` | **P90:** `{p.p90_latency_ms}ms` | **P95:** `{p.p95_latency_ms}ms` | **P99:** `{p.p99_latency_ms}ms`",
            f"- **Min / Max Latency:** `{p.min_latency_ms}ms` / `{p.max_latency_ms}ms`",
            f"- **SLA Breaches:** `{p.sla_breach_count}` endpoints",
            ""
        ]

        if p.slow_endpoints:
            lines.extend([
                "### SLA Breaching Endpoints (>500ms)",
                "| Method | Endpoint | Latency | Target SLA | Overrun |",
                "| :--- | :--- | :---: | :---: | :---: |"
            ])
            for se in p.slow_endpoints:
                lines.append(f"| `{se.endpoint_method}` | `{se.endpoint_path}` | `{se.latency_ms}ms` | `{se.target_sla_ms}ms` | `+{se.sla_breach_ms}ms` |")
            lines.append("")

        if f.failures:
            lines.extend([
                "## 3. Functional Failure Breakdown",
                "| Test Scenario | Method & Route | Status | HTTP Code | Failure Detail |",
                "| :--- | :--- | :---: | :---: | :--- |"
            ])
            for fl in f.failures:
                lines.append(f"| {fl.test_name} | `{fl.endpoint_method} {fl.endpoint_path}` | `{fl.status}` | `{fl.response_code or 'ERR'}` | {fl.failure_summary} |")
            lines.append("")

        if r.regressions:
            lines.extend([
                f"## 4. Regressions vs Baseline (Run #{r.baseline_run_id})",
                f"- **New Regressions:** `{r.new_failures_count}` | **Latency Degradations:** `{r.latency_regressions_count}`",
                "| Test Scenario | Route | Previous | Current | Category | Details |",
                "| :--- | :--- | :---: | :---: | :---: | :--- |"
            ])
            for rg in r.regressions:
                lines.append(f"| {rg.test_name} | `{rg.endpoint_method} {rg.endpoint_path}` | `{rg.baseline_status}` | `{rg.current_status}` | `{rg.category}` | {rg.details or '-'} |")
            lines.append("")

        if rf.patterns:
            lines.extend([
                "## 5. Recurring & Chronic Failure Patterns",
                "| Fingerprint | Method & Route | Occurrences | Persistence | Root Cause Hint |",
                "| :---: | :--- | :---: | :---: | :--- |"
            ])
            for pat in rf.patterns:
                lines.append(f"| `{pat.fingerprint}` | `{pat.endpoint_method} {pat.endpoint_path}` | `{pat.occurrence_count}` | `{pat.persistence_rating}` | {pat.root_cause_hint} |")
            lines.append("")

        if rec.recommendations:
            lines.extend([
                "## 6. Actionable AI & Rule-Based Remediations",
                ""
            ])
            for idx, rcmd in enumerate(rec.recommendations, 1):
                lines.extend([
                    f"### #{idx}: [{rcmd.endpoint_method}] {rcmd.endpoint_path} ({rcmd.severity})",
                    f"- **Root Cause:** `{rcmd.root_cause_category}` ({rcmd.source})",
                    f"- **Diagnosis:** {rcmd.likely_cause}",
                    f"- **Remediation:** {rcmd.suggested_fix}",
                    "",
                    "```bash",
                    f"# Reproducible cURL Command",
                    f"{rcmd.reproducible_curl or 'curl -X GET ' + rcmd.endpoint_path}",
                    "```",
                    "",
                    "```python",
                    f"# Suggested Code Fix",
                    f"{rcmd.code_snippet or '# No snippet available'}",
                    "```",
                    ""
                ])

        lines.append("---")
        lines.append("*Generated automatically by API Sentinel Platform (JP-009).*")
        return "\n".join(lines)


    @classmethod
    def generate_html_report(cls, report: ComprehensiveTestReport) -> str:
        """Render a self-contained, responsive, printable Dark Cyber HTML report."""
        s = report.summary
        f = report.functional
        p = report.performance
        r = report.regressions
        rec = report.recommendations
        rf = report.recurring_failures

        verdict_color = "emerald" if s.verdict == ReportVerdict.PASS else ("amber" if s.verdict == ReportVerdict.DEGRADED else "rose")

        failures_rows = ""
        for fl in f.failures:
            failures_rows += f"""
            <tr class="border-b border-white/5 hover:bg-white/[0.02]">
              <td class="p-3 text-white font-medium">{fl.test_name}</td>
              <td class="p-3 font-mono text-cyan-400 text-xs"><span class="px-1.5 py-0.5 rounded bg-white/10">{fl.endpoint_method}</span> {fl.endpoint_path}</td>
              <td class="p-3 font-mono text-rose-400 text-xs">{fl.status}</td>
              <td class="p-3 font-mono text-text-secondary text-xs">{fl.response_code or 'ERR'}</td>
              <td class="p-3 text-text-secondary text-xs">{fl.failure_summary}</td>
            </tr>
            """

        slow_rows = ""
        for se in p.slow_endpoints:
            slow_rows += f"""
            <tr class="border-b border-white/5 hover:bg-white/[0.02]">
              <td class="p-3 font-mono text-cyan-400 text-xs"><span class="px-1.5 py-0.5 rounded bg-white/10">{se.endpoint_method}</span> {se.endpoint_path}</td>
              <td class="p-3 font-mono text-amber-400 text-xs">{se.latency_ms}ms</td>
              <td class="p-3 font-mono text-text-secondary text-xs">{se.target_sla_ms}ms</td>
              <td class="p-3 font-mono text-rose-400 text-xs">+{se.sla_breach_ms}ms</td>
            </tr>
            """

        rec_cards = ""
        for idx, rcmd in enumerate(rec.recommendations, 1):
            sev_badge = "bg-rose-500/20 text-rose-300" if rcmd.severity in ["CRITICAL", "HIGH"] else "bg-amber-500/20 text-amber-300"
            rec_cards += f"""
            <div class="bg-neutral-surface border border-white/10 rounded-xl p-5 space-y-3">
              <div class="flex items-center justify-between border-b border-white/10 pb-3">
                <div class="flex items-center gap-2 font-mono text-sm text-cyan-400">
                  <span class="px-2 py-0.5 rounded bg-cyan-500/10 border border-cyan-500/20 font-bold">{rcmd.endpoint_method}</span>
                  <span>{rcmd.endpoint_path}</span>
                </div>
                <div class="flex items-center gap-2">
                  <span class="px-2 py-0.5 rounded text-xs font-mono font-bold {sev_badge}">{rcmd.severity}</span>
                  <span class="text-[10px] text-text-secondary font-mono bg-white/5 px-2 py-0.5 rounded">{rcmd.root_cause_category}</span>
                </div>
              </div>
              <p class="text-xs text-white/90 leading-relaxed"><strong class="text-cyan-300">Diagnosis:</strong> {rcmd.likely_cause}</p>
              <p class="text-xs text-text-secondary leading-relaxed"><strong class="text-white">Action:</strong> {rcmd.suggested_fix}</p>
              <div class="space-y-1.5 pt-2">
                <span class="text-[11px] text-text-secondary uppercase font-semibold tracking-wider font-mono">Suggested Fix Snippet ({rcmd.source})</span>
                <pre class="bg-black/60 border border-white/10 rounded-lg p-3 text-xs font-mono text-emerald-400 overflow-x-auto"><code>{rcmd.code_snippet or '# No snippet provided'}</code></pre>
              </div>
            </div>
            """

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>API Sentinel Report — Run #{s.run_id} ({s.project_name})</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    /* the same lichen / clay / ochre the cockpit uses, so a pass reads as a
       pass without the stock palette shouting over the page */
    tailwind.config = {{ theme: {{ extend: {{ colors: {{
      emerald: {{ 300:'#c2d9a8', 400:'#a3c47f', 500:'#86ab63' }},
      green:   {{ 300:'#c2d9a8', 400:'#a3c47f', 500:'#86ab63' }},
      rose:    {{ 300:'#e8b09a', 400:'#d98b6a', 500:'#c26f4e' }},
      red:     {{ 300:'#e8b09a', 400:'#d98b6a', 500:'#c26f4e' }},
      amber:   {{ 300:'#ecc98d', 400:'#dcb166', 500:'#c9974a' }},
      yellow:  {{ 300:'#ecc98d', 400:'#dcb166', 500:'#c9974a' }},
      cyan:    {{ 300:'#dfe7d2', 400:'#e4ead6', 500:'#cdd8bb' }},
    }} }} }} }}
  </script>
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
  <style>
    /* Living Green — the same palette the cockpit and the landing page are
       cut from, so an exported report still reads as this product. */
    @font-face {{
      font-family: 'Lexend';
      src: url('/inner-green-assets/lexend-latin.woff2') format('woff2');
      font-weight: 100 900; font-style: normal; font-display: swap;
    }}
    body {{
      font-family: 'Lexend', system-ui, -apple-system, 'Segoe UI', sans-serif;
      font-weight: 300;
      background-color: #383b34;
      color: #ffffff;
      background-image:
        radial-gradient(64% 44% at 50% 104%, rgba(238,243,231,.10) 0%, rgba(238,243,231,0) 72%),
        radial-gradient(60% 50% at 94% 2%, rgba(24,28,20,.14) 0%, rgba(24,28,20,0) 68%);
      background-attachment: fixed;
    }}
    .font-mono {{ font-family: 'JetBrains Mono', ui-monospace, monospace; }}
    .bg-neutral-surface {{
      background-color: rgba(38,44,34,.55);
      background-image: linear-gradient(180deg, rgba(255,255,255,.055), rgba(255,255,255,0) 42%);
      backdrop-filter: blur(16px) saturate(1.18);
      border-color: rgba(255,255,255,.11);
      box-shadow: 0 8px 22px rgba(10,14,8,.28), inset 0 1px 0 rgba(255,255,255,.06);
    }}
    .text-brand-primary {{ color: #e4ead6; }}
    .border-brand-primary {{ border-color: #e4ead6; }}
    .text-text-secondary {{ color: rgba(255,255,255,.52); }}
    .uppercase {{ letter-spacing: .14em; }}
    .font-bold, .font-semibold {{ font-weight: 500; }}
  </style>
</head>
<body class="p-6 md:p-12 max-w-5xl mx-auto space-y-8">
  <!-- Header Bar -->
  <header class="bg-neutral-surface border border-white/10 rounded-2xl p-6 flex flex-col md:flex-row md:items-center justify-between gap-4 shadow-2xl">
    <div>
      <div class="flex items-center gap-3">
        <div class="w-8 h-8 rounded-lg bg-cyan-500/20 text-brand-primary flex items-center justify-center font-bold font-mono">AS</div>
        <h1 class="text-xl font-bold text-white tracking-tight">API Sentinel Diagnostic Report</h1>
      </div>
      <p class="text-xs text-text-secondary font-mono mt-1">Generated: {report.generated_at} • Run #{s.run_id}</p>
    </div>
    <div class="flex items-center gap-3">
      <span class="px-3 py-1 rounded-full text-xs font-mono font-bold border uppercase bg-{verdict_color}-500/10 text-{verdict_color}-400 border-{verdict_color}-500/30">Verdict: {s.verdict.value}</span>
      <button onclick="window.print()" class="px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-xs text-white font-medium transition-all">Print / Save PDF</button>
    </div>
  </header>

  <!-- Executive KPI Grid -->
  <section class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-3">
    <div class="bg-neutral-surface border border-white/10 rounded-xl p-4">
      <span class="text-[11px] text-text-secondary font-mono uppercase">Workspace</span>
      <div class="text-sm font-bold text-white truncate mt-1">{s.project_name}</div>
    </div>
    <div class="bg-neutral-surface border border-white/10 rounded-xl p-4">
      <span class="text-[11px] text-text-secondary font-mono uppercase">Pass Rate</span>
      <div class="text-xl font-bold text-{verdict_color}-400 mt-1">{s.pass_rate_pct}%</div>
    </div>
    <div class="bg-neutral-surface border border-white/10 rounded-xl p-4">
      <span class="text-[11px] text-text-secondary font-mono uppercase">Tests Executed</span>
      <div class="text-xl font-bold text-white mt-1">{s.total_tests}</div>
    </div>
    <div class="bg-neutral-surface border border-white/10 rounded-xl p-4">
      <span class="text-[11px] text-text-secondary font-mono uppercase">Passed / Failed</span>
      <div class="text-xl font-bold text-white mt-1"><span class="text-emerald-400">{s.passed_tests}</span> / <span class="text-rose-400">{s.failed_tests}</span></div>
    </div>
    <div class="bg-neutral-surface border border-white/10 rounded-xl p-4">
      <span class="text-[11px] text-text-secondary font-mono uppercase">Avg Latency</span>
      <div class="text-xl font-bold text-white mt-1">{p.avg_latency_ms}ms</div>
    </div>
    <div class="bg-neutral-surface border border-white/10 rounded-xl p-4">
      <span class="text-[11px] text-text-secondary font-mono uppercase">P95 Latency</span>
      <div class="text-xl font-bold text-white mt-1">{p.p95_latency_ms}ms</div>
    </div>
  </section>

  <!-- Performance Statistics Bar -->
  <section class="bg-neutral-surface border border-white/10 rounded-xl p-5 space-y-3">
    <h2 class="text-xs uppercase font-semibold text-brand-primary tracking-wider font-mono">Performance SLA & Percentiles</h2>
    <div class="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-7 gap-2 text-xs font-mono">
      <div class="p-2.5 rounded-lg bg-black/40 border border-white/5"><span class="text-text-secondary block text-[10px]">P50 (Median)</span><span class="text-white font-bold">{p.p50_latency_ms}ms</span></div>
      <div class="p-2.5 rounded-lg bg-black/40 border border-white/5"><span class="text-text-secondary block text-[10px]">P90</span><span class="text-white font-bold">{p.p90_latency_ms}ms</span></div>
      <div class="p-2.5 rounded-lg bg-black/40 border border-white/5"><span class="text-text-secondary block text-[10px]">P95</span><span class="text-white font-bold">{p.p95_latency_ms}ms</span></div>
      <div class="p-2.5 rounded-lg bg-black/40 border border-white/5"><span class="text-text-secondary block text-[10px]">P99</span><span class="text-white font-bold">{p.p99_latency_ms}ms</span></div>
      <div class="p-2.5 rounded-lg bg-black/40 border border-white/5"><span class="text-text-secondary block text-[10px]">Min Latency</span><span class="text-white font-bold">{p.min_latency_ms}ms</span></div>
      <div class="p-2.5 rounded-lg bg-black/40 border border-white/5"><span class="text-text-secondary block text-[10px]">Max Latency</span><span class="text-white font-bold">{p.max_latency_ms}ms</span></div>
      <div class="p-2.5 rounded-lg bg-black/40 border border-white/5"><span class="text-text-secondary block text-[10px]">SLA Breaches</span><span class="text-rose-400 font-bold">{p.sla_breach_count}</span></div>
    </div>
  </section>

  <!-- SLA Breaches Table -->
  {"<section class='bg-neutral-surface border border-white/10 rounded-xl overflow-hidden'>" +
   "<div class='p-4 border-b border-white/10 font-semibold text-xs text-white uppercase font-mono'>SLA Breaching Endpoints (>500ms)</div>" +
   "<table class='w-full text-left text-xs font-mono'><thead class='bg-white/[0.02] text-text-secondary uppercase text-[10px]'><tr><th class='p-3'>Endpoint</th><th class='p-3'>Latency</th><th class='p-3'>Target SLA</th><th class='p-3'>Overrun</th></tr></thead><tbody>" + slow_rows + "</tbody></table></section>" if p.slow_endpoints else ""}

  <!-- Functional Failures Table -->
  {"<section class='bg-neutral-surface border border-white/10 rounded-xl overflow-hidden'>" +
   "<div class='p-4 border-b border-white/10 font-semibold text-xs text-rose-400 uppercase font-mono'>Functional Failure Breakdown (" + str(len(f.failures)) + " failed)</div>" +
   "<table class='w-full text-left text-xs'><thead class='bg-white/[0.02] text-text-secondary uppercase text-[10px] font-mono'><tr><th class='p-3'>Test Scenario</th><th class='p-3'>Endpoint</th><th class='p-3'>Status</th><th class='p-3'>HTTP Code</th><th class='p-3'>Failure Detail</th></tr></thead><tbody>" + failures_rows + "</tbody></table></section>" if f.failures else ""}

  <!-- Actionable Recommendations -->
  {"<section class='space-y-4'><h2 class='text-xs uppercase font-semibold text-brand-primary tracking-wider font-mono'>Actionable AI & Rule-Based Remediations (" + str(len(rec.recommendations)) + ")</h2><div class='space-y-4'>" + rec_cards + "</div></section>" if rec.recommendations else ""}

  <footer class="pt-8 border-t border-white/10 text-center text-xs text-text-secondary font-mono">
    Generated by API Sentinel Automated Telemetry & Diagnostics Platform (Case Study JP-009)
  </footer>
</body>
</html>"""
        return html
