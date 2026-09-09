"""REST API Router for Automatic Test Generation and Review Staging Area (Stage 15)."""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.schemas.response import StandardResponse
from app.models.schemas.test_generation import (
    AcceptStagedTestsRequest,
    AcceptStagedTestsResponse,
    AdHocTestGenerationRequest,
    BulkProjectTestGenerationRequest,
    BulkProjectTestGenerationResponse,
    EndpointTestGenerationRequest,
    TestGenerationOptions,
    TestGenerationStagingResponse,
)
from app.services.test_generation_service import TestGenerationService

logger = logging.getLogger("app.api.v1.test_generation")

router = APIRouter(tags=["Test Generation"])


@router.post(
    "/test-generation/generate-adhoc",
    response_model=StandardResponse[TestGenerationStagingResponse],
    summary="Synthesize Test Cases from Raw Schema (Ad-Hoc)",
    status_code=status.HTTP_200_OK
)
def generate_adhoc_tests(
    req: AdHocTestGenerationRequest
):
    """
    Synthesizes positive happy path and negative edge case test scenarios from arbitrary schema definitions.
    """
    try:
        result = TestGenerationService.generate_adhoc_tests(req)
        return StandardResponse(
            success=True,
            data=result,
            message=f"Synthesized {result.total_generated} test cases ({result.positive_count} positive, {result.negative_count} negative)."
        )
    except Exception as e:
        logger.error(f"Failed to generate ad-hoc test cases: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/endpoints/{endpoint_id}/generate-tests",
    response_model=StandardResponse[TestGenerationStagingResponse],
    summary="Synthesize & Stage Test Cases for Endpoint",
    status_code=status.HTTP_200_OK
)
def generate_endpoint_tests(
    endpoint_id: int,
    req: Optional[EndpointTestGenerationRequest] = None,
    db: Session = Depends(get_db)
):
    """
    Inspects endpoint schemas, parameters, and contracts to synthesize a staging preview of positive and negative tests.
    """
    try:
        options = req.options if req else TestGenerationOptions()
        result = TestGenerationService.generate_endpoint_tests(
            endpoint_id=endpoint_id,
            options=options,
            db=db
        )
        return StandardResponse(
            success=True,
            data=result,
            message=f"Generated {result.total_generated} staged test scenarios for endpoint #{endpoint_id}."
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to generate tests for endpoint #{endpoint_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/endpoints/{endpoint_id}/accept-tests",
    response_model=StandardResponse[AcceptStagedTestsResponse],
    summary="Approve & Persist Staged Test Cases",
    status_code=status.HTTP_201_CREATED
)
def accept_staged_tests(
    endpoint_id: int,
    req: AcceptStagedTestsRequest,
    db: Session = Depends(get_db)
):
    """
    Accepts, approves, and persists selected staged test cases directly into the database as active TestCase entities.
    """
    try:
        result = TestGenerationService.accept_staged_tests(
            endpoint_id=endpoint_id,
            req=req,
            db=db
        )
        return StandardResponse(
            success=True,
            data=result,
            message=result.message
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to accept staged tests for endpoint #{endpoint_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/projects/{project_id}/generate-tests",
    response_model=StandardResponse[BulkProjectTestGenerationResponse],
    summary="Bulk Synthesize Test Cases Across Project Endpoints",
    status_code=status.HTTP_200_OK
)
def generate_project_bulk_tests(
    project_id: int,
    req: BulkProjectTestGenerationRequest,
    db: Session = Depends(get_db)
):
    """
    Synthesizes test suites across all or specified active endpoints in a project with optional auto-acceptance.
    """
    try:
        result = TestGenerationService.generate_project_bulk_tests(
            project_id=project_id,
            req=req,
            db=db
        )
        return StandardResponse(
            success=True,
            data=result,
            message=f"Synthesized {result.total_tests_generated} test cases across {result.total_endpoints_processed} endpoints."
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to bulk generate tests for project #{project_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
