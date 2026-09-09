"""Pydantic DTOs for the AI Recommendation Layer (Stage 19)."""
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.schemas.failure_analysis import FailureEvidence, PackageEvidenceRequest


class RecommendationSource(str, Enum):
    """Which engine produced the recommendation."""
    GEMINI_LLM = "GEMINI_LLM"
    RULE_BASED_HEURISTIC = "RULE_BASED_HEURISTIC"


class RecommendationSeverity(str, Enum):
    """Severity assigned to the recommended fix."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class SynthesizedPrompt(BaseModel):
    """The exact prompt pair that would be sent to an LLM."""
    system_prompt: str = Field(..., description="System role instruction enforcing JSON output")
    user_prompt: str = Field(..., description="Formatted failure evidence context")
    evidence_id: Optional[str] = Field(default=None)
    estimated_tokens: int = Field(default=0, description="Rough token estimate for cost control")
    response_schema: Dict[str, Any] = Field(
        default_factory=dict, description="JSON schema the model must satisfy"
    )


class FixRecommendation(BaseModel):
    """Structured remediation card returned to the developer."""
    evidence_id: Optional[str] = Field(default=None)
    root_cause_category: Optional[str] = Field(default=None)
    likely_cause: str = Field(..., description="Most probable underlying defect")
    severity: RecommendationSeverity = Field(default=RecommendationSeverity.MEDIUM)
    suggested_fix: str = Field(..., description="Concrete developer action")
    code_snippet: Optional[str] = Field(default=None, description="Illustrative remediation code")
    confidence_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    source: RecommendationSource = Field(default=RecommendationSource.RULE_BASED_HEURISTIC)
    model_name: Optional[str] = Field(default=None)
    references: List[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RecommendFromEvidenceRequest(BaseModel):
    """Generate a recommendation from an already-packaged evidence bundle."""
    evidence: FailureEvidence
    persist: bool = Field(default=False, description="Store the recommendation in the database")
    test_result_id: Optional[int] = Field(default=None, description="Result row to attach to")


class RecommendFromSnapshotRequest(PackageEvidenceRequest):
    """Package evidence and recommend a fix in a single call."""
    persist: bool = Field(default=False)
    test_result_id: Optional[int] = Field(default=None)


class AIRecommendationResponse(BaseModel):
    """Persisted recommendation record."""
    id: int
    test_result_id: Optional[int] = None
    evidence_id: Optional[str] = None
    root_cause_category: Optional[str] = None
    likely_cause: str
    severity: str
    suggested_fix: str
    code_snippet: Optional[str] = None
    confidence_pct: float
    source: str
    model_name: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AIEngineStatus(BaseModel):
    """Reports which recommendation engine is currently active."""
    ai_enabled: bool = Field(..., description="True when an LLM API key is configured")
    active_engine: RecommendationSource
    model_name: Optional[str] = None
    sdk_available: bool = Field(default=False, description="True when the google-genai SDK is importable")
    fallback_engine: RecommendationSource = RecommendationSource.RULE_BASED_HEURISTIC
    message: str = ""
