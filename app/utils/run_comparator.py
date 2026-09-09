"""Pure comparison helpers for side-by-side run diffing (Stage 21)."""
from typing import Dict, List, Optional, Tuple

from app.models.schemas.run_comparison import (
    BadgeTone,
    ChangeKind,
    ComparisonVerdict,
    DeltaBadge,
    LatencyShift,
    MetricDelta,
    TestChange,
)

# Statuses that count as a healthy outcome when diffing two runs.
PASSING_STATUSES = {"PASS", "PASSED"}

# A latency move must clear this to be worth surfacing as SLOWER / FASTER.
LATENCY_SHIFT_THRESHOLD_PCT = 25.0


def is_passing(status: Optional[str]) -> bool:
    """Return True when a recorded result status represents success."""
    return (status or "").upper() in PASSING_STATUSES


def pct_change(baseline: Optional[float], current: Optional[float]) -> Optional[float]:
    """Percentage movement from baseline to current, guarding division by zero."""
    if baseline is None or current is None:
        return None
    if baseline == 0:
        return None if current == 0 else 100.0
    return round(((current - baseline) / baseline) * 100.0, 2)


def classify_change(
    baseline_status: Optional[str],
    current_status: Optional[str],
    baseline_latency: Optional[float],
    current_latency: Optional[float]
) -> Tuple[ChangeKind, BadgeTone, str]:
    """Decide how one test moved between runs and how it should be rendered."""
    if baseline_status is None:
        return ChangeKind.ADDED, BadgeTone.NEUTRAL, "NEW TEST"
    if current_status is None:
        return ChangeKind.REMOVED, BadgeTone.NEUTRAL, "REMOVED"

    was_ok = is_passing(baseline_status)
    now_ok = is_passing(current_status)

    if was_ok and not now_ok:
        return ChangeKind.BROKEN, BadgeTone.NEGATIVE, "BROKEN TEST"
    if not was_ok and now_ok:
        return ChangeKind.FIXED, BadgeTone.POSITIVE, "RESOLVED / FIXED"
    if not was_ok and not now_ok:
        return ChangeKind.STILL_FAILING, BadgeTone.NEGATIVE, "STILL FAILING"

    # Both sides passed; surface a material latency move.
    shift = pct_change(baseline_latency, current_latency)
    if shift is not None and shift >= LATENCY_SHIFT_THRESHOLD_PCT:
        return ChangeKind.SLOWER, BadgeTone.WARNING, f"SLOWDOWN +{shift:.0f}%"
    if shift is not None and shift <= -LATENCY_SHIFT_THRESHOLD_PCT:
        return ChangeKind.FASTER, BadgeTone.POSITIVE, f"FASTER {shift:.0f}%"
    return ChangeKind.STILL_PASSING, BadgeTone.NEUTRAL, "STABLE"


def build_test_change(
    test_name: str,
    baseline: Optional[Dict],
    current: Optional[Dict]
) -> TestChange:
    """Build one per-test diff row from a baseline and current result record."""
    b_status = baseline.get("status") if baseline else None
    c_status = current.get("status") if current else None
    b_latency = baseline.get("latency_ms") if baseline else None
    c_latency = current.get("latency_ms") if current else None
    b_code = baseline.get("status_code") if baseline else None
    c_code = current.get("status_code") if current else None

    kind, tone, badge = classify_change(b_status, c_status, b_latency, c_latency)
    shift = pct_change(b_latency, c_latency)

    if kind == ChangeKind.BROKEN:
        detail = f"Previously {b_status} ({b_code}); now {c_status} ({c_code})."
        if c_code is not None and c_code >= 500:
            badge = "CRITICAL CRASH"
    elif kind == ChangeKind.FIXED:
        detail = f"Recovered from {b_status} ({b_code}) to {c_status} ({c_code})."
    elif kind in (ChangeKind.SLOWER, ChangeKind.FASTER):
        detail = f"Latency moved {b_latency}ms -> {c_latency}ms ({shift:+.1f}%)."
    elif kind == ChangeKind.STILL_FAILING:
        detail = f"Still failing ({c_status}, HTTP {c_code})."
    elif kind == ChangeKind.ADDED:
        detail = "Test did not exist in the baseline run."
    elif kind == ChangeKind.REMOVED:
        detail = "Test was present in the baseline run but not in the current run."
    else:
        detail = "No material change."

    source = current or baseline or {}
    return TestChange(
        test_name=test_name,
        test_case_id=source.get("test_case_id"),
        endpoint_id=source.get("endpoint_id"),
        change=kind,
        tone=tone,
        badge=badge,
        baseline_status=b_status,
        current_status=c_status,
        baseline_code=b_code,
        current_code=c_code,
        baseline_latency_ms=b_latency,
        current_latency_ms=c_latency,
        latency_delta_pct=shift,
        detail=detail,
    )


def build_metric_delta(
    metric: str,
    baseline: float,
    current: float,
    higher_is_better: bool = True
) -> MetricDelta:
    """Compute a signed metric delta and choose its display tone."""
    delta = round(current - baseline, 3)
    change = pct_change(baseline, current)
    if delta == 0:
        tone = BadgeTone.NEUTRAL
    elif (delta > 0 and higher_is_better) or (delta < 0 and not higher_is_better):
        tone = BadgeTone.POSITIVE
    else:
        tone = BadgeTone.NEGATIVE
    return MetricDelta(
        metric=metric,
        baseline=round(baseline, 3),
        current=round(current, 3),
        delta=delta,
        delta_pct=change,
        tone=tone,
    )


def build_latency_shift(
    baseline_latencies: List[float],
    current_latencies: List[float]
) -> LatencyShift:
    """Summarize how the latency distribution moved between runs."""
    b_avg = round(sum(baseline_latencies) / len(baseline_latencies), 3) if baseline_latencies else 0.0
    c_avg = round(sum(current_latencies) / len(current_latencies), 3) if current_latencies else 0.0
    b_max = round(max(baseline_latencies), 3) if baseline_latencies else 0.0
    c_max = round(max(current_latencies), 3) if current_latencies else 0.0
    delta = round(c_avg - b_avg, 3)
    shift = pct_change(b_avg, c_avg)

    if shift is None or abs(shift) < 5.0:
        tone = BadgeTone.NEUTRAL
        summary = "Latency is essentially unchanged."
    elif shift > 0:
        tone = BadgeTone.WARNING if shift < LATENCY_SHIFT_THRESHOLD_PCT else BadgeTone.NEGATIVE
        summary = f"Average latency increased {shift:.1f}% ({b_avg}ms -> {c_avg}ms)."
    else:
        tone = BadgeTone.POSITIVE
        summary = f"Average latency improved {abs(shift):.1f}% ({b_avg}ms -> {c_avg}ms)."

    return LatencyShift(
        baseline_avg_ms=b_avg,
        current_avg_ms=c_avg,
        delta_ms=delta,
        delta_pct=shift,
        baseline_max_ms=b_max,
        current_max_ms=c_max,
        tone=tone,
        summary=summary,
    )


def decide_verdict(
    broken: int,
    fixed: int,
    net_quality_delta_pct: float,
    has_server_crash: bool
) -> Tuple[ComparisonVerdict, str]:
    """Choose the overall verdict and its one-line headline."""
    if has_server_crash or broken >= 3:
        headline = (
            f"{broken} test(s) regressed, including a server-side crash."
            if has_server_crash
            else f"{broken} test(s) regressed since the baseline run."
        )
        return ComparisonVerdict.CRITICAL_REGRESSIONS_FOUND, headline
    if broken > 0:
        return (
            ComparisonVerdict.DEGRADED,
            f"{broken} test(s) broke and {fixed} were fixed "
            f"({net_quality_delta_pct:+.1f}% pass rate).",
        )
    if fixed > 0 or net_quality_delta_pct > 0:
        return (
            ComparisonVerdict.IMPROVED,
            f"{fixed} test(s) recovered with no new regressions "
            f"({net_quality_delta_pct:+.1f}% pass rate).",
        )
    return ComparisonVerdict.CLEAN, "No status changes detected between the two runs."


def build_badges(
    broken: int,
    fixed: int,
    slower: int,
    faster: int,
    net_quality_delta_pct: float,
    latency: LatencyShift
) -> List[DeltaBadge]:
    """Assemble the badge strip shown above the diff table."""
    return [
        DeltaBadge(
            label="New Regressions",
            value=str(broken),
            tone=BadgeTone.NEGATIVE if broken else BadgeTone.POSITIVE,
            hint="Tests that passed in the baseline and fail now",
        ),
        DeltaBadge(
            label="Fixed",
            value=str(fixed),
            tone=BadgeTone.POSITIVE if fixed else BadgeTone.NEUTRAL,
            hint="Tests that failed in the baseline and pass now",
        ),
        DeltaBadge(
            label="Slower",
            value=str(slower),
            tone=BadgeTone.WARNING if slower else BadgeTone.NEUTRAL,
            hint=f"Latency up more than {LATENCY_SHIFT_THRESHOLD_PCT:.0f}%",
        ),
        DeltaBadge(
            label="Faster",
            value=str(faster),
            tone=BadgeTone.POSITIVE if faster else BadgeTone.NEUTRAL,
            hint=f"Latency down more than {LATENCY_SHIFT_THRESHOLD_PCT:.0f}%",
        ),
        DeltaBadge(
            label="Net Quality",
            value=f"{net_quality_delta_pct:+.1f}%",
            tone=(
                BadgeTone.POSITIVE if net_quality_delta_pct > 0
                else BadgeTone.NEGATIVE if net_quality_delta_pct < 0
                else BadgeTone.NEUTRAL
            ),
            hint="Pass-rate movement against the baseline",
        ),
        DeltaBadge(
            label="Avg Latency",
            value=f"{latency.delta_ms:+.1f}ms",
            tone=latency.tone,
            hint=latency.summary,
        ),
    ]
