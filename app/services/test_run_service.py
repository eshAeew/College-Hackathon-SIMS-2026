"""Service Layer for Orchestrating and Managing Test Suite Runs."""
import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.orm import Session

from app.models.entities.endpoint import Endpoint
from app.models.entities.project import Project
from app.models.entities.test_case import TestCase
from app.models.entities.test_run import TestRun
from app.models.entities.test_result import TestResult
from app.models.schemas.test_run import (
    RunStatus,
    TestResultResponse,
    TestResultStatus,
    TestRunCreateRequest,
    TestRunDetailResponse,
    TestRunSummaryResponse,
)
from app.services.test_case_service import TestCaseService
from app.utils.run_state_machine import (
    calculate_run_metrics,
    validate_state_transition,
)

logger = logging.getLogger("app.services.test_run")


class TestRunService:
    """Orchestrator service for queuing, executing, and tracking test runs."""

    @classmethod
    def create_test_run(
        cls,
        project_id: int,
        req: TestRunCreateRequest,
        db: Session
    ) -> TestRun:
        """Create and queue a new TestRun entity with selected test cases."""
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError(f"Project #{project_id} not found.")

        # Query relevant test cases based on filters
        query = db.query(TestCase).join(Endpoint).filter(
            Endpoint.project_id == project_id,
            TestCase.is_active == True
        )

        if req.test_case_ids:
            query = query.filter(TestCase.id.in_(req.test_case_ids))
        if req.endpoint_ids:
            query = query.filter(Endpoint.id.in_(req.endpoint_ids))

        all_test_cases = query.all()

        if req.tag_filter:
            tag = req.tag_filter.strip().lower()
            all_test_cases = [tc for tc in all_test_cases if tag in [t.lower() for t in tc.tags]]

        run_name = req.name or f"Test Run - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}"

        test_run = TestRun(
            project_id=project.id,
            name=run_name,
            status=RunStatus.QUEUED.value,
            environment=req.environment or project.environment,
            concurrency=req.concurrency,
            total_tests=len(all_test_cases),
            passed_tests=0,
            failed_tests=0,
            warning_tests=0,
            error_tests=0,
            duration_ms=0.0
        )
        db.add(test_run)
        db.commit()
        db.refresh(test_run)

        logger.info(f"Created TestRun #{test_run.id} ('{test_run.name}') with {len(all_test_cases)} queued test cases")
        return test_run

    @classmethod
    async def execute_test_run(
        cls,
        run_id: int,
        db: Session
    ) -> TestRun:
        """
        Execute a queued TestRun with concurrency limits and record individual results.
        """
        test_run = db.query(TestRun).filter(TestRun.id == run_id).first()
        if not test_run:
            raise ValueError(f"TestRun #{run_id} not found.")

        # Validate lifecycle transition QUEUED -> RUNNING
        validate_state_transition(test_run.status, RunStatus.RUNNING.value)
        test_run.status = RunStatus.RUNNING.value
        test_run.started_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(test_run)

        # Retrieve target test cases
        query = db.query(TestCase).join(Endpoint).filter(
            Endpoint.project_id == test_run.project_id,
            TestCase.is_active == True
        )
        test_cases = query.all()

        semaphore = asyncio.Semaphore(test_run.concurrency)
        results: List[TestResult] = []

        async def _run_single_test_case(tc: TestCase) -> TestResult:
            async with semaphore:
                # Check for run cancellation mid-flight
                db.refresh(test_run)
                if test_run.status == RunStatus.CANCELLED.value:
                    return TestResult(
                        run_id=test_run.id,
                        test_case_id=tc.id,
                        endpoint_id=tc.endpoint_id,
                        status=TestResultStatus.CANCELLED.value,
                        test_name=tc.name,
                        http_method=tc.endpoint.method if tc.endpoint else "GET",
                        url=f"{test_run.project.base_url}{tc.endpoint.path if tc.endpoint else ''}",
                        response_code=None,
                        response_time_ms=0.0,
                        failure_type="RUN_CANCELLED",
                        failure_evidence={"message": "Run cancelled before test execution"}
                    )

                try:
                    eval_resp = await TestCaseService.evaluate_test_case(
                        test_case_id=tc.id,
                        db=db
                    )
                    
                    report = eval_resp.assertion_report

                    res_status = TestResultStatus.PASS.value if report.all_passed else TestResultStatus.FAIL.value
                    fail_type = None
                    evidence = {}

                    if not report.all_passed:
                        failed_rules = [r for r in report.results if not r.passed]
                        evidence = {
                            "summary": f"{report.failed_rules} of {report.total_rules} assertions failed",
                            "failed_rules_count": len(failed_rules),
                            "failures": [r.message for r in failed_rules]
                        }
                        if eval_resp.status_code and eval_resp.status_code >= 500:
                            fail_type = "SERVER_CRASH"
                        else:
                            fail_type = "ASSERTION_FAILED"

                    snippet = str(eval_resp.response_body)[:500] if eval_resp.response_body is not None else None

                    return TestResult(
                        run_id=test_run.id,
                        test_case_id=tc.id,
                        endpoint_id=tc.endpoint_id,
                        status=res_status,
                        test_name=tc.name,
                        http_method=eval_resp.http_method or (tc.endpoint.method if tc.endpoint else "GET"),
                        url=eval_resp.target_url,
                        response_code=eval_resp.status_code,
                        response_time_ms=eval_resp.latency_ms,
                        response_body_snippet=snippet,
                        response_headers=eval_resp.response_headers,
                        failure_type=fail_type,
                        failure_evidence=evidence
                    )
                except Exception as e:
                    logger.exception(f"Error executing test case #{tc.id} in Run #{test_run.id}: {e}")
                    return TestResult(
                        run_id=test_run.id,
                        test_case_id=tc.id,
                        endpoint_id=tc.endpoint_id,
                        status=TestResultStatus.ERROR.value,
                        test_name=tc.name,
                        http_method=tc.endpoint.method if tc.endpoint else "GET",
                        url=f"{test_run.project.base_url}{tc.endpoint.path if tc.endpoint else ''}",
                        response_code=None,
                        response_time_ms=0.0,
                        failure_type="EXECUTION_ERROR",
                        failure_evidence={"exception": str(e)}
                    )

        # Dispatch all test cases asynchronously
        if test_cases:
            tasks = [_run_single_test_case(tc) for tc in test_cases]
            results = await asyncio.gather(*tasks)
            for r in results:
                db.add(r)
            db.commit()

        # Check final status
        db.refresh(test_run)
        if test_run.status != RunStatus.CANCELLED.value:
            validate_state_transition(test_run.status, RunStatus.COMPLETED.value)
            test_run.status = RunStatus.COMPLETED.value

        test_run.finished_at = datetime.now(timezone.utc)
        
        # Calculate final metrics
        total, passed, failed, warnings, errors, _, dur_ms = calculate_run_metrics(
            results,
            test_run.started_at,
            test_run.finished_at
        )
        test_run.total_tests = total
        test_run.passed_tests = passed
        test_run.failed_tests = failed
        test_run.warning_tests = warnings
        test_run.error_tests = errors
        test_run.duration_ms = dur_ms

        db.commit()
        db.refresh(test_run)
        logger.info(f"TestRun #{test_run.id} finished with status '{test_run.status}' in {dur_ms}ms (Pass: {passed}/{total})")
        return test_run

    @classmethod
    def cancel_test_run(
        cls,
        run_id: int,
        reason: str,
        db: Session
    ) -> TestRun:
        """Cancel an ongoing or queued TestRun."""
        test_run = db.query(TestRun).filter(TestRun.id == run_id).first()
        if not test_run:
            raise ValueError(f"TestRun #{run_id} not found.")

        validate_state_transition(test_run.status, RunStatus.CANCELLED.value)
        test_run.status = RunStatus.CANCELLED.value
        test_run.cancellation_reason = reason
        test_run.finished_at = datetime.now(timezone.utc)
        
        if test_run.started_at:
            s = test_run.started_at.replace(tzinfo=None) if test_run.started_at.tzinfo else test_run.started_at
            f = test_run.finished_at.replace(tzinfo=None) if test_run.finished_at.tzinfo else test_run.finished_at
            delta = f - s
            test_run.duration_ms = max(0.0, round(delta.total_seconds() * 1000.0, 2))

        db.commit()
        db.refresh(test_run)
        logger.info(f"TestRun #{test_run.id} CANCELLED. Reason: {reason}")
        return test_run

    @classmethod
    def get_test_run(
        cls,
        run_id: int,
        db: Session
    ) -> TestRun:
        """Retrieve TestRun by ID."""
        test_run = db.query(TestRun).filter(TestRun.id == run_id).first()
        if not test_run:
            raise ValueError(f"TestRun #{run_id} not found.")
        return test_run

    @classmethod
    def list_project_runs(
        cls,
        project_id: int,
        db: Session,
        status: Optional[str] = None
    ) -> List[TestRun]:
        """List all test runs for a project ordered by creation time descending."""
        query = db.query(TestRun).filter(TestRun.project_id == project_id)
        if status:
            query = query.filter(TestRun.status == status.upper())
        return query.order_by(TestRun.created_at.desc()).all()

    @classmethod
    def delete_test_run(
        cls,
        run_id: int,
        db: Session
    ) -> bool:
        """Delete a TestRun and cascade delete all its TestResult records."""
        test_run = db.query(TestRun).filter(TestRun.id == run_id).first()
        if not test_run:
            raise ValueError(f"TestRun #{run_id} not found.")
        db.delete(test_run)
        db.commit()
        return True

    @classmethod
    def format_summary(cls, run: TestRun) -> TestRunSummaryResponse:
        """Format TestRun entity into summary DTO with pass_rate_pct."""
        pass_rate = round((run.passed_tests / run.total_tests * 100.0), 1) if run.total_tests > 0 else 0.0
        return TestRunSummaryResponse(
            id=run.id,
            project_id=run.project_id,
            name=run.name,
            status=RunStatus(run.status),
            environment=run.environment,
            concurrency=run.concurrency,
            total_tests=run.total_tests,
            passed_tests=run.passed_tests,
            failed_tests=run.failed_tests,
            warning_tests=run.warning_tests,
            error_tests=run.error_tests,
            pass_rate_pct=pass_rate,
            started_at=run.started_at,
            finished_at=run.finished_at,
            duration_ms=run.duration_ms,
            cancellation_reason=run.cancellation_reason,
            created_at=run.created_at,
            updated_at=run.updated_at
        )

    @classmethod
    def format_detail(cls, run: TestRun) -> TestRunDetailResponse:
        """Format TestRun entity into detailed DTO including all individual test results."""
        summary = cls.format_summary(run)
        results = [
            TestResultResponse(
                id=r.id,
                run_id=r.run_id,
                test_case_id=r.test_case_id,
                endpoint_id=r.endpoint_id,
                test_name=r.test_name,
                http_method=r.http_method,
                url=r.url,
                status=TestResultStatus(r.status),
                response_code=r.response_code,
                response_time_ms=r.response_time_ms,
                response_body_snippet=r.response_body_snippet,
                response_headers=r.response_headers,
                failure_type=r.failure_type,
                failure_evidence=r.failure_evidence,
                executed_at=r.executed_at
            )
            for r in run.test_results
        ]
        return TestRunDetailResponse(
            **summary.model_dump(),
            results=results
        )
