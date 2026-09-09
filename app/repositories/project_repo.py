"""Specialized repository for Project workspace entities."""
from typing import List, Optional
from sqlalchemy.orm import Session

from app.models.entities.project import Project
from app.repositories.base import BaseRepository


class ProjectRepository(BaseRepository[Project]):
    """Repository for workspace management and summary queries."""

    def __init__(self, db: Session):
        super().__init__(Project, db)

    def get_by_name(self, name: str) -> Optional[Project]:
        """Lookup project workspace by exact name."""
        return self.db.query(Project).filter(Project.name == name).first()

    def get_by_environment(self, environment: str) -> List[Project]:
        """Find projects configured for a specific target environment."""
        return self.db.query(Project).filter(Project.environment == environment).all()
