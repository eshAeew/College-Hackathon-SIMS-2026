"""Service layer for autonomous programmatic platform self-testing and health matrix analysis."""
import io
import logging
import os
import sys
import time
import unittest
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.models.schemas.self_test import (
    SelfTestRunResponse,
    SubsystemCategory,
    SubsystemHealthMatrixResponse,
    SubsystemSummaryDTO,
    SuiteMetadata,
    TestCaseResultDTO,
)

logger = logging.getLogger("app.services.self_test")


# Map subsystems to their test module files
SUBSYSTEM_MAP: Dict[str, Dict[str, Any]] = {
    "core_foundation": {
        "name": "Core Foundation & Request Pipeline",
        "description": "Base app, projects, endpoints, request builder, and preflight checks.",
        "files": [
            "test_main.py",
            "test_logging_and_health.py",
            "test_projects.py",
            "test_endpoints.py",
            "test_request_builder.py",
            "test_preflight_validation.py",
        ],
    },
    "execution_engine": {
        "name": "Core API Execution & Telemetry Engine",
        "description": "Async HTTP dispatcher, telemetry capture, test cases, assertions, and test runs.",
        "files": [
            "test_async_http_dispatcher.py",
            "test_response_telemetry.py",
            "test_test_cases.py",
            "test_assertion_rules.py",
            "test_test_run_management.py",
            "test_safety_controls.py",
        ],
    },
    "validation_engine": {
        "name": "Contract & Schema Validation Engine",
        "description": "Protocol validator, JSON schema rules, OpenAPI parser, and test generator.",
        "files": [
            "test_protocol_validation.py",
            "test_schema_validation.py",
            "test_contract_spec.py",
            "test_openapi_support.py",
            "test_test_generation.py",
        ],
    },
    "analysis_ai": {
        "name": "Failure Diagnostics, Analytics & AI Layer",
        "description": "Negative testing, inconsistency, performance, recurring failures, regression, and AI recommendations.",
        "files": [
            "test_adversarial_testing.py",
            "test_inconsistent_behavior.py",
            "test_performance_analysis.py",
            "test_recurring_failures.py",
            "test_regression_engine.py",
            "test_result_classification.py",
            "test_failure_analysis.py",
            "test_failure_analysis_deep_audit.py",
            "test_ai_recommendations.py",
            "test_run_comparison.py",
        ],
    },
    "resilience_data_audit": {
        "name": "Resilience, Reports, Database & Auditability",
        "description": "Reports engine, database DAL, circuit breakers, error handlers, and audit trail.",
        "files": [
            "test_reports.py",
            "test_database_layer.py",
            "test_resilience_and_errors.py",
            "test_logging_tracing_and_audit.py",
            "test_dashboard_ui.py",
        ],
    },
}


class DetailedTestResult(unittest.TestResult):
    """Custom TestResult capturing timing and failure details for each test case."""

    def __init__(self, include_tracebacks: bool = True):
        super().__init__()
        self.include_tracebacks = include_tracebacks
        self.test_records: List[TestCaseResultDTO] = []
        self._test_start_time: float = 0.0

    def startTest(self, test):
        super().startTest(test)
        self._test_start_time = time.perf_counter()

    def addSuccess(self, test):
        super().addSuccess(test)
        duration_ms = round((time.perf_counter() - self._test_start_time) * 1000.0, 2)
        self.test_records.append(
            TestCaseResultDTO(
                test_id=f"{test.__class__.__name__}.{test._testMethodName}",
                status="PASSED",
                duration_ms=duration_ms,
            )
        )

    def addFailure(self, test, err):
        super().addFailure(test, err)
        duration_ms = round((time.perf_counter() - self._test_start_time) * 1000.0, 2)
        tb_str = self._exc_info_to_string(err, test) if self.include_tracebacks else None
        err_msg = str(err[1]) if len(err) > 1 else "AssertionError"
        self.test_records.append(
            TestCaseResultDTO(
                test_id=f"{test.__class__.__name__}.{test._testMethodName}",
                status="FAILED",
                duration_ms=duration_ms,
                error_message=err_msg,
                traceback=tb_str,
            )
        )

    def addError(self, test, err):
        super().addError(test, err)
        duration_ms = round((time.perf_counter() - self._test_start_time) * 1000.0, 2)
        tb_str = self._exc_info_to_string(err, test) if self.include_tracebacks else None
        err_msg = str(err[1]) if len(err) > 1 else "Exception"
        self.test_records.append(
            TestCaseResultDTO(
                test_id=f"{test.__class__.__name__}.{test._testMethodName}",
                status="ERROR",
                duration_ms=duration_ms,
                error_message=err_msg,
                traceback=tb_str,
            )
        )

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        duration_ms = round((time.perf_counter() - self._test_start_time) * 1000.0, 2)
        self.test_records.append(
            TestCaseResultDTO(
                test_id=f"{test.__class__.__name__}.{test._testMethodName}",
                status="SKIPPED",
                duration_ms=duration_ms,
                error_message=reason,
            )
        )


class SelfTestService:
    """Service executing and aggregating test suite results across all subsystems."""

    _latest_run: Optional[SelfTestRunResponse] = None

    @classmethod
    def get_available_suites(cls) -> List[SuiteMetadata]:
        """Return catalog of available subsystem test suites."""
        suites = []
        for sub_id, info in SUBSYSTEM_MAP.items():
            suites.append(
                SuiteMetadata(
                    id=sub_id,
                    name=info["name"],
                    description=info["description"],
                    test_files_count=len(info["files"]),
                    estimated_tests=len(info["files"]) * 8,
                )
            )
        return suites

    @classmethod
    def run_self_tests(
        cls,
        subsystem: SubsystemCategory = SubsystemCategory.FULL_SUITE,
        stop_on_first_error: bool = False,
        include_tracebacks: bool = True,
    ) -> SelfTestRunResponse:
        """Programmatically execute test suites and compute comprehensive metrics."""
        run_id = f"st-{uuid.uuid4().hex[:8]}"
        overall_start = time.perf_counter()
        loader = unittest.TestLoader()

        subsystems_to_run: List[str] = (
            list(SUBSYSTEM_MAP.keys())
            if subsystem == SubsystemCategory.FULL_SUITE
            else [subsystem.value]
        )

        all_failures: List[TestCaseResultDTO] = []
        subsystem_summaries: List[SubsystemSummaryDTO] = []
        total_p = 0
        total_f = 0
        total_e = 0
        total_s = 0
        total_t = 0

        for sub_key in subsystems_to_run:
            sub_info = SUBSYSTEM_MAP.get(sub_key)
            if not sub_info:
                continue

            sub_start = time.perf_counter()
            sub_suite = unittest.TestSuite()

            # Load tests from designated files
            tests_dir = os.path.join(os.getcwd(), "tests")
            for fname in sub_info["files"]:
                fpath = os.path.join(tests_dir, fname)
                if os.path.exists(fpath):
                    mod_name = f"tests.{fname[:-3]}"
                    try:
                        module_suite = loader.loadTestsFromName(mod_name)
                        sub_suite.addTests(module_suite)
                    except Exception as load_exc:
                        logger.warning(f"Could not load test module {mod_name}: {load_exc}")

            # Run subsystem suite
            result = DetailedTestResult(include_tracebacks=include_tracebacks)
            if stop_on_first_error:
                result.failfast = True

            sub_suite.run(result)
            sub_duration_ms = round((time.perf_counter() - sub_start) * 1000.0, 2)

            sub_total = result.testsRun
            sub_p = len([r for r in result.test_records if r.status == "PASSED"])
            sub_f = len(result.failures)
            sub_e = len(result.errors)
            sub_s = len(result.skipped)
            sub_pass_rate = round((sub_p / sub_total * 100.0), 1) if sub_total > 0 else 100.0

            sub_status = "HEALTHY"
            if sub_f > 0 or sub_e > 0:
                sub_status = "FAILING" if (sub_f + sub_e) > 2 else "DEGRADED"

            subsystem_summaries.append(
                SubsystemSummaryDTO(
                    subsystem=sub_key,
                    total_tests=sub_total,
                    passed=sub_p,
                    failed=sub_f,
                    errors=sub_e,
                    skipped=sub_s,
                    pass_rate=sub_pass_rate,
                    duration_ms=sub_duration_ms,
                    status=sub_status,
                )
            )

            total_t += sub_total
            total_p += sub_p
            total_f += sub_f
            total_e += sub_e
            total_s += sub_s

            all_failures.extend([r for r in result.test_records if r.status in ("FAILED", "ERROR")])

        overall_duration_ms = round((time.perf_counter() - overall_start) * 1000.0, 2)
        overall_pass_rate = round((total_p / total_t * 100.0), 1) if total_t > 0 else 100.0

        verdict = "ALL_PASSED"
        if total_f > 0 or total_e > 0:
            verdict = "FAILED" if (total_f + total_e) > 3 else "DEGRADED"

        response = SelfTestRunResponse(
            run_id=run_id,
            subsystem=subsystem.value,
            verdict=verdict,
            total_tests=total_t,
            passed=total_p,
            failed=total_f,
            errors=total_e,
            skipped=total_s,
            pass_rate=overall_pass_rate,
            total_duration_ms=overall_duration_ms,
            subsystems_breakdown=subsystem_summaries,
            failures=all_failures,
            executed_at=datetime.now(timezone.utc).isoformat(),
        )

        cls._latest_run = response
        return response

    @classmethod
    def get_latest_run(cls) -> Optional[SelfTestRunResponse]:
        """Retrieve most recent self-testing execution report."""
        if cls._latest_run is None:
            # Execute full suite if no run exists yet
            return cls.run_self_tests(SubsystemCategory.FULL_SUITE)
        return cls._latest_run

    @classmethod
    def get_health_matrix(cls) -> SubsystemHealthMatrixResponse:
        """Compute readiness status and metrics for all architectural subsystems."""
        latest = cls.get_latest_run()
        healthy_count = sum(1 for s in latest.subsystems_breakdown if s.status == "HEALTHY")
        overall = "HEALTHY" if healthy_count == len(latest.subsystems_breakdown) else "DEGRADED"

        return SubsystemHealthMatrixResponse(
            overall_system_status=overall,
            total_subsystems=len(latest.subsystems_breakdown),
            healthy_subsystems=healthy_count,
            subsystems=latest.subsystems_breakdown,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
