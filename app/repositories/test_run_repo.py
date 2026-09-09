"""Specialized repository for TestRun entities."""
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from sqlalchemy.orm import Session

from app.models.entities.test_run import TestRun
from app.repositories.base import BaseRepository


class TestRunRepository(BaseRepository[TestRun]):
    """Repository for test run orchestration and lifecycle management."""

    def __init__(self, db: Session):
        super().__init__(TestRun, db)

    def get_recent_by_project(self, project_id: int, limit: int = 10) -> List[TestRun]:
        """Fetch recent test runs for a project ordered by ID descending."""
        return (
            self.db.query(TestRun)
            .filter(TestRun.project_id == project_id)
            .order_by(TestRun.id.desc())
            .limit(limit)
            .all()
        )

    def get_latest_completed(self, project_id: int) -> Optional[TestRun]:
        """Fetch the most recent completed test run for a project."""
        return (
            self.db.query(TestRun)
            .filter(TestRun.project_id == project_id, TestRun.status == "COMPLETED")
            .order_by(TestRun.id.desc())
            .first()
        )

    def get_runs_older_than(self, days: int) -> List[TestRun]:
        """Find test runs created before a given age threshold in days."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        return (
            self.db.query(TestRun)
            .filter(TestRun.created_at < cutoff)
            .all()
        )
