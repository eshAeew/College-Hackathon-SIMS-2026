"""AIRecommendation database entity model for persisting remediation proposals."""
import json
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.core.database import Base


class AIRecommendation(Base):
    """Database entity storing an AI- or rule-generated remediation recommendation."""
    __tablename__ = "ai_recommendations"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    test_result_id = Column(
        Integer,
        ForeignKey("test_results.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    evidence_id = Column(String(50), nullable=False, index=True)
    root_cause_category = Column(String(60), nullable=False, index=True)
    likely_cause = Column(Text, nullable=False)
    severity = Column(String(20), nullable=False, default="MEDIUM")
    suggested_fix = Column(Text, nullable=False)
    code_snippet = Column(Text, nullable=True)
    confidence_pct = Column(Float, nullable=False, default=80.0)
    source = Column(String(40), nullable=False, default="RULE_BASED_HEURISTIC")
    model_name = Column(String(60), nullable=True)
    references_json = Column(Text, default="[]", nullable=False)
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    # Relationships
    test_result = relationship("TestResult", backref="ai_recommendations")

    @property
    def references(self) -> list:
        """Parse references JSON string into list."""
        try:
            return json.loads(self.references_json) if self.references_json else []
        except Exception:
            return []

    @references.setter
    def references(self, value: list) -> None:
        """Serialize references list into JSON string."""
        self.references_json = json.dumps(value or [])
