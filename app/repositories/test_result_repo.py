"""Specialized repository for TestResult entities."""
from typing import List, Optional
from sqlalchemy.orm import Session

from app.models.entities.test_result import TestResult
from app.repositories.base import BaseRepository


class TestResultRepository(BaseRepository[TestResult]):
    """Repository for individual test execution results."""

    def __init__(self, db: Session):
        super().__init__(TestResult, db)

    def get_by_run(self, run_id: int) -> List[TestResult]:
        """Fetch all test results for a specific test run."""
        return (
            self.db.query(TestResult)
            .filter(TestResult.run_id == run_id)
            .order_by(TestResult.id.asc())
            .all()
        )

    def get_failures_by_run(self, run_id: int) -> List[TestResult]:
        """Fetch failing or error results for a specific test run."""
        return (
            self.db.query(TestResult)
            .filter(TestResult.run_id == run_id, TestResult.status.in_(["FAIL", "ERROR", "WARNING"]))
            .all()
        )

    def get_history_for_endpoint(self, endpoint_id: int, limit: int = 20) -> List[TestResult]:
        """Fetch execution history for an endpoint across runs."""
        return (
            self.db.query(TestResult)
            .filter(TestResult.endpoint_id == endpoint_id)
            .order_by(TestResult.id.desc())
            .limit(limit)
            .all()
        )
