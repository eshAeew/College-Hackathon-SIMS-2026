"""Service layer for Result Classification Engine and Test Run outcome aggregation (Stage 17)."""
import json
import logging
from typing import List, Optional
from sqlalchemy.orm import Session

from app.models.entities.project import Project
from app.models.entities.test_result import TestResult
from app.models.entities.test_run import TestRun
from app.models.schemas.result_classification import (
    BatchClassificationReport,
    BatchClassificationRequest,
    ClassifiedResultReport,
    ExecutionClassificationInput,
    TestRunClassificationReport,
)
from app.utils.result_classifier import (
    classify_batch_executions,
    classify_execution,
)

logger = logging.getLogger("app.services.result_classification")


class ResultClassificationService:
    """Service providing 4-tier outcome matrix classification and severity scoring."""

    @classmethod
    def classify_single(cls, item: ExecutionClassificationInput) -> ClassifiedResultReport:
        """Classify a single execution input into standard outcome tiers."""
        return classify_execution(item)

    @classmethod
    def classify_batch(cls, req: BatchClassificationRequest) -> BatchClassificationReport:
        """Classify a batch of ad-hoc or persisted execution inputs."""
        return classify_batch_executions(req.items)

    @classmethod
    def classify_test_run(cls, run_id: int, db: Session) -> TestRunClassificationReport:
        """Evaluate and classify all TestResult records belonging to a TestRun."""
        run = db.query(TestRun).filter(TestRun.id == run_id).first()
        if not run:
            raise ValueError(f"TestRun #{run_id} not found.")

        test_results = db.query(TestResult).filter(TestResult.run_id == run.id).all()
        inputs: List[ExecutionClassificationInput] = []

        for r in test_results:
            err_list = []
            if r.failure_type:
                err_list.append(f"Failure Type: {r.failure_type}")
            if r.failure_evidence and isinstance(r.failure_evidence, dict) and "message" in r.failure_evidence:
                err_list.append(r.failure_evidence["message"])

            is_pass = (r.status == "PASS")
            net_err = (
                r.failure_evidence.get("message", "Network error")
                if r.status in ("ERROR", "CANCELLED") and not r.response_code
                else None
            )

            inputs.append(
                ExecutionClassificationInput(
                    test_name=r.test_name,
                    http_method=r.http_method,
                    url=r.url,
                    status_code=r.response_code,
                    expected_status=200,
                    latency_ms=r.response_time_ms or 0.0,
                    max_latency_ms=1000.0,
                    assertions_passed=is_pass,
                    assertion_errors=err_list,
                    network_error=net_err,
                    is_negative_test=False,
                    endpoint_severity="medium"
                )
            )


        batch_report = classify_batch_executions(inputs)

        return TestRunClassificationReport(
            run_id=run.id,
            project_id=run.project_id,
            run_name=run.name,
            environment=run.environment,
            summary=batch_report.summary,
            prioritized_failures=batch_report.prioritized_failures,
            classified_results=batch_report.all_results
        )

    @classmethod
    def classify_project_latest(cls, project_id: int, db: Session) -> TestRunClassificationReport:
        """Retrieve and classify the latest TestRun execution for a Project."""
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError(f"Project #{project_id} not found.")

        latest_run = (
            db.query(TestRun)
            .filter(TestRun.project_id == project.id)
            .order_by(TestRun.created_at.desc())
            .first()
        )
        if not latest_run:
            raise ValueError(f"No test runs found for Project #{project_id}.")

        return cls.classify_test_run(run_id=latest_run.id, db=db)
