"""Structured prompt synthesis for the AI recommendation layer (Stage 19, sub-stage 01)."""
import json
from typing import Any, Dict

from app.models.schemas.ai_recommendation import SynthesizedPrompt
from app.models.schemas.failure_analysis import FailureEvidence

# The model must return exactly this shape; anything else is rejected by the caller.
RECOMMENDATION_JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["likely_cause", "severity", "suggested_fix"],
    "properties": {
        "likely_cause": {"type": "string"},
        "severity": {"type": "string", "enum": ["CRITICAL", "HIGH", "MEDIUM", "LOW"]},
        "suggested_fix": {"type": "string"},
        "code_snippet": {"type": "string"},
        "confidence_pct": {"type": "number"},
    },
}

SYSTEM_PROMPT = (
    "You are an expert API Reliability and QA Engineer.\n"
    "A deterministic test engine has ALREADY decided that this test failed; that verdict is "
    "final and is not yours to revisit. Your only job is to explain the most likely underlying "
    "cause and propose a concrete fix.\n"
    "Rules:\n"
    "1. Never state whether the test passed or failed.\n"
    "2. Base every claim on the supplied evidence; do not invent endpoints, fields, or logs.\n"
    "3. If the evidence is insufficient, say so in likely_cause and lower confidence_pct.\n"
    "4. Output ONLY valid JSON matching the required schema. No prose, no markdown fences."
)

# Rough heuristic: English averages ~4 characters per token.
CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """Approximate the token count of a prompt for cost control."""
    return max(1, len(text) // CHARS_PER_TOKEN)


def format_evidence_block(evidence: FailureEvidence) -> str:
    """Render a FailureEvidence bundle as a compact, deterministic prompt block."""
    req = evidence.request
    res = evidence.response
    lines = [
        "EVIDENCE:",
        f"- Test: {evidence.test_name}",
        f"- Endpoint: {req.http_method} {req.url}",
        f"- Expected Status: {evidence.expected_status if evidence.expected_status is not None else 'not specified'}",
        f"- Received Status: {res.status_code if res.status_code is not None else 'no response'}",
    ]
    if res.network_error:
        lines.append(f"- Network Error: {res.network_error}")
    if res.latency_ms is not None:
        budget = f" (budget {evidence.max_latency_ms}ms)" if evidence.max_latency_ms else ""
        lines.append(f"- Latency: {res.latency_ms}ms{budget}")
    if evidence.is_negative_test:
        lines.append("- Test Type: NEGATIVE / adversarial input (server should reject with 4xx)")
    if req.body is not None:
        body = json.dumps(req.body) if isinstance(req.body, (dict, list)) else str(req.body)
        lines.append(f"- Request Payload: {body[:600]}")
    if res.body_snippet:
        lines.append(f"- Response Body: {res.body_snippet[:800]}")
    if res.content_type:
        lines.append(f"- Response Content-Type: {res.content_type}")
    if evidence.assertion_failures:
        lines.append("- Failed Assertions:")
        for failure in evidence.assertion_failures[:8]:
            lines.append(
                f"    * {failure.rule}: expected {failure.expected!r}, got {failure.actual!r}"
                f" - {failure.message}"
            )
    lines.append(f"- Deterministic Classification: {evidence.root_cause.category.value}")
    lines.append(f"- Classifier Summary: {evidence.root_cause.summary}")
    lines.append(f"- Severity: {evidence.severity.value}")
    history = evidence.history
    if history.total_observations:
        lines.append(
            f"- History: failed {history.previous_failures} of {history.total_observations} "
            f"observed runs ({history.failure_rate_pct}%, {history.persistence_rating})"
        )
    return "\n".join(lines)


def synthesize_prompt(evidence: FailureEvidence) -> SynthesizedPrompt:
    """Build the system/user prompt pair for a single failure evidence bundle."""
    user_prompt = (
        f"{format_evidence_block(evidence)}\n\n"
        "TASK: Identify the most likely root cause and the concrete code-level fix. "
        "Return JSON with keys: likely_cause, severity, suggested_fix, code_snippet, confidence_pct."
    )
    return SynthesizedPrompt(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        evidence_id=evidence.evidence_id,
        estimated_tokens=estimate_tokens(SYSTEM_PROMPT + user_prompt),
        response_schema=RECOMMENDATION_JSON_SCHEMA,
    )
