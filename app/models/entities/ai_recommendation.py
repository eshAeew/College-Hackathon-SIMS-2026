"""AIRecommendation entity storing generated remediation guidance (Stage 19)."""
import json
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base


class AIRecommendation(Base):
    """Database entity storing a remediation recommendation for a failed execution."""
    __tablename__ = "ai_recommendations"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    test_result_id = Column(Integer, ForeignKey("test_results.id", ondelete="CASCADE"), nullable=True, index=True)

    evidence_id = Column(String(40), nullable=True, index=True)
    root_cause_category = Column(String(60), nullable=True, index=True)
    likely_cause = Column(Text, nullable=False)
    severity = Column(String(20), default="MEDIUM", nullable=False, index=True)
    suggested_fix = Column(Text, nullable=False)
    code_snippet = Column(Text, nullable=True)
    confidence_pct = Column(Float, default=0.0, nullable=False)

    source = Column(String(40), default="RULE_BASED_HEURISTIC", nullable=False, index=True)
    model_name = Column(String(60), nullable=True)
    references_json = Column(Text, default="[]", nullable=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    test_result = relationship("TestResult")

    @property
    def references(self) -> list:
        """Parse the references JSON string into a list."""
        try:
            return json.loads(self.references_json) if self.references_json else []
        except Exception:
            return []

    @references.setter
    def references(self, value: list) -> None:
        """Serialize the references list into a JSON string."""
        self.references_json = json.dumps(value or [])
