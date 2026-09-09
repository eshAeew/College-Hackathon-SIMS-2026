"""API Router for Endpoint Registration, Configuration, Duplication, and CRUD operations."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.schemas.response import StandardResponse
from app.models.schemas.endpoint import (
    EndpointCreate,
    EndpointUpdate,
    EndpointResponse,
    EndpointDuplicate,
)
from app.services.endpoint_service import EndpointService
from app.services.project_service import ProjectService

router = APIRouter(tags=["Endpoints"])


@router.post(
    "/projects/{project_id}/endpoints",
    response_model=StandardResponse[EndpointResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Register New Endpoint in Project"
)
async def create_endpoint(
    project_id: int,
    endpoint_in: EndpointCreate,
    db: Session = Depends(get_db)
):
    """Register a new REST API endpoint under a project workspace with path, method, and parameters."""
    project = ProjectService.get_project_by_id(db, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project #{project_id} not found"
        )

    endpoint = EndpointService.create_endpoint(db, project_id=project_id, endpoint_in=endpoint_in)
    return StandardResponse(
        success=True,
        data=EndpointResponse.model_validate(endpoint),
        message=f"Endpoint '[{endpoint.method}] {endpoint.path}' registered successfully"
    )


@router.get(
    "/projects/{project_id}/endpoints",
    response_model=StandardResponse[List[EndpointResponse]],
    summary="List All Endpoints for a Project"
)
async def list_project_endpoints(
    project_id: int,
    is_active: Optional[bool] = Query(None, description="Filter endpoints by active status"),
    skip: int = Query(0, ge=0, description="Offset for pagination"),
    limit: int = Query(100, ge=1, le=1000, description="Max items per page"),
    db: Session = Depends(get_db)
):
    """Retrieve all endpoints registered within a specific project workspace."""
    project = ProjectService.get_project_by_id(db, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project #{project_id} not found"
        )

    endpoints = EndpointService.get_endpoints_by_project(
        db,
        project_id=project_id,
        skip=skip,
        limit=limit,
        is_active=is_active
    )
    return StandardResponse(
        success=True,
        data=[EndpointResponse.model_validate(ep) for ep in endpoints],
        message=f"Retrieved {len(endpoints)} endpoint(s) for Project #{project_id}"
    )


@router.get(
    "/endpoints/{endpoint_id}",
    response_model=StandardResponse[EndpointResponse],
    summary="Get Endpoint Details by ID"
)
async def get_endpoint(
    endpoint_id: int,
    db: Session = Depends(get_db)
):
    """Retrieve specific endpoint configuration by its unique identifier."""
    endpoint = EndpointService.get_endpoint_by_id(db, endpoint_id)
    if not endpoint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Endpoint #{endpoint_id} not found"
        )
    return StandardResponse(
        success=True,
        data=EndpointResponse.model_validate(endpoint),
        message="Endpoint retrieved successfully"
    )


@router.put(
    "/endpoints/{endpoint_id}",
    response_model=StandardResponse[EndpointResponse],
    summary="Update Endpoint Configuration"
)
async def update_endpoint(
    endpoint_id: int,
    endpoint_update: EndpointUpdate,
    db: Session = Depends(get_db)
):
    """Update method, path, headers, query parameters, path variables, or expected schema for an endpoint."""
    endpoint = EndpointService.get_endpoint_by_id(db, endpoint_id)
    if not endpoint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Endpoint #{endpoint_id} not found"
        )

    updated_endpoint = EndpointService.update_endpoint(db, endpoint=endpoint, endpoint_update=endpoint_update)
    return StandardResponse(
        success=True,
        data=EndpointResponse.model_validate(updated_endpoint),
        message=f"Endpoint #{endpoint_id} updated successfully"
    )


@router.delete(
    "/endpoints/{endpoint_id}",
    response_model=StandardResponse[dict],
    summary="Delete Endpoint"
)
async def delete_endpoint(
    endpoint_id: int,
    db: Session = Depends(get_db)
):
    """Delete an API endpoint from the database."""
    endpoint = EndpointService.get_endpoint_by_id(db, endpoint_id)
    if not endpoint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Endpoint #{endpoint_id} not found"
        )

    EndpointService.delete_endpoint(db, endpoint=endpoint)
    return StandardResponse(
        success=True,
        data={"deleted_id": endpoint_id},
        message=f"Endpoint #{endpoint_id} deleted successfully"
    )


@router.post(
    "/endpoints/{endpoint_id}/duplicate",
    response_model=StandardResponse[EndpointResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Duplicate / Clone Endpoint"
)
async def duplicate_endpoint(
    endpoint_id: int,
    duplicate_in: Optional[EndpointDuplicate] = None,
    db: Session = Depends(get_db)
):
    """Duplicate an existing endpoint with its full parameter and contract configuration."""
    endpoint = EndpointService.get_endpoint_by_id(db, endpoint_id)
    if not endpoint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Endpoint #{endpoint_id} not found"
        )

    new_name = duplicate_in.name if duplicate_in else None
    duplicated = EndpointService.duplicate_endpoint(db, endpoint=endpoint, new_name=new_name)
    return StandardResponse(
        success=True,
        data=EndpointResponse.model_validate(duplicated),
        message=f"Endpoint #{endpoint_id} cloned as #{duplicated.id} successfully"
    )


@router.patch(
    "/endpoints/{endpoint_id}/toggle-active",
    response_model=StandardResponse[EndpointResponse],
    summary="Toggle Endpoint Active State"
)
async def toggle_endpoint_active(
    endpoint_id: int,
    db: Session = Depends(get_db)
):
    """Enable or disable endpoint execution during automated test suite runs."""
    endpoint = EndpointService.get_endpoint_by_id(db, endpoint_id)
    if not endpoint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Endpoint #{endpoint_id} not found"
        )

    toggled = EndpointService.toggle_active(db, endpoint=endpoint)
    state_str = "enabled" if toggled.is_active else "disabled"
    return StandardResponse(
        success=True,
        data=EndpointResponse.model_validate(toggled),
        message=f"Endpoint #{endpoint_id} is now {state_str}"
    )
