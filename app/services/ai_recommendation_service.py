"""AI Recommendation Layer service with graceful offline fallback (Stage 19).

Prime directive: the deterministic engine has already decided pass/fail. This layer only
explains a failure and proposes a fix. If the LLM is unavailable, unauthenticated, rate
limited, or returns unusable JSON, the rule-based engine answers instead - the platform
never loses this capability.
"""
import json
import logging
from typing import List, Optional

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities.ai_recommendation import AIRecommendation
from app.models.schemas.ai_recommendation import (
    AIEngineStatus,
    FixRecommendation,
    RecommendationSeverity,
    RecommendationSource,
    SynthesizedPrompt,
)
from app.models.schemas.failure_analysis import FailureEvidence, PackageEvidenceRequest
from app.services.failure_analysis_service import FailureAnalysisService
from app.utils.heuristic_recommender import recommend_from_evidence
from app.utils.prompt_synthesizer import synthesize_prompt

logger = logging.getLogger("app.services.ai_recommendation")


def _sdk_available() -> bool:
    """Report whether the optional google-genai SDK is importable."""
    try:
        import google.genai  # noqa: F401
        return True
    except Exception:
        return False


class AIRecommendationService:
    """Dual-mode remediation engine: Gemini when configured, heuristics otherwise."""

    @staticmethod
    def engine_status() -> AIEngineStatus:
        """Describe which recommendation engine will answer the next request."""
        settings = get_settings()
        sdk = _sdk_available()
        online = bool(settings.is_ai_enabled and sdk)
        if online:
            message = f"Google Gemini ({settings.GEMINI_MODEL}) is configured and will be used."
        elif settings.is_ai_enabled and not sdk:
            message = (
                "GEMINI_API_KEY is set but the google-genai SDK is not installed; "
                "falling back to the deterministic rule-based engine."
            )
        else:
            message = (
                "No GEMINI_API_KEY configured - running fully offline on the "
                "deterministic rule-based engine."
            )
        return AIEngineStatus(
            ai_enabled=settings.is_ai_enabled,
            active_engine=(
                RecommendationSource.GEMINI_LLM if online
                else RecommendationSource.RULE_BASED_HEURISTIC
            ),
            model_name=settings.GEMINI_MODEL if online else None,
            sdk_available=sdk,
            message=message,
        )

    @staticmethod
    def synthesize(evidence: FailureEvidence) -> SynthesizedPrompt:
        """Expose the exact prompt that would be sent to the LLM (sub-stage 19.01)."""
        return synthesize_prompt(evidence)

    @staticmethod
    def _call_gemini(prompt: SynthesizedPrompt) -> Optional[FixRecommendation]:
        """Attempt an LLM completion; return None so the caller can fall back."""
        settings = get_settings()
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            response = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=prompt.user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=prompt.system_prompt,
                    response_mime_type="application/json",
                    temperature=0.2,
                ),
            )
            payload = json.loads(response.text)
        except Exception as exc:
            logger.warning(
                f"Gemini recommendation unavailable ({type(exc).__name__}: {exc}); "
                "using rule-based fallback."
            )
            return None

        try:
            severity = RecommendationSeverity(str(payload.get("severity", "MEDIUM")).upper())
        except ValueError:
            severity = RecommendationSeverity.MEDIUM

        likely_cause = payload.get("likely_cause")
        suggested_fix = payload.get("suggested_fix")
        if not likely_cause or not suggested_fix:
            logger.warning("Gemini returned an incomplete card; using rule-based fallback.")
            return None

        return FixRecommendation(
            evidence_id=prompt.evidence_id,
            likely_cause=str(likely_cause),
            severity=severity,
            suggested_fix=str(suggested_fix),
            code_snippet=payload.get("code_snippet"),
            confidence_pct=float(payload.get("confidence_pct") or 70.0),
            source=RecommendationSource.GEMINI_LLM,
            model_name=settings.GEMINI_MODEL,
        )

    @classmethod
    def generate(
        cls,
        evidence: FailureEvidence,
        db: Optional[Session] = None,
        persist: bool = False,
        test_result_id: Optional[int] = None
    ) -> FixRecommendation:
        """Produce a remediation card, preferring the LLM and falling back to heuristics."""
        settings = get_settings()
        recommendation: Optional[FixRecommendation] = None

        if settings.is_ai_enabled and _sdk_available():
            recommendation = cls._call_gemini(synthesize_prompt(evidence))

        if recommendation is None:
            recommendation = recommend_from_evidence(evidence)

        # Keep the deterministic category attached regardless of which engine answered.
        recommendation.root_cause_category = evidence.root_cause.category.value
        recommendation.evidence_id = evidence.evidence_id

        if persist and db is not None:
            cls._persist(db, recommendation, test_result_id)

        return recommendation

    @classmethod
    def generate_from_snapshot(
        cls,
        req: PackageEvidenceRequest,
        db: Optional[Session] = None,
        persist: bool = False,
        test_result_id: Optional[int] = None
    ) -> FixRecommendation:
        """Package evidence and recommend a fix in a single call."""
        evidence = FailureAnalysisService.package_adhoc(req)
        return cls.generate(evidence, db=db, persist=persist, test_result_id=test_result_id)

    @staticmethod
    def _persist(
        db: Session,
        recommendation: FixRecommendation,
        test_result_id: Optional[int]
    ) -> AIRecommendation:
        """Store a generated recommendation for later retrieval."""
        record = AIRecommendation(
            test_result_id=test_result_id,
            evidence_id=recommendation.evidence_id,
            root_cause_category=recommendation.root_cause_category,
            likely_cause=recommendation.likely_cause,
            severity=recommendation.severity.value,
            suggested_fix=recommendation.suggested_fix,
            code_snippet=recommendation.code_snippet,
            confidence_pct=recommendation.confidence_pct,
            source=recommendation.source.value,
            model_name=recommendation.model_name,
        )
        record.references = recommendation.references
        db.add(record)
        db.commit()
        db.refresh(record)
        logger.info(
            f"Stored AIRecommendation #{record.id} ({record.source}) for "
            f"evidence {record.evidence_id}"
        )
        return record

    @staticmethod
    def for_result(db: Session, result_id: int) -> List[AIRecommendation]:
        """Return every stored recommendation attached to a test result."""
        return (
            db.query(AIRecommendation)
            .filter(AIRecommendation.test_result_id == result_id)
            .order_by(AIRecommendation.created_at.desc())
            .all()
        )

    @classmethod
    def recommend_for_result(
        cls,
        db: Session,
        result_id: int,
        persist: bool = True
    ) -> Optional[FixRecommendation]:
        """Package a stored result and generate its remediation card."""
        evidence = FailureAnalysisService.package_from_result(db, result_id)
        if evidence is None:
            return None
        return cls.generate(evidence, db=db, persist=persist, test_result_id=result_id)
