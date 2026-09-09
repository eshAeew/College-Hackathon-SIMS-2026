"""Business logic service for API Endpoint registration, duplication, and management."""
import logging
from typing import List, Optional
from sqlalchemy.orm import Session

from app.models.entities.project import Project
from app.models.entities.endpoint import Endpoint
from app.models.schemas.endpoint import EndpointCreate, EndpointUpdate

logger = logging.getLogger("app.services.endpoint")


class EndpointService:
    """Service handling Endpoint entity CRUD operations, duplication, and activation states."""

    @staticmethod
    def create_endpoint(db: Session, project_id: int, endpoint_in: EndpointCreate) -> Optional[Endpoint]:
        """Register a new Endpoint under a specified Project."""
        # Verify parent project exists
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            logger.warning(f"Failed to create endpoint: Project #{project_id} not found")
            return None

        endpoint = Endpoint(
            project_id=project_id,
            name=endpoint_in.name,
            description=endpoint_in.description,
            method=endpoint_in.method.value if hasattr(endpoint_in.method, "value") else str(endpoint_in.method),
            path=endpoint_in.path,
            expected_status=endpoint_in.expected_status,
            is_active=endpoint_in.is_active,
        )
        endpoint.headers = endpoint_in.headers
        endpoint.query_params = endpoint_in.query_params
        endpoint.path_params = endpoint_in.path_params
        endpoint.body_schema = endpoint_in.body_schema

        db.add(endpoint)
        db.commit()
        db.refresh(endpoint)
        logger.info(f"Created Endpoint #{endpoint.id}: [{endpoint.method}] {endpoint.path} (Project #{project_id})")
        return endpoint

    @staticmethod
    def get_endpoints_by_project(
        db: Session,
        project_id: int,
        skip: int = 0,
        limit: int = 100,
        is_active: Optional[bool] = None
    ) -> List[Endpoint]:
        """Retrieve paginated list of endpoints for a specific project."""
        query = db.query(Endpoint).filter(Endpoint.project_id == project_id)
        if is_active is not None:
            query = query.filter(Endpoint.is_active == is_active)
        return query.order_by(Endpoint.id.asc()).offset(skip).limit(limit).all()

    @staticmethod
    def get_endpoint_by_id(db: Session, endpoint_id: int) -> Optional[Endpoint]:
        """Fetch endpoint by primary ID."""
        return db.query(Endpoint).filter(Endpoint.id == endpoint_id).first()

    @staticmethod
    def update_endpoint(db: Session, endpoint: Endpoint, endpoint_update: EndpointUpdate) -> Endpoint:
        """Update existing endpoint configuration and schemas."""
        update_data = endpoint_update.model_dump(exclude_unset=True)

        # Handle complex serialized JSON properties
        if "headers" in update_data:
            endpoint.headers = update_data.pop("headers")
        if "query_params" in update_data:
            endpoint.query_params = update_data.pop("query_params")
        if "path_params" in update_data:
            endpoint.path_params = update_data.pop("path_params")
        if "body_schema" in update_data:
            endpoint.body_schema = update_data.pop("body_schema")

        if "method" in update_data and update_data["method"] is not None:
            m = update_data.pop("method")
            endpoint.method = m.value if hasattr(m, "value") else str(m)

        for key, value in update_data.items():
            setattr(endpoint, key, value)

        db.commit()
        db.refresh(endpoint)
        logger.info(f"Updated Endpoint #{endpoint.id}: [{endpoint.method}] {endpoint.path}")
        return endpoint

    @staticmethod
    def delete_endpoint(db: Session, endpoint: Endpoint) -> None:
        """Delete endpoint record."""
        endpoint_id = endpoint.id
        endpoint_name = endpoint.name
        db.delete(endpoint)
        db.commit()
        logger.info(f"Deleted Endpoint #{endpoint_id}: '{endpoint_name}'")

    @staticmethod
    def duplicate_endpoint(db: Session, endpoint: Endpoint, new_name: Optional[str] = None) -> Endpoint:
        """Clone an existing endpoint with its full parameters and contract definitions."""
        cloned_name = new_name.strip() if (new_name and new_name.strip()) else f"[Copy] {endpoint.name}"
        
        cloned_endpoint = Endpoint(
            project_id=endpoint.project_id,
            name=cloned_name,
            description=endpoint.description,
            method=endpoint.method,
            path=endpoint.path,
            expected_status=endpoint.expected_status,
            is_active=endpoint.is_active,
        )
        cloned_endpoint.headers = endpoint.headers
        cloned_endpoint.query_params = endpoint.query_params
        cloned_endpoint.path_params = endpoint.path_params
        cloned_endpoint.body_schema = endpoint.body_schema

        db.add(cloned_endpoint)
        db.commit()
        db.refresh(cloned_endpoint)
        logger.info(f"Duplicated Endpoint #{endpoint.id} -> New Endpoint #{cloned_endpoint.id} ('{cloned_name}')")
        return cloned_endpoint

    @staticmethod
    def toggle_active(db: Session, endpoint: Endpoint) -> Endpoint:
        """Toggle active status of endpoint."""
        endpoint.is_active = not endpoint.is_active
        db.commit()
        db.refresh(endpoint)
        logger.info(f"Toggled active state of Endpoint #{endpoint.id} to: {endpoint.is_active}")
        return endpoint
