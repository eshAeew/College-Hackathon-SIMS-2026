"""Prompt synthesis and guardrail enforcement for the AI Recommendation Layer (Sub-Stage 19.01).

PRIME DIRECTIVE:
The deterministic execution and classification engines own the pass/fail and severity decisions.
The LLM's sole responsibility is explaining the failure context and proposing actionable code fixes.
The LLM is strictly prohibited from altering pass/fail verdicts or outputting free-form unstructured text.
"""
import json
from app.models.schemas.ai_recommendation import SynthesizedPrompt
from app.models.schemas.failure_analysis import FailureEvidence

SYSTEM_INSTRUCTION = """You are an expert Backend API Quality and Resilience Engineer for API Sentinel.
Your task is to analyze the provided diagnostic failure evidence and propose an exact root cause analysis and a concrete, ready-to-apply code fix.

STRICT RULES:
1. Never state whether the test passed or failed - that determination has already been made by the deterministic engine.
2. Focus strictly on explaining why the failure happened and how to fix it in code (e.g. FastAPI / Pydantic / SQLAlchemy / Express / Spring).
3. Return your response ONLY as valid JSON conforming to the schema below.
4. Provide a concrete code_snippet illustrating the fix.

JSON RESPONSE SCHEMA:
{
  "likely_cause": "<concise explanation of why the failure occurred>",
  "severity": "<CRITICAL | HIGH | MEDIUM | LOW | INFO>",
  "suggested_fix": "<step-by-step actionable remediation instructions>",
  "code_snippet": "<python/fastapi or framework code snippet fixing the bug>",
  "confidence_pct": <float between 0.0 and 100.0>,
  "references": ["<relevant docs or RFC URLs>"]
}
"""

RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["likely_cause", "severity", "suggested_fix"],
    "properties": {
        "likely_cause": {"type": "string"},
        "severity": {
            "type": "string",
            "enum": ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"],
        },
        "suggested_fix": {"type": "string"},
        "code_snippet": {"type": "string"},
        "confidence_pct": {"type": "number"},
        "references": {"type": "array", "items": {"type": "string"}},
    },
}


def synthesize_prompt(evidence: FailureEvidence) -> SynthesizedPrompt:
    """Build a structured, token-efficient prompt bundle from a FailureEvidence package."""
    assertions_text = "\n".join(
        f"- Target: {a.target}, Path: {a.path or 'N/A'}, Operator: {a.operator}, Expected: {a.expected}, Actual: {a.actual} ({a.message})"
        for a in evidence.assertion_failures
    ) or "None (status or network failure)"

    user_prompt = f"""DIAGNOSTIC EVIDENCE:
Evidence ID: {evidence.evidence_id}
Test Scenario: {evidence.test_name}
Target URL: [{evidence.request.http_method}] {evidence.request.url}
Is Adversarial / Negative Test: {evidence.is_negative_test}
Expected Status Code: {evidence.expected_status or 'N/A'}
Actual Status Code: {evidence.response.status_code or 'None (Connection Failed)'}
Latency: {evidence.response.latency_ms or 0.0:.1f}ms (Max Allowed SLA: {evidence.max_latency_ms or 'N/A'}ms)
Network Error: {evidence.response.network_error or 'None'}

REQUEST DETAILS:
Headers: {json.dumps(evidence.request.headers)}
Query Params: {json.dumps(evidence.request.query_params)}
Body Snippet: {evidence.request.body_snippet or 'None'}
Reproducible cURL: {evidence.request.curl_command}

RESPONSE DETAILS:
Headers: {json.dumps(evidence.response.headers)}
Body Snippet: {evidence.response.body_snippet or 'None'}

DETERMINISTIC DIAGNOSIS:
Root Cause Category: {evidence.root_cause.category.value}
Diagnostic Summary: {evidence.root_cause.description}
Historical Recurrence: {evidence.history.persistence_rating} ({evidence.history.failure_rate_pct}% failure rate over {evidence.history.total_observations} observations)

FAILED ASSERTIONS:
{assertions_text}

Analyze this failure and return the structured JSON remediation card.
"""
    # Approximate token estimation: ~4 chars per token
    token_est = (len(SYSTEM_INSTRUCTION) + len(user_prompt)) // 4

    return SynthesizedPrompt(
        system_prompt=SYSTEM_INSTRUCTION.strip(),
        user_prompt=user_prompt.strip(),
        response_schema=RESPONSE_SCHEMA,
        estimated_tokens=token_est,
        evidence_id=evidence.evidence_id,
    )
