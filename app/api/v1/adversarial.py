"""Adversarial & Negative Testing API Endpoints."""
from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.schemas.response import StandardResponse
from app.models.schemas.adversarial import (
    PayloadMutationRequest,
    PayloadMutationResponse,
    NegativeTestEvaluationRequest,
    NegativeTestEvaluationReport,
    AdversarialEndpointScanRequest,
    AdversarialScanReport,
)
from app.services.adversarial_service import AdversarialService

router = APIRouter(prefix="/adversarial", tags=["Negative & Adversarial Testing Engine"])


@router.post(
    "/mutate",
    response_model=StandardResponse[PayloadMutationResponse],
    status_code=status.HTTP_200_OK,
    summary="Generate Adversarial Payload Mutations",
    description="Combinatorially synthesizes adversarial test payloads from baseline JSON (missing required fields, type inversions, boundary probes, null injections)."
)
async def generate_mutations_endpoint(
    req: PayloadMutationRequest
) -> StandardResponse[PayloadMutationResponse]:
    """Generate combinatorial negative/adversarial mutations."""
    res = AdversarialService.generate_mutations(req)
    return StandardResponse(
        success=True,
        data=res,
        message=f"Generated {res.total_mutations} unique adversarial mutation(s) using {len(res.strategies_used)} strategy(s)."
    )


@router.post(
    "/evaluate-response",
    response_model=StandardResponse[NegativeTestEvaluationReport],
    status_code=status.HTTP_200_OK,
    summary="Evaluate Negative Test Response (4xx vs 500 Classifier)",
    description="Evaluates whether an adversarial or negative test resulted in proper client rejection (HTTP 4xx) or exposed a backend crash vulnerability (HTTP 500) / silent acceptance (HTTP 2xx)."
)
async def evaluate_negative_response_endpoint(
    req: NegativeTestEvaluationRequest
) -> StandardResponse[NegativeTestEvaluationReport]:
    """Classify 4xx vs 500 negative test outcome."""
    report = AdversarialService.evaluate_negative_result(req)
    return StandardResponse(
        success=report.passed,
        data=report,
        message=report.message
    )


@router.post(
    "/endpoints/{endpoint_id}/scan",
    response_model=StandardResponse[AdversarialScanReport],
    status_code=status.HTTP_200_OK,
    summary="Automated Adversarial Fuzz Scan on Endpoint",
    description="Generates combinatorial mutations, executes them against the target endpoint, evaluates 4xx vs 500 backend responses, and produces an executive vulnerability audit report."
)
async def scan_endpoint_adversarial_endpoint(
    endpoint_id: int = Path(..., description="Target Endpoint ID", ge=1),
    req: AdversarialEndpointScanRequest = ...,
    db: Session = Depends(get_db)
) -> StandardResponse[AdversarialScanReport]:
    """Execute automated adversarial fuzz scan on target endpoint."""
    report = await AdversarialService.scan_endpoint_adversarial(endpoint_id, req, db)
    return StandardResponse(
        success=(len(report.critical_vulnerabilities) == 0),
        data=report,
        message=report.summary
    )
