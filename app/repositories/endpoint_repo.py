"""Specialized repository for Endpoint entities."""
from typing import List, Optional
from sqlalchemy.orm import Session

from app.models.entities.endpoint import Endpoint
from app.repositories.base import BaseRepository


class EndpointRepository(BaseRepository[Endpoint]):
    """Repository for API endpoint registry."""

    def __init__(self, db: Session):
        super().__init__(Endpoint, db)

    def get_by_project(self, project_id: int, active_only: bool = False) -> List[Endpoint]:
        """Fetch all endpoints registered under a project workspace."""
        query = self.db.query(Endpoint).filter(Endpoint.project_id == project_id)
        if active_only:
            query = query.filter(Endpoint.is_active == True)
        return query.order_by(Endpoint.path.asc()).all()

    def get_by_path_and_method(self, project_id: int, method: str, path: str) -> Optional[Endpoint]:
        """Find endpoint by HTTP method and URL path within a project."""
        return (
            self.db.query(Endpoint)
            .filter(
                Endpoint.project_id == project_id,
                Endpoint.method == method.upper(),
                Endpoint.path == path
            )
            .first()
        )

    def count_by_project(self, project_id: int) -> int:
        """Count registered endpoints under a project."""
        return self.db.query(Endpoint).filter(Endpoint.project_id == project_id).count()
