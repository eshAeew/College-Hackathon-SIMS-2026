"""Decision matrix and severity scoring algorithms for test results (Stage 17)."""
import logging
from typing import List, Optional

from app.models.schemas.result_classification import (
    BatchClassificationReport,
    ClassificationSeverity,
    ClassificationSummaryCards,
    ClassifiedResultReport,
    ExecutionClassificationInput,
    ExecutionOutcomeTier,
    FailureSubCategory,
)

logger = logging.getLogger("app.utils.result_classifier")


def classify_execution(item: ExecutionClassificationInput) -> ClassifiedResultReport:
    """
    Evaluate an execution item through the 4-tier decision matrix and assign impact severity.
    """
    # -------------------------------------------------------------
    # 1. ERROR: Network, Connection, or DNS Failure
    # -------------------------------------------------------------
    if item.network_error:
        err_msg = item.network_error.lower()
        if "timeout" in err_msg:
            sub = FailureSubCategory.LATENCY_SLA_BREACH
            title = "Network Timeout Error"
            diag = [f"Request timed out: {item.network_error}"]
            action = "Check target server responsiveness, network latency, or increase request timeout."
        elif "connection refused" in err_msg or "connect" in err_msg:
            sub = FailureSubCategory.NETWORK_CONNECTIVITY_ERROR
            title = "Connection Refused / Server Unreachable"
            diag = [f"Failed to connect to host: {item.network_error}"]
            action = "Verify target server is running and accessible on the specified host and port."
        elif "ssl" in err_msg or "certificate" in err_msg:
            sub = FailureSubCategory.AUTH_SECURITY_FAILURE
            title = "SSL / TLS Certificate Validation Error"
            diag = [f"SSL handshake error: {item.network_error}"]
            action = "Inspect target SSL certificate validity or disable SSL verification for dev targets."
        else:
            sub = FailureSubCategory.NETWORK_CONNECTIVITY_ERROR
            title = "Network Execution Error"
            diag = [f"Network exception: {item.network_error}"]
            action = "Inspect network connection, DNS configuration, and target host URL syntax."

        return ClassifiedResultReport(
            test_name=item.test_name or "Execution",
            http_method=item.http_method.upper(),
            url=item.url,
            outcome=ExecutionOutcomeTier.ERROR,
            severity=ClassificationSeverity.HIGH,
            sub_category=sub,
            priority_rank=2,
            title=title,
            diagnostic_details=diag,
            suggested_action=action
        )

    # -------------------------------------------------------------
    # 2. HTTP 500 Unhandled Server Exceptions
    # -------------------------------------------------------------
    status = item.status_code
    exp_status = item.expected_status or (200 if not item.is_negative_test else 400)

    if status and status >= 500 and (exp_status < 500):
        if item.is_negative_test:
            title = f"Unhandled Server Exception (HTTP {status}) on Negative Payload"
            diag = [
                f"Negative test payload triggered an unhandled HTTP {status} server crash.",
                "Server should validate inputs and return 4xx (400 Bad Request / 422 Unprocessable Entity)."
            ]
            action = "Add defensive input validation and exception boundary handling to reject malformed input with 4xx."
            sev = ClassificationSeverity.CRITICAL
            rank = 1
        else:
            title = f"Internal Server Error (HTTP {status})"
            diag = [f"Endpoint crashed with HTTP {status} unexpectedly."]
            action = "Check application backend server logs and stack traces for unhandled exceptions."
            sev = ClassificationSeverity.CRITICAL if item.endpoint_severity == "critical" else ClassificationSeverity.HIGH
            rank = 1 if sev == ClassificationSeverity.CRITICAL else 2

        return ClassifiedResultReport(
            test_name=item.test_name or "Execution",
            http_method=item.http_method.upper(),
            url=item.url,
            outcome=ExecutionOutcomeTier.ERROR,
            severity=sev,
            sub_category=FailureSubCategory.HTTP_500_SERVER_CRASH,
            priority_rank=rank,
            title=title,
            diagnostic_details=diag,
            suggested_action=action
        )

    # -------------------------------------------------------------
    # 3. FAIL: Functional Assertions, Status Code, or Schema Violations
    # -------------------------------------------------------------
    if not item.assertions_passed or (status is not None and status != exp_status):
        diag_list = list(item.assertion_errors)
        if status != exp_status:
            diag_list.insert(0, f"Status code mismatch: expected {exp_status}, observed {status}.")

        # Categorize sub-category and severity
        is_schema_err = any("schema" in e.lower() for e in diag_list)
        is_status_err = (status != exp_status)
        is_auth_err = (status in (401, 403)) and (exp_status not in (401, 403))

        if is_auth_err:
            sub = FailureSubCategory.AUTH_SECURITY_FAILURE
            title = f"Authentication / Authorization Failure (HTTP {status})"
            sev = ClassificationSeverity.CRITICAL
            rank = 1
            action = "Verify API credentials, authentication headers (Bearer token, API key), or user permissions."
        elif is_status_err:
            sub = FailureSubCategory.STATUS_CODE_MISMATCH
            title = f"Status Code Assertion Mismatch ({status} != {exp_status})"
            sev = ClassificationSeverity.HIGH if item.endpoint_severity in ("critical", "high") else ClassificationSeverity.MEDIUM
            rank = 2 if sev == ClassificationSeverity.HIGH else 3
            action = "Verify endpoint business logic and route handling return expected HTTP status codes."
        elif is_schema_err:
            sub = FailureSubCategory.SCHEMA_VIOLATION
            title = "Response JSON Schema Contract Violation"
            sev = ClassificationSeverity.MEDIUM
            rank = 3
            action = "Update API response model or align consumer schema with the latest backend contract."
        else:
            sub = FailureSubCategory.FIELD_ASSERTION_FAILED
            title = "Functional Field Assertion Failed"
            sev = ClassificationSeverity.MEDIUM
            rank = 3
            action = "Review payload response values and adjust test expectation operators if appropriate."

        return ClassifiedResultReport(
            test_name=item.test_name or "Execution",
            http_method=item.http_method.upper(),
            url=item.url,
            outcome=ExecutionOutcomeTier.FAIL,
            severity=sev,
            sub_category=sub,
            priority_rank=rank,
            title=title,
            diagnostic_details=diag_list,
            suggested_action=action
        )

    # -------------------------------------------------------------
    # 4. WARNING: Functional Pass but Latency SLA or Minor Anomaly
    # -------------------------------------------------------------
    is_latency_warn = False
    if item.max_latency_ms is not None and item.latency_ms > item.max_latency_ms:
        is_latency_warn = True

    if is_latency_warn:
        diag = [
            f"Response latency {item.latency_ms:.2f}ms exceeded SLA threshold {item.max_latency_ms:.2f}ms."
        ]
        overrun_pct = ((item.latency_ms - item.max_latency_ms) / item.max_latency_ms) * 100.0
        sev = ClassificationSeverity.MEDIUM if overrun_pct > 100.0 else ClassificationSeverity.LOW
        rank = 3 if sev == ClassificationSeverity.MEDIUM else 4

        return ClassifiedResultReport(
            test_name=item.test_name or "Execution",
            http_method=item.http_method.upper(),
            url=item.url,
            outcome=ExecutionOutcomeTier.WARNING,
            severity=sev,
            sub_category=FailureSubCategory.LATENCY_SLA_BREACH,
            priority_rank=rank,
            title=f"Performance SLA Warning (+{overrun_pct:.1f}% latency overrun)",
            diagnostic_details=diag,
            suggested_action="Profile database queries, network latency, and service compute time to optimize response speed."
        )

    # -------------------------------------------------------------
    # 5. PASS: Clean Standard Success
    # -------------------------------------------------------------
    return ClassifiedResultReport(
        test_name=item.test_name or "Execution",
        http_method=item.http_method.upper(),
        url=item.url,
        outcome=ExecutionOutcomeTier.PASS,
        severity=ClassificationSeverity.NONE,
        sub_category=FailureSubCategory.NONE,
        priority_rank=5,
        title="Execution Passed All Assertions",
        diagnostic_details=[f"HTTP {status or 200} OK in {item.latency_ms:.2f}ms"],
        suggested_action="No action required. Test is healthy."
    )


def classify_batch_executions(items: List[ExecutionClassificationInput]) -> BatchClassificationReport:
    """
    Classify a batch of executions, compute aggregate metrics, calculate health score, and prioritize failures.
    """
    total = len(items)
    pass_cnt = 0
    fail_cnt = 0
    warn_cnt = 0
    err_cnt = 0
    skip_cnt = 0

    crit_sev = 0
    high_sev = 0
    med_sev = 0
    low_sev = 0

    classified_list: List[ClassifiedResultReport] = []

    for it in items:
        rep = classify_execution(it)
        classified_list.append(rep)

        if rep.outcome == ExecutionOutcomeTier.PASS:
            pass_cnt += 1
        elif rep.outcome == ExecutionOutcomeTier.FAIL:
            fail_cnt += 1
        elif rep.outcome == ExecutionOutcomeTier.WARNING:
            warn_cnt += 1
        elif rep.outcome == ExecutionOutcomeTier.ERROR:
            err_cnt += 1
        elif rep.outcome == ExecutionOutcomeTier.SKIPPED:
            skip_cnt += 1

        if rep.severity == ClassificationSeverity.CRITICAL:
            crit_sev += 1
        elif rep.severity == ClassificationSeverity.HIGH:
            high_sev += 1
        elif rep.severity == ClassificationSeverity.MEDIUM:
            med_sev += 1
        elif rep.severity == ClassificationSeverity.LOW:
            low_sev += 1

    # Pass Rate Calculation
    effective_total = total - skip_cnt
    pass_rate = round((pass_cnt / effective_total) * 100.0, 1) if effective_total > 0 else 100.0

    # Health Score Index: 100 - weighted failure penalties
    deductions = (crit_sev * 25.0) + (high_sev * 15.0) + (med_sev * 5.0) + (low_sev * 2.0)
    health_score = max(0.0, min(100.0, round(100.0 - deductions, 1)))

    # Sort failures by priority rank (1=Critical, 2=High, 3=Medium, 4=Low)
    failures = [
        r for r in classified_list
        if r.outcome in (ExecutionOutcomeTier.FAIL, ExecutionOutcomeTier.ERROR, ExecutionOutcomeTier.WARNING)
    ]
    prioritized = sorted(failures, key=lambda x: (x.priority_rank, x.test_name))

    summary = ClassificationSummaryCards(
        total_executions=total,
        pass_count=pass_cnt,
        fail_count=fail_cnt,
        warning_count=warn_cnt,
        error_count=err_cnt,
        skipped_count=skip_cnt,
        critical_severity_count=crit_sev,
        high_severity_count=high_sev,
        medium_severity_count=med_sev,
        low_severity_count=low_sev,
        health_score_index=health_score,
        pass_rate_pct=pass_rate
    )

    return BatchClassificationReport(
        summary=summary,
        prioritized_failures=prioritized,
        all_results=classified_list
    )
