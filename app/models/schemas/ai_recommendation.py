"""Pydantic schemas and DTOs for the AI Recommendation Layer (Stage 19)."""
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class RecommendationSource(str, Enum):
    """The engine that produced a remediation card."""
    GEMINI_LLM = "GEMINI_LLM"
    RULE_BASED_HEURISTIC = "RULE_BASED_HEURISTIC"


class RecommendationSeverity(str, Enum):
    """Impact severity rating of the underlying failure."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class SynthesizedPrompt(BaseModel):
    """Structured LLM prompt payload with guardrails and strict JSON contract."""
    system_prompt: str = Field(..., description="System instructions and schema rules")
    user_prompt: str = Field(..., description="Contextual prompt populated with diagnostic evidence")
    response_schema: Dict[str, Any] = Field(..., description="Expected JSON Schema contract")
    estimated_tokens: int = Field(..., ge=0, description="Approximate token count estimate")
    evidence_id: str = Field(..., description="Associated diagnostic evidence ID")


class FixRecommendation(BaseModel):
    """Structured remediation proposal for a test failure."""
    evidence_id: str = Field(..., description="Diagnostic evidence ID")
    root_cause_category: Optional[str] = Field(default=None, description="Deterministic root cause category")
    likely_cause: str = Field(..., description="Concise explanation of the underlying failure")
    severity: RecommendationSeverity = Field(default=RecommendationSeverity.MEDIUM, description="Assessed severity")
    suggested_fix: str = Field(..., description="Step-by-step remediation action plan")
    code_snippet: Optional[str] = Field(default=None, description="Ready-to-apply code fix snippet")
    confidence_pct: float = Field(default=80.0, ge=0.0, le=100.0, description="Confidence percentage")
    source: RecommendationSource = Field(..., description="GEMINI_LLM or RULE_BASED_HEURISTIC")
    model_name: Optional[str] = Field(default=None, description="LLM model name if answered by AI")
    references: List[str] = Field(default_factory=list, description="Relevant documentation / RFC links")


class AIEngineStatus(BaseModel):
    """Status probe for the AI Recommendation service."""
    ai_enabled: bool = Field(..., description="True if external Gemini API key is configured")
    active_engine: RecommendationSource = Field(..., description="Engine answering current requests")
    model_name: Optional[str] = Field(default=None, description="Configured LLM model name")
    sdk_available: bool = Field(..., description="True if google-genai SDK is importable")
    message: str = Field(..., description="Human-readable operational status message")


class GenerateRecommendationRequest(BaseModel):
    """Request payload for generating remediation on an ad-hoc snapshot."""
    test_name: str = Field(..., description="Name of the test scenario")
    url: str = Field(..., description="Executed URL")
    http_method: str = Field(default="GET", description="HTTP Method")
    status_code: Optional[int] = Field(default=None, description="Status code received")
    expected_status: Optional[int] = Field(default=None, description="Expected status code")
    response_body: Optional[str] = Field(default=None, description="Response body snippet")
    latency_ms: Optional[float] = Field(default=None, description="Latency in ms")
    max_latency_ms: Optional[float] = Field(default=None, description="Max latency allowed in ms")
    network_error: Optional[str] = Field(default=None, description="Network exception name")
    is_negative_test: bool = Field(default=False, description="True if this was an adversarial test")
    persist: bool = Field(default=False, description="Whether to persist recommendation to database")
