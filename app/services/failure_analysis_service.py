"""Business logic for the Failure Analysis Engine (Stage 18)."""
import json
import logging
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.entities.test_result import TestResult
from app.models.entities.test_run import TestRun
from app.models.schemas.failure_analysis import (
    CategorizeFailureRequest,
    FailureEvidence,
    PackageEvidenceRequest,
    RootCauseAssessment,
    RunFailureAnalysisReport,
)
from app.utils.evidence_packager import (
    build_evidence_id,
    build_historical_context,
    build_request_evidence,
    build_response_evidence,
    categorize_root_cause,
    derive_severity,
)

logger = logging.getLogger("app.services.failure_analysis")

FAILING_STATUSES = {"FAIL", "ERROR", "WARNING"}


class FailureAnalysisService:
    """Packages failures into standardized diagnostic evidence bundles."""

    @staticmethod
    def categorize(req: CategorizeFailureRequest) -> RootCauseAssessment:
        """Categorize a failure from raw signals without persisting anything."""
        return categorize_root_cause(
            status_code=req.status_code,
            expected_status=req.expected_status,
            response_body=req.response_body,
            latency_ms=req.latency_ms,
            max_latency_ms=req.max_latency_ms,
            network_error=req.network_error,
            is_negative_test=req.is_negative_test,
            schema_errors=req.schema_errors,
        )

    @staticmethod
    def package_adhoc(req: PackageEvidenceRequest) -> FailureEvidence:
        """Build a complete evidence bundle from a caller-supplied execution snapshot."""
        assessment = categorize_root_cause(
            status_code=req.status_code,
            expected_status=req.expected_status,
            response_body=req.response_body,
            latency_ms=req.latency_ms,
            max_latency_ms=req.max_latency_ms,
            network_error=req.network_error,
            is_negative_test=req.is_negative_test,
            schema_errors=[f.message for f in req.assertion_failures if f.message],
            assertion_failures=req.assertion_failures,
        )
        history = build_historical_context(req.previous_failures, req.total_observations)

        return FailureEvidence(
            evidence_id=build_evidence_id(
                req.test_name, req.url, req.status_code, assessment.category.value
            ),
            test_name=req.test_name,
            is_negative_test=req.is_negative_test,
            expected_status=req.expected_status,
            max_latency_ms=req.max_latency_ms,
            request=build_request_evidence(
                http_method=req.http_method,
                url=req.url,
                headers=req.request_headers,
                query_params=req.query_params,
                path_params=req.path_params,
                body=req.request_body,
            ),
            response=build_response_evidence(
                status_code=req.status_code,
                headers=req.response_headers,
                body=req.response_body,
                latency_ms=req.latency_ms,
                network_error=req.network_error,
            ),
            assertion_failures=req.assertion_failures,
            root_cause=assessment,
            severity=derive_severity(assessment, history),
            history=history,
        )

    @staticmethod
    def package_from_result(db: Session, result_id: int) -> Optional[FailureEvidence]:
        """Build an evidence bundle from a persisted TestResult row."""
        result = db.query(TestResult).filter(TestResult.id == result_id).first()
        if not result:
            return None
        return FailureAnalysisService._evidence_for_result(db, result)

    @staticmethod
    def _evidence_for_result(db: Session, result: TestResult) -> FailureEvidence:
        """Convert a single TestResult row into a FailureEvidence bundle."""
        try:
            evidence_blob = json.loads(result.failure_evidence_json or "{}")
        except (TypeError, ValueError):
            evidence_blob = {}
        if not isinstance(evidence_blob, dict):
            evidence_blob = {}
        try:
            response_headers = json.loads(result.response_headers_json or "{}")
        except (TypeError, ValueError):
            response_headers = {}

        network_error = evidence_blob.get("exception") or evidence_blob.get("network_error")
        expected_status = evidence_blob.get("expected_status")
        max_latency = evidence_blob.get("max_latency_ms")

        previous = 0
        total = 0
        if result.test_case_id is not None:
            history_rows = (
                db.query(TestResult)
                .filter(TestResult.test_case_id == result.test_case_id)
                .all()
            )
            total = len(history_rows)
            previous = sum(1 for row in history_rows if (row.status or "").upper() in FAILING_STATUSES)

        assessment = categorize_root_cause(
            status_code=result.response_code,
            expected_status=expected_status,
            response_body=result.response_body_snippet,
            latency_ms=result.response_time_ms,
            max_latency_ms=max_latency,
            network_error=network_error,
            is_negative_test=bool(evidence_blob.get("is_negative_test", False)),
            schema_errors=evidence_blob.get("schema_errors") or [],
        )
        history = build_historical_context(previous, total)

        return FailureEvidence(
            evidence_id=build_evidence_id(
                result.test_name, result.url, result.response_code, assessment.category.value
            ),
            test_name=result.test_name,
            test_case_id=result.test_case_id,
            endpoint_id=result.endpoint_id,
            run_id=result.run_id,
            expected_status=expected_status,
            max_latency_ms=max_latency,
            request=build_request_evidence(
                http_method=result.http_method,
                url=result.url,
                headers=evidence_blob.get("request_headers") or {},
                body=evidence_blob.get("request_body"),
            ),
            response=build_response_evidence(
                status_code=result.response_code,
                headers=response_headers,
                body=result.response_body_snippet,
                latency_ms=result.response_time_ms,
                network_error=network_error,
            ),
            root_cause=assessment,
            severity=derive_severity(assessment, history),
            history=history,
        )

    @staticmethod
    def analyze_run(db: Session, run_id: int) -> Optional[RunFailureAnalysisReport]:
        """Package every failing result in a run and summarize the distribution."""
        run = db.query(TestRun).filter(TestRun.id == run_id).first()
        if not run:
            return None

        results: List[TestResult] = (
            db.query(TestResult).filter(TestResult.run_id == run_id).all()
        )
        failures = [r for r in results if (r.status or "").upper() in FAILING_STATUSES]
        bundles = [FailureAnalysisService._evidence_for_result(db, r) for r in failures]

        category_breakdown: Dict[str, int] = {}
        severity_breakdown: Dict[str, int] = {}
        for bundle in bundles:
            key = bundle.root_cause.category.value
            category_breakdown[key] = category_breakdown.get(key, 0) + 1
            sev = bundle.severity.value
            severity_breakdown[sev] = severity_breakdown.get(sev, 0) + 1

        logger.info(
            f"Failure analysis for Run #{run_id}: {len(bundles)} failure(s) across "
            f"{len(category_breakdown)} category(s)"
        )

        return RunFailureAnalysisReport(
            run_id=run.id,
            run_name=run.name,
            total_results=len(results),
            total_failures=len(bundles),
            category_breakdown=category_breakdown,
            severity_breakdown=severity_breakdown,
            evidence=bundles,
        )
