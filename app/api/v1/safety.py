"""REST API Router for Safety & Execution Controls (Stage 16)."""
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.schemas.response import StandardResponse
from app.models.schemas.safety import (
    AuditTestRunRequest,
    AuditTestRunResponse,
    EvaluateOperationRequest,
    EvaluateOperationResponse,
    SafetyPolicy,
    ValidateTargetRequest,
    ValidateTargetResponse,
)
from app.services.safety_service import SafetyService

logger = logging.getLogger("app.api.v1.safety")

router = APIRouter(prefix="/safety", tags=["Safety & Execution Controls"])


@router.post(
    "/validate-target",
    response_model=StandardResponse[ValidateTargetResponse],
    summary="Validate Target Host Authorization",
    status_code=status.HTTP_200_OK
)
def validate_target(
    req: ValidateTargetRequest,
    db: Session = Depends(get_db)
):
    """
    Checks if a target host URL is authorized for test dispatch and returns compliance status.
    """
    try:
        result = SafetyService.validate_target(req, db=db)
        return StandardResponse(
            success=result.is_authorized,
            data=result,
            message=result.message
        )
    except Exception as e:
        logger.error(f"Target validation failed: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/evaluate-operation",
    response_model=StandardResponse[EvaluateOperationResponse],
    summary="Evaluate Operation Risk & Destructive Safeguards",
    status_code=status.HTTP_200_OK
)
def evaluate_operation(
    req: EvaluateOperationRequest
):
    """
    Classifies operation risk level (SAFE_READ_ONLY, POTENTIALLY_DESTRUCTIVE, CRITICAL_DATA_PURGE) and checks confirmation.
    """
    try:
        result = SafetyService.evaluate_operation(req)
        return StandardResponse(
            success=result.is_permitted,
            data=result,
            message=result.reason
        )
    except Exception as e:
        logger.error(f"Operation evaluation failed: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/audit-test-run",
    response_model=StandardResponse[AuditTestRunResponse],
    summary="Pre-Flight Safety Audit of Batch Test Operations",
    status_code=status.HTTP_200_OK
)
def audit_test_run(
    req: AuditTestRunRequest
):
    """
    Scans a batch of test operations before execution, identifying blocked or destructive actions.
    """
    try:
        result = SafetyService.audit_test_run(req)
        return StandardResponse(
            success=result.is_run_permitted,
            data=result,
            message=f"Audit complete: {result.safe_operations} safe, {result.destructive_operations} destructive, {result.blocked_operations} blocked."
        )
    except Exception as e:
        logger.error(f"Test run audit failed: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "/projects/{project_id}/policy",
    response_model=StandardResponse[SafetyPolicy],
    summary="Get Project Safety Policy",
    status_code=status.HTTP_200_OK
)
def get_project_safety_policy(
    project_id: int,
    db: Session = Depends(get_db)
):
    """
    Retrieves the active safety policy, allowed hosts, and safeguards for a project.
    """
    try:
        result = SafetyService.get_project_safety_policy(project_id, db=db)
        return StandardResponse(
            success=True,
            data=result,
            message=f"Safety policy for Project #{project_id} retrieved successfully."
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get safety policy for project #{project_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.put(
    "/projects/{project_id}/policy",
    response_model=StandardResponse[SafetyPolicy],
    summary="Update Project Safety Policy",
    status_code=status.HTTP_200_OK
)
def update_project_safety_policy(
    project_id: int,
    policy: SafetyPolicy,
    db: Session = Depends(get_db)
):
    """
    Updates the safety policy for a project.
    """
    try:
        result = SafetyService.update_project_safety_policy(project_id, policy=policy, db=db)
        return StandardResponse(
            success=True,
            data=result,
            message=f"Safety policy for Project #{project_id} updated successfully."
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to update safety policy for project #{project_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
