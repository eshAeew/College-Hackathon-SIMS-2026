"""Adversarial Testing Service: Combinatorial Mutation, 4xx/500 Classifier, and Endpoint Scanner."""
import logging
from typing import Any, Dict, List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.entities.endpoint import Endpoint
from app.models.entities.project import Project
from app.models.schemas.adversarial import (
    MutationStrategy,
    MutatedPayload,
    PayloadMutationRequest,
    PayloadMutationResponse,
    NegativeTestEvaluationRequest,
    NegativeTestEvaluationReport,
    AdversarialEndpointScanRequest,
    AdversarialScanItemResult,
    AdversarialScanReport,
)
from app.models.schemas.execution import EndpointExecutionRequest, ExecutionOptions
from app.models.schemas.request_config import RequestCompileOverride
from app.utils.mutation_engine import generate_all_mutations
from app.utils.adversarial_classifier import classify_negative_response
from app.services.http_dispatcher import HttpDispatcherService

logger = logging.getLogger("app.services.adversarial_service")


class AdversarialService:
    """Service layer managing adversarial mutation synthesis and 4xx vs 500 vulnerability detection."""

    @staticmethod
    def generate_mutations(req: PayloadMutationRequest) -> PayloadMutationResponse:
        """Generate combinatorial adversarial payload mutations."""
        strategies = [s.value for s in req.strategies] if req.strategies else None
        raw_mutations = generate_all_mutations(
            baseline_payload=req.baseline_payload,
            schema_definition=req.schema_definition,
            strategies=strategies,
            max_count=req.max_mutations
        )

        mutations = [
            MutatedPayload(
                mutation_id=m["mutation_id"],
                strategy=m["strategy"],
                target_field=m["target_field"],
                description=m["description"],
                original_value=m.get("original_value"),
                mutated_value=m.get("mutated_value"),
                payload=m["payload"],
                expected_status_category=m.get("expected_status_category", "4xx")
            )
            for m in raw_mutations
        ]

        strategies_used = list({m.strategy for m in mutations})
        return PayloadMutationResponse(
            total_mutations=len(mutations),
            strategies_used=strategies_used,
            mutations=mutations
        )

    @staticmethod
    def evaluate_negative_result(req: NegativeTestEvaluationRequest) -> NegativeTestEvaluationReport:
        """Classify negative test outcome for 4xx vs 500 vulnerability."""
        raw_result = classify_negative_response(
            status_code=req.status_code,
            response_body=req.response_body,
            mutation_info={"target_field": req.target_field, "strategy": req.strategy}
        )
        return NegativeTestEvaluationReport(
            passed=raw_result["passed"],
            status_code=raw_result["status_code"],
            classification=raw_result["classification"],
            severity=raw_result["severity"],
            verdict=raw_result["verdict"],
            message=raw_result["message"],
            defect_type=raw_result.get("defect_type"),
            recommendation=raw_result.get("recommendation")
        )

    @classmethod
    async def scan_endpoint_adversarial(
        cls,
        endpoint_id: int,
        req: AdversarialEndpointScanRequest,
        db: Session
    ) -> AdversarialScanReport:
        """Execute automated adversarial fuzz scan on an endpoint to uncover 500 crash or 2xx leak vulnerabilities."""
        endpoint = db.query(Endpoint).filter(Endpoint.id == endpoint_id).first()
        if not endpoint:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Endpoint with ID {endpoint_id} not found."
            )

        # Build baseline payload from body_schema or default
        baseline = {}
        if endpoint.body_schema and isinstance(endpoint.body_schema, dict):
            properties = endpoint.body_schema.get("properties", {})
            for k, prop in properties.items():
                p_type = prop.get("type", "string")
                if p_type == "integer":
                    baseline[k] = 100
                elif p_type == "number":
                    baseline[k] = 19.99
                elif p_type == "boolean":
                    baseline[k] = True
                elif p_type == "array":
                    baseline[k] = ["sample"]
                elif p_type == "object":
                    baseline[k] = {"sample_key": "sample_val"}
                else:
                    baseline[k] = f"sample_{k}"
        
        if not baseline:
            baseline = {"sample_param": "valid_value", "id": 1}

        # Generate mutations
        strategies = [s.value for s in req.strategies] if req.strategies else None
        raw_mutations = generate_all_mutations(
            baseline_payload=baseline,
            schema_definition=endpoint.body_schema,
            strategies=strategies,
            max_count=req.max_mutations
        )

        all_results: List[AdversarialScanItemResult] = []
        crashes_5xx = 0
        leaks_2xx = 0
        handled_4xx = 0

        for mut in raw_mutations:
            # Dispatch against target endpoint
            exec_req = EndpointExecutionRequest(
                request_override=RequestCompileOverride(
                    body_type="json",
                    body_json=mut["payload"]
                ),
                options=ExecutionOptions(
                    timeout_seconds=req.timeout_seconds,
                    follow_redirects=True
                )
            )

            try:
                exec_result = await HttpDispatcherService.dispatch_endpoint(
                    project_id=endpoint.project_id,
                    endpoint_id=endpoint.id,
                    req=exec_req,
                    db=db
                )
                actual_status = exec_result.status_code
                latency = getattr(exec_result, "elapsed_ms", 0.0)
                body = exec_result.body
            except Exception as exc:
                logger.error(f"Adversarial dispatch exception: {type(exc).__name__}: {exc}")
                actual_status = 500
                latency = 0.0
                body = str(exc)

            eval_dict = classify_negative_response(
                status_code=actual_status if actual_status is not None else 500,
                response_body=body,
                mutation_info=mut
            )

            eval_report = NegativeTestEvaluationReport(
                passed=eval_dict["passed"],
                status_code=eval_dict["status_code"],
                classification=eval_dict["classification"],
                severity=eval_dict["severity"],
                verdict=eval_dict["verdict"],
                message=eval_dict["message"],
                defect_type=eval_dict.get("defect_type"),
                recommendation=eval_dict.get("recommendation")
            )

            if eval_report.classification == "PROPERLY_HANDLED_4XX":
                handled_4xx += 1
            elif eval_report.classification == "UNHANDLED_SERVER_EXCEPTION_5XX":
                crashes_5xx += 1
            elif eval_report.classification == "UNVALIDATED_ACCEPTANCE_2XX":
                leaks_2xx += 1

            all_results.append(
                AdversarialScanItemResult(
                    mutation_id=mut["mutation_id"],
                    strategy=mut["strategy"],
                    target_field=mut["target_field"],
                    description=mut["description"],
                    mutated_payload=mut["payload"],
                    status_code=actual_status,
                    latency_ms=latency,
                    evaluation=eval_report
                )
            )

        total_tested = len(all_results)
        safety_score = round((handled_4xx / total_tested) * 100, 2) if total_tested > 0 else 100.0
        critical_vulns = [r for r in all_results if r.evaluation.severity in ("CRITICAL", "HIGH")]

        summary = (
            f"Adversarial Fuzz Scan Completed for [{endpoint.method}] {endpoint.path}: "
            f"{handled_4xx}/{total_tested} properly rejected ({safety_score}% Safety Score). "
            f"Found {crashes_5xx} unhandled 5xx crash(es) and {leaks_2xx} unvalidated 2xx leak(s)."
        )

        return AdversarialScanReport(
            endpoint_id=endpoint.id,
            endpoint_name=endpoint.name,
            endpoint_path=endpoint.path,
            total_mutations_tested=total_tested,
            properly_handled_4xx_count=handled_4xx,
            unhandled_5xx_crashes_count=crashes_5xx,
            unvalidated_2xx_leaks_count=leaks_2xx,
            safety_score=safety_score,
            critical_vulnerabilities=critical_vulns,
            all_results=all_results,
            summary=summary
        )
