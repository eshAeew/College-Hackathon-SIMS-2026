"""Project and Workspace management API endpoints."""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.schemas.project import ProjectCreate, ProjectUpdate, ProjectResponse
from app.models.schemas.response import StandardResponse, ErrorResponse, ErrorDetail
from app.services.project_service import ProjectService

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.post(
    "",
    response_model=StandardResponse[ProjectResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create New Project",
    description="Register a new API testing project workspace."
)
def create_project(
    project_in: ProjectCreate,
    db: Session = Depends(get_db)
):
    project = ProjectService.create_project(db, project_in)
    return StandardResponse(
        success=True,
        data=ProjectResponse.model_validate(project),
        message=f"Project '{project.name}' registered successfully"
    )


@router.get(
    "",
    response_model=StandardResponse[List[ProjectResponse]],
    summary="List All Projects",
    description="Retrieve list of all active testing projects."
)
def list_projects(
    skip: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(100, ge=1, le=500, description="Pagination limit"),
    db: Session = Depends(get_db)
):
    projects = ProjectService.get_all_projects(db, skip=skip, limit=limit)
    data = [ProjectResponse.model_validate(p) for p in projects]
    return StandardResponse(
        success=True,
        data=data,
        message=f"Retrieved {len(data)} projects"
    )


@router.get(
    "/{project_id}",
    response_model=StandardResponse[ProjectResponse],
    summary="Get Project by ID",
    description="Retrieve full details for a specific project."
)
def get_project(
    project_id: int,
    db: Session = Depends(get_db)
):
    project = ProjectService.get_project_by_id(db, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID #{project_id} not found"
        )
    return StandardResponse(
        success=True,
        data=ProjectResponse.model_validate(project),
        message="Project details retrieved successfully"
    )


@router.put(
    "/{project_id}",
    response_model=StandardResponse[ProjectResponse],
    summary="Update Project",
    description="Update an existing project's name, base URL, or headers."
)
def update_project(
    project_id: int,
    project_update: ProjectUpdate,
    db: Session = Depends(get_db)
):
    project = ProjectService.get_project_by_id(db, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID #{project_id} not found"
        )
    updated = ProjectService.update_project(db, project, project_update)
    return StandardResponse(
        success=True,
        data=ProjectResponse.model_validate(updated),
        message=f"Project '{updated.name}' updated successfully"
    )


@router.delete(
    "/{project_id}",
    response_model=StandardResponse[dict],
    summary="Delete Project",
    description="Delete a project workspace and all associated endpoints."
)
def delete_project(
    project_id: int,
    db: Session = Depends(get_db)
):
    project = ProjectService.get_project_by_id(db, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID #{project_id} not found"
        )
    ProjectService.delete_project(db, project)
    return StandardResponse(
        success=True,
        data={"deleted_project_id": project_id},
        message=f"Project #{project_id} deleted successfully"
    )
