"""Specialized repository for TestCase entities."""
from typing import List, Optional
from sqlalchemy.orm import Session

from app.models.entities.test_case import TestCase
from app.models.entities.endpoint import Endpoint
from app.repositories.base import BaseRepository


class TestCaseRepository(BaseRepository[TestCase]):
    """Repository for test cases and assertion scenarios."""

    def __init__(self, db: Session):
        super().__init__(TestCase, db)

    def get_by_endpoint(self, endpoint_id: int, active_only: bool = False) -> List[TestCase]:
        """Fetch test cases belonging to a specific endpoint."""
        query = self.db.query(TestCase).filter(TestCase.endpoint_id == endpoint_id)
        if active_only:
            query = query.filter(TestCase.is_active == True)
        return query.all()

    def get_by_project(self, project_id: int) -> List[TestCase]:
        """Fetch all test cases across all endpoints in a project."""
        return (
            self.db.query(TestCase)
            .join(Endpoint, TestCase.endpoint_id == Endpoint.id)
            .filter(Endpoint.project_id == project_id)
            .all()
        )

    def get_by_severity(self, severity: str, project_id: Optional[int] = None) -> List[TestCase]:
        """Find test cases by severity rating."""
        query = self.db.query(TestCase).filter(TestCase.severity == severity.upper())
        if project_id is not None:
            query = query.join(Endpoint, TestCase.endpoint_id == Endpoint.id).filter(Endpoint.project_id == project_id)
        return query.all()
