"""Pure comparison & delta analysis engine for Regression Testing (Stage 13)."""
from typing import Dict, List, Optional, Tuple
from app.models.schemas.regression import (
    ComparisonExecutionItem,
    RegressionItem,
    RegressionSeverity,
    RegressionSummaryCard,
    RegressionType,
    RegressionVerdict,
)


def calculate_latency_delta(
    baseline_ms: Optional[float],
    current_ms: float
) -> Tuple[float, float]:
    """
    Calculate absolute delta ms and percentage change.
    
    Returns:
        (latency_delta_ms, latency_change_pct)
    """
    if baseline_ms is None or baseline_ms <= 0.0:
        return 0.0, 0.0

    delta = round(current_ms - baseline_ms, 2)
    change_pct = round((delta / baseline_ms) * 100.0, 1)
    return delta, change_pct


def classify_regression(
    baseline: Optional[ComparisonExecutionItem],
    current: ComparisonExecutionItem,
    latency_threshold_pct: float = 50.0,
    min_latency_delta_ms: float = 50.0
) -> Tuple[RegressionType, RegressionSeverity, str, str]:
    """
    Classify the regression nature and severity of a test case.
    
    Returns:
        (regression_type, severity, badge_label, suggested_remediation)
    """
    curr_pass = current.status.upper() in ("PASS", "SUCCESS", "200")
    
    # 1. New Test Introduced
    if baseline is None:
        if not curr_pass:
            return (
                RegressionType.NEW_FAILURE,
                RegressionSeverity.HIGH,
                "NEW FAILURE",
                "Review new test scenario definition, request parameters, and mock backend requirements."
            )
        return (
            RegressionType.NO_REGRESSION,
            RegressionSeverity.NONE,
            "NEW PASS",
            "Newly introduced test passed cleanly."
        )

    base_pass = baseline.status.upper() in ("PASS", "SUCCESS", "200")
    delta_ms, pct_change = calculate_latency_delta(baseline.response_time_ms, current.response_time_ms)

    # 2. Functional Regression (Was passing, now failing)
    if base_pass and not curr_pass:
        # Check if critical server crash (5xx)
        if current.status_code and current.status_code >= 500:
            return (
                RegressionType.FUNCTIONAL_REGRESSION,
                RegressionSeverity.CRITICAL,
                "CRITICAL CRASH",
                "Urgent: Endpoint threw unhandled 5xx server exception after recent deployment."
            )
        return (
            RegressionType.FUNCTIONAL_REGRESSION,
            RegressionSeverity.HIGH,
            "BROKEN TEST",
            "Functional regression detected: Test previously succeeded. Inspect recent codebase commits."
        )

    # 3. Resolved Improvement (Was failing, now passing)
    if not base_pass and curr_pass:
        return (
            RegressionType.RESOLVED_IMPROVEMENT,
            RegressionSeverity.NONE,
            "RESOLVED / FIXED",
            "Test scenario previously failed and is now passing successfully."
        )

    # 4. Performance Regression (Significant latency spike on passing or failing test)
    if pct_change >= latency_threshold_pct and delta_ms >= min_latency_delta_ms:
        severity = RegressionSeverity.HIGH if pct_change >= 150.0 else RegressionSeverity.MEDIUM
        return (
            RegressionType.PERFORMANCE_REGRESSION,
            severity,
            f"SLOWDOWN +{pct_change}%",
            f"Response time degraded by {pct_change}% (+{delta_ms}ms). Check database queries and connection pools."
        )

    # 5. Schema / Assertion Regression
    if not curr_pass and current.failure_type == "SCHEMA_MISMATCH":
        return (
            RegressionType.SCHEMA_REGRESSION,
            RegressionSeverity.HIGH,
            "SCHEMA MISMATCH",
            "Response contract violation detected. Verify JSON Schema serialization rules."
        )

    # 6. Stable State (Either passed both or failed both)
    badge = "STABLE PASS" if curr_pass else "STABLE FAIL"
    return (
        RegressionType.NO_REGRESSION,
        RegressionSeverity.NONE,
        badge,
        "No new functional or performance regressions observed."
    )


def compare_execution_results(
    baseline_items: List[ComparisonExecutionItem],
    current_items: List[ComparisonExecutionItem],
    latency_threshold_pct: float = 50.0,
    min_latency_delta_ms: float = 50.0
) -> Tuple[RegressionSummaryCard, List[RegressionItem], List[RegressionItem], List[RegressionItem]]:
    """
    Compare baseline and current execution results, returning summary card and categorized item lists.
    """
    # Key baseline items by test_name or test_case_id
    baseline_map: Dict[str, ComparisonExecutionItem] = {}
    for b in baseline_items:
        key = str(b.test_case_id) if b.test_case_id is not None else b.test_name
        baseline_map[key] = b

    regressions: List[RegressionItem] = []
    improvements: List[RegressionItem] = []
    stable_items: List[RegressionItem] = []

    for curr in current_items:
        key = str(curr.test_case_id) if curr.test_case_id is not None else curr.test_name
        base = baseline_map.get(key)

        delta_ms, pct_change = calculate_latency_delta(
            base.response_time_ms if base else None,
            curr.response_time_ms
        )

        reg_type, severity, badge, suggestion = classify_regression(
            baseline=base,
            current=curr,
            latency_threshold_pct=latency_threshold_pct,
            min_latency_delta_ms=min_latency_delta_ms
        )

        item = RegressionItem(
            test_case_id=curr.test_case_id,
            endpoint_id=curr.endpoint_id,
            test_name=curr.test_name,
            regression_type=reg_type,
            severity=severity,
            baseline_status=base.status if base else None,
            current_status=curr.status,
            baseline_status_code=base.status_code if base else None,
            current_status_code=curr.status_code,
            baseline_latency_ms=base.response_time_ms if base else None,
            current_latency_ms=curr.response_time_ms,
            latency_delta_ms=delta_ms,
            latency_change_pct=pct_change,
            failure_type=curr.failure_type,
            failure_message=curr.failure_message,
            badge_label=badge,
            suggested_remediation=suggestion
        )

        if reg_type in (RegressionType.FUNCTIONAL_REGRESSION, RegressionType.PERFORMANCE_REGRESSION, RegressionType.SCHEMA_REGRESSION, RegressionType.NEW_FAILURE):
            regressions.append(item)
        elif reg_type == RegressionType.RESOLVED_IMPROVEMENT:
            improvements.append(item)
        else:
            stable_items.append(item)

    # Compute summary card statistics
    total = len(current_items)
    func_c = sum(1 for r in regressions if r.regression_type == RegressionType.FUNCTIONAL_REGRESSION)
    perf_c = sum(1 for r in regressions if r.regression_type == RegressionType.PERFORMANCE_REGRESSION)
    schema_c = sum(1 for r in regressions if r.regression_type == RegressionType.SCHEMA_REGRESSION)
    fixes_c = len(improvements)
    stable_pass_c = sum(1 for s in stable_items if s.current_status.upper() in ("PASS", "SUCCESS", "200"))
    
    total_reg = len(regressions)
    reg_rate = round((total_reg / total * 100.0), 1) if total > 0 else 0.0

    if any(r.severity == RegressionSeverity.CRITICAL for r in regressions) or func_c > 0:
        verdict = RegressionVerdict.CRITICAL_REGRESSIONS_FOUND
    elif total_reg > 0:
        verdict = RegressionVerdict.DEGRADED
    else:
        verdict = RegressionVerdict.CLEAN

    summary = RegressionSummaryCard(
        total_compared_tests=total,
        total_regressions=total_reg,
        functional_regressions=func_c,
        performance_regressions=perf_c,
        schema_regressions=schema_c,
        resolved_improvements=fixes_c,
        stable_passing=stable_pass_c,
        verdict=verdict,
        regression_rate_pct=reg_rate
    )

    return summary, regressions, improvements, stable_items
