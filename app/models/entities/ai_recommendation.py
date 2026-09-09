"""AIRecommendation database entity model for persisting remediation proposals."""
import json
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship, backref

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
    # A dismissed card stays on the record - the evidence trail is the point -
    # but drops out of the dashboard feed and its counts. It also has to remain
    # a row: the overview regenerates a recommendation for any failed result
    # that lacks one, so a hard delete would simply grow it back.
    dismissed_at = Column(DateTime, nullable=True, index=True)

    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    # Relationships
    # passive_deletes hands the cascade to the database. Without it SQLAlchemy
    # de-associates instead: deleting a run or workspace left its cards behind
    # with a NULL test_result_id, still counting toward the KPI forever.
    test_result = relationship(
        "TestResult",
        backref=backref("ai_recommendations", cascade="all, delete-orphan", passive_deletes=True)
    )

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
