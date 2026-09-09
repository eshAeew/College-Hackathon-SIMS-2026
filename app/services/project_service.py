"""Business logic service for Project / Workspace management and Summary stats."""
import logging
from typing import List, Optional
from sqlalchemy.orm import Session

from app.models.entities.project import Project
from app.models.schemas.project import ProjectCreate, ProjectUpdate, ProjectSummaryResponse, EnvironmentPreset

logger = logging.getLogger("app.services.project")


class ProjectService:
    """Service handling Project entity CRUD operations and workspace metrics."""

    @staticmethod
    def create_project(db: Session, project_in: ProjectCreate) -> Project:
        """Register a new Project record."""
        project = Project(
            name=project_in.name,
            description=project_in.description,
            base_url=project_in.base_url,
            environment=project_in.environment,
        )
        project.global_headers = project_in.global_headers
        db.add(project)
        db.commit()
        db.refresh(project)
        logger.info(f"Created Project #{project.id}: '{project.name}' ({project.base_url})")
        return project

    @staticmethod
    def get_all_projects(db: Session, skip: int = 0, limit: int = 100) -> List[Project]:
        """Retrieve paginated list of projects ordered by update time."""
        return db.query(Project).order_by(Project.updated_at.desc()).offset(skip).limit(limit).all()

    @staticmethod
    def get_project_by_id(db: Session, project_id: int) -> Optional[Project]:
        """Fetch project by ID."""
        return db.query(Project).filter(Project.id == project_id).first()

    @staticmethod
    def update_project(db: Session, project: Project, project_update: ProjectUpdate) -> Project:
        """Update existing project fields."""
        update_data = project_update.model_dump(exclude_unset=True)
        
        if "global_headers" in update_data:
            project.global_headers = update_data.pop("global_headers")
            
        for key, value in update_data.items():
            setattr(project, key, value)

        db.commit()
        db.refresh(project)
        logger.info(f"Updated Project #{project.id}: '{project.name}'")
        return project

    @staticmethod
    def delete_project(db: Session, project: Project) -> None:
        """Delete project record."""
        project_id = project.id
        project_name = project.name
        db.delete(project)
        db.commit()
        logger.info(f"Deleted Project #{project_id}: '{project_name}'")

    @staticmethod
    def get_project_summary(db: Session, project: Project) -> ProjectSummaryResponse:
        """Compute live workspace metadata and summary statistics for a project."""
        headers = project.global_headers
        has_auth = any(k.lower() in ("authorization", "x-api-key", "apikey", "token") for k in headers.keys())
        
        # Build standard environment presets
        presets = [
            EnvironmentPreset(name="development", base_url=project.base_url, is_active=(project.environment == "development")),
            EnvironmentPreset(name="staging", base_url=project.base_url.replace("localhost", "staging.api"), is_active=(project.environment == "staging")),
            EnvironmentPreset(name="production", base_url=project.base_url.replace("localhost", "api"), is_active=(project.environment == "production")),
        ]

        # In later stages (03, 06, 12), these will dynamically count from Endpoint, TestCase, and TestRun tables
        total_endpoints = 0
        total_test_cases = 0
        total_test_runs = 0
        health_score = 100.0

        return ProjectSummaryResponse(
            project_id=project.id,
            project_name=project.name,
            base_url=project.base_url,
            environment=project.environment,
            total_endpoints=total_endpoints,
            total_test_cases=total_test_cases,
            total_test_runs=total_test_runs,
            health_score=health_score,
            global_headers_count=len(headers),
            has_auth_header=has_auth,
            environment_presets=presets
        )
