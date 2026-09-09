"""Specialized repository for AIRecommendation entities."""
from typing import List, Optional
from sqlalchemy.orm import Session

from app.models.entities.ai_recommendation import AIRecommendation
from app.repositories.base import BaseRepository


class AIRecommendationRepository(BaseRepository[AIRecommendation]):
    """Repository for AI diagnostic recommendations."""

    def __init__(self, db: Session):
        super().__init__(AIRecommendation, db)

    def get_by_test_result(self, test_result_id: int) -> List[AIRecommendation]:
        """Fetch recommendations linked to a specific test result."""
        return (
            self.db.query(AIRecommendation)
            .filter(AIRecommendation.test_result_id == test_result_id)
            .order_by(AIRecommendation.id.desc())
            .all()
        )

    def get_by_evidence_id(self, evidence_id: str) -> Optional[AIRecommendation]:
        """Find cached recommendation by deterministic evidence fingerprint hash."""
        return (
            self.db.query(AIRecommendation)
            .filter(AIRecommendation.evidence_id == evidence_id)
            .first()
        )

    def get_by_root_cause_category(self, category: str, limit: int = 50) -> List[AIRecommendation]:
        """Find recommendations matching a specific root-cause category."""
        return (
            self.db.query(AIRecommendation)
            .filter(AIRecommendation.root_cause_category == category)
            .order_by(AIRecommendation.id.desc())
            .limit(limit)
            .all()
        )
