"""API Router for Dynamic Request Configuration, URL path interpolation, pre-flight validation, and HTTP request compilation."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.schemas.response import StandardResponse
from app.models.schemas.request_config import (
    RequestCompileOverride,
    DirectRequestBuilderRequest,
    CompiledRequestResponse,
    PreflightValidationRequest,
    PreflightValidationReport,
)
from app.services.project_service import ProjectService
from app.services.endpoint_service import EndpointService
from app.services.request_builder_service import RequestBuilderService

router = APIRouter(tags=["Request Configuration"])


@router.post(
    "/projects/{project_id}/endpoints/{endpoint_id}/build-request",
    response_model=StandardResponse[CompiledRequestResponse],
    summary="Build & Compile HTTP Request from Stored Endpoint",
    description="Interpolate path variables, merge project global headers with endpoint headers, serialize payload, and construct an executable request."
)
async def build_endpoint_request(
    project_id: int,
    endpoint_id: int,
    overrides: Optional[RequestCompileOverride] = None,
    db: Session = Depends(get_db)
):
    """Compile an endpoint specification and workspace into a concrete, executable HTTP request."""
    project = ProjectService.get_project_by_id(db, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project #{project_id} not found"
        )

    endpoint = EndpointService.get_endpoint_by_id(db, endpoint_id)
    if not endpoint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Endpoint #{endpoint_id} not found"
        )

    if endpoint.project_id != project.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Endpoint #{endpoint_id} does not belong to Project #{project_id}"
        )

    try:
        _, compiled_dto = RequestBuilderService.compile_endpoint_request(
            project=project,
            endpoint=endpoint,
            overrides=overrides
        )
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(val_err)
        )

    return StandardResponse(
        success=True,
        data=compiled_dto,
        message=f"Compiled HTTP request for [{compiled_dto.method}] {compiled_dto.url} successfully"
    )


@router.post(
    "/projects/{project_id}/endpoints/{endpoint_id}/preflight-check",
    response_model=StandardResponse[PreflightValidationReport],
    summary="Pre-Flight Validation Check for Stored Endpoint",
    description="Audit an endpoint request configuration for URL errors, missing path parameters, or malformed payloads before network execution."
)
async def preflight_check_endpoint(
    project_id: int,
    endpoint_id: int,
    overrides: Optional[RequestCompileOverride] = None,
    db: Session = Depends(get_db)
):
    """Perform pre-flight safety and syntax validation on an endpoint configuration."""
    project = ProjectService.get_project_by_id(db, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project #{project_id} not found"
        )

    endpoint = EndpointService.get_endpoint_by_id(db, endpoint_id)
    if not endpoint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Endpoint #{endpoint_id} not found"
        )

    if endpoint.project_id != project.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Endpoint #{endpoint_id} does not belong to Project #{project_id}"
        )

    report = RequestBuilderService.validate_endpoint_preflight(
        project=project,
        endpoint=endpoint,
        overrides=overrides
    )

    msg = "Pre-flight validation passed cleanly" if report.is_valid else "Pre-flight validation detected configuration errors"
    return StandardResponse(
        success=True,
        data=report,
        message=msg
    )


@router.post(
    "/requests/build",
    response_model=StandardResponse[CompiledRequestResponse],
    summary="Direct Ad-Hoc Request Builder",
    description="Directly build and compile an HTTP request from arbitrary parameters without saving to database."
)
async def build_direct_request(request_in: DirectRequestBuilderRequest):
    """Directly compile path variables, query parameters, headers, and body into an executable HTTP request."""
    try:
        _, compiled_dto = RequestBuilderService.compile_direct_request(request_in)
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(val_err)
        )

    return StandardResponse(
        success=True,
        data=compiled_dto,
        message=f"Compiled direct HTTP request for [{compiled_dto.method}] {compiled_dto.url} successfully"
    )


@router.post(
    "/requests/preflight-check",
    response_model=StandardResponse[PreflightValidationReport],
    summary="Direct Pre-Flight Configuration Validation",
    description="Validate URL scheme, hostname, port, path parameters, payload syntax, and headers before network execution."
)
async def preflight_check_direct(request_in: PreflightValidationRequest):
    """Audit an ad-hoc request configuration before execution, returning blocking errors and helpful warnings."""
    report = RequestBuilderService.validate_preflight(request_in)
    msg = "Pre-flight validation passed cleanly" if report.is_valid else "Pre-flight validation detected configuration errors"
    return StandardResponse(
        success=True,
        data=report,
        message=msg
    )
