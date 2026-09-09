"""Pure helpers that package failure evidence and categorize root causes (Stage 18)."""
import hashlib
import json
from typing import Any, Dict, List, Optional

from app.models.schemas.failure_analysis import (
    EvidenceSeverity,
    HistoricalContext,
    RequestEvidence,
    ResponseEvidence,
    RootCauseAssessment,
    RootCauseCategory,
)

# Header names whose values must never appear in stored evidence or LLM prompts.
SENSITIVE_HEADERS = {
    "authorization", "proxy-authorization", "cookie", "set-cookie",
    "x-api-key", "api-key", "x-auth-token", "auth-token", "x-access-token",
}

MAX_BODY_SNIPPET_CHARS = 2000

SERVER_EXCEPTION_MARKERS = (
    "traceback", "keyerror", "typeerror", "valueerror", "attributeerror",
    "nullpointerexception", "nullreferenceexception", "indexerror",
    "unhandled", "internal server error", "stack trace",
)


def mask_sensitive_headers(headers: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """Return headers with credential-bearing values replaced by a redaction marker."""
    masked: Dict[str, str] = {}
    for key, value in (headers or {}).items():
        masked[str(key)] = "***REDACTED***" if str(key).lower() in SENSITIVE_HEADERS else str(value)
    return masked


def snippet_body(body: Any, limit: int = MAX_BODY_SNIPPET_CHARS) -> Optional[str]:
    """Render a response body as a bounded text snippet suitable for evidence storage."""
    if body is None:
        return None
    if isinstance(body, (dict, list)):
        try:
            text = json.dumps(body, ensure_ascii=False)
        except (TypeError, ValueError):
            text = str(body)
    else:
        text = str(body)
    if len(text) > limit:
        return text[:limit] + f"... [truncated {len(text) - limit} chars]"
    return text


def build_curl_command(
    method: str,
    url: str,
    headers: Optional[Dict[str, Any]] = None,
    body: Any = None
) -> str:
    """Build a copy-paste cURL reproduction command with credentials masked."""
    parts = [f"curl -X {method.upper()}", f'"{url}"']
    for key, value in mask_sensitive_headers(headers).items():
        parts.append(f'-H "{key}: {value}"')
    if body is not None:
        payload = json.dumps(body, ensure_ascii=False) if isinstance(body, (dict, list)) else str(body)
        parts.append(f"-d '{payload}'")
    return " ".join(parts)


def build_evidence_id(test_name: str, url: str, status_code: Optional[int], category: str) -> str:
    """Deterministic identifier so identical failures share one evidence id."""
    raw = f"{test_name}|{url}|{status_code}|{category}"
    return "EV-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12].upper()


def build_request_evidence(
    http_method: str,
    url: str,
    headers: Optional[Dict[str, Any]] = None,
    query_params: Optional[Dict[str, Any]] = None,
    path_params: Optional[Dict[str, Any]] = None,
    body: Any = None
) -> RequestEvidence:
    """Assemble the request half of an evidence bundle."""
    return RequestEvidence(
        http_method=(http_method or "GET").upper(),
        url=url or "",
        headers=mask_sensitive_headers(headers),
        query_params=dict(query_params or {}),
        path_params=dict(path_params or {}),
        body=body,
        curl_command=build_curl_command(http_method or "GET", url or "", headers, body),
    )


def build_response_evidence(
    status_code: Optional[int] = None,
    headers: Optional[Dict[str, Any]] = None,
    body: Any = None,
    latency_ms: Optional[float] = None,
    network_error: Optional[str] = None,
    status_text: Optional[str] = None
) -> ResponseEvidence:
    """Assemble the response half of an evidence bundle."""
    masked = mask_sensitive_headers(headers)
    content_type = None
    for key, value in masked.items():
        if key.lower() == "content-type":
            content_type = value
            break
    return ResponseEvidence(
        status_code=status_code,
        status_text=status_text,
        headers=masked,
        body_snippet=snippet_body(body),
        content_type=content_type,
        latency_ms=round(latency_ms, 3) if isinstance(latency_ms, (int, float)) else None,
        network_error=network_error,
    )


def build_historical_context(previous_failures: int, total_observations: int) -> HistoricalContext:
    """Summarize how often this failure has been seen before."""
    total = max(int(total_observations or 0), 0)
    prev = max(int(previous_failures or 0), 0)
    rate = round((prev / total) * 100.0, 2) if total else 0.0
    if prev == 0:
        rating = "NEW"
    elif total and rate >= 80.0:
        rating = "CHRONIC"
    elif prev >= 2:
        rating = "INTERMITTENT"
    else:
        rating = "NEW"
    return HistoricalContext(
        total_observations=total,
        previous_failures=prev,
        consecutive_failures=prev,
        failure_rate_pct=rate,
        persistence_rating=rating,
    )


def _body_mentions_exception(body: Any) -> bool:
    """Detect server stack-trace markers inside a response body."""
    text = (snippet_body(body) or "").lower()
    return any(marker in text for marker in SERVER_EXCEPTION_MARKERS)


def categorize_root_cause(
    status_code: Optional[int] = None,
    expected_status: Optional[int] = None,
    response_body: Any = None,
    latency_ms: Optional[float] = None,
    max_latency_ms: Optional[float] = None,
    network_error: Optional[str] = None,
    is_negative_test: bool = False,
    schema_errors: Optional[List[str]] = None
) -> RootCauseAssessment:
    """Map raw failure signals onto the standardized root-cause taxonomy."""
    signals: List[str] = []
    schema_errors = schema_errors or []

    # 1. Transport-level failures outrank everything else.
    if network_error:
        err = str(network_error).lower()
        signals.append(f"network_error={network_error}")
        if "timeout" in err or "timedout" in err:
            return RootCauseAssessment(
                category=RootCauseCategory.NETWORK_TIMEOUT,
                title="Request timed out before a response arrived",
                summary=f"The target did not respond within the configured timeout ({network_error}).",
                confidence_pct=95.0,
                remediation_hint=(
                    "Profile the slow path, add indexes or caching, or raise the timeout "
                    "if the work is legitimately long-running."
                ),
                matched_signals=signals,
            )
        return RootCauseAssessment(
            category=RootCauseCategory.NETWORK_CONNECTIVITY,
            title="Target unreachable",
            summary=f"The request never completed: {network_error}.",
            confidence_pct=92.0,
            remediation_hint=(
                "Verify the host resolves, the service is listening, and no firewall or "
                "TLS policy blocks the connection."
            ),
            matched_signals=signals,
        )

    # 2. A 5xx on adversarial input is the platform's signature finding.
    if status_code is not None and 500 <= status_code < 600:
        signals.append(f"status={status_code}")
        if _body_mentions_exception(response_body):
            signals.append("stack_trace_markers")
        if is_negative_test:
            return RootCauseAssessment(
                category=RootCauseCategory.MISSING_INPUT_VALIDATION,
                title="Invalid input crashed the server instead of being rejected",
                summary=(
                    f"An intentionally malformed request produced HTTP {status_code}. "
                    "A well-behaved API rejects bad input with 400 or 422."
                ),
                confidence_pct=96.0,
                remediation_hint=(
                    "Validate the request body against a schema before the handler touches "
                    "it, and return 400/422 on violation."
                ),
                matched_signals=signals,
            )
        return RootCauseAssessment(
            category=RootCauseCategory.SERVER_EXCEPTION,
            title=f"Unhandled server exception (HTTP {status_code})",
            summary=f"The endpoint returned HTTP {status_code}, indicating an unhandled backend error.",
            confidence_pct=90.0,
            remediation_hint=(
                "Inspect server logs for the stack trace and wrap the failing call in "
                "explicit error handling."
            ),
            matched_signals=signals,
        )

    # 3. Authentication / authorization / not-found are distinct, actionable classes.
    if status_code in (401, 407):
        return RootCauseAssessment(
            category=RootCauseCategory.AUTHENTICATION_FAILURE,
            title="Authentication rejected",
            summary=f"The target returned HTTP {status_code}; credentials are missing, expired, or malformed.",
            confidence_pct=93.0,
            remediation_hint="Refresh the token or configure project-level Authorization headers before re-running.",
            matched_signals=[f"status={status_code}"],
        )
    if status_code == 403:
        return RootCauseAssessment(
            category=RootCauseCategory.AUTHORIZATION_FAILURE,
            title="Authorized identity lacks permission",
            summary="The target returned HTTP 403; the caller authenticated but is not permitted this operation.",
            confidence_pct=90.0,
            remediation_hint="Check role or scope assignment for the test identity.",
            matched_signals=["status=403"],
        )
    if status_code == 404 and expected_status not in (404, None):
        return RootCauseAssessment(
            category=RootCauseCategory.RESOURCE_NOT_FOUND,
            title="Target resource does not exist",
            summary="The target returned HTTP 404 where a resource was expected.",
            confidence_pct=85.0,
            remediation_hint="Confirm path parameters resolve to seeded fixtures and that the route is registered.",
            matched_signals=["status=404"],
        )
    if status_code == 429:
        return RootCauseAssessment(
            category=RootCauseCategory.RATE_LIMITED,
            title="Rate limit exceeded",
            summary="The target returned HTTP 429; the suite is issuing requests faster than the API allows.",
            confidence_pct=94.0,
            remediation_hint="Lower run concurrency or add an inter-request delay.",
            matched_signals=["status=429"],
        )

    # 4. Contract violations.
    if schema_errors:
        joined = "; ".join(schema_errors[:3])
        return RootCauseAssessment(
            category=RootCauseCategory.RESPONSE_CONTRACT_MISMATCH,
            title="Response does not match the declared schema",
            summary=f"{len(schema_errors)} schema violation(s): {joined}",
            confidence_pct=95.0,
            remediation_hint=(
                "Align the serializer with the published contract, or update the contract "
                "if the new shape is intentional."
            ),
            matched_signals=[f"schema_errors={len(schema_errors)}"],
        )

    # 5. Latency breach with an otherwise healthy response.
    if max_latency_ms is not None and latency_ms is not None and latency_ms > max_latency_ms:
        over = round(((latency_ms / max_latency_ms) - 1.0) * 100.0, 1) if max_latency_ms else 0.0
        return RootCauseAssessment(
            category=RootCauseCategory.PERFORMANCE_SLA_BREACH,
            title="Response exceeded its latency budget",
            summary=f"Observed {latency_ms:.1f}ms against a {max_latency_ms:.1f}ms budget ({over}% over).",
            confidence_pct=88.0,
            remediation_hint=(
                "Profile the handler; look for N+1 queries, missing indexes, or synchronous "
                "third-party calls."
            ),
            matched_signals=[f"latency={latency_ms}", f"budget={max_latency_ms}"],
        )

    # 6. Plain status mismatch.
    if expected_status is not None and status_code is not None and status_code != expected_status:
        return RootCauseAssessment(
            category=RootCauseCategory.STATUS_CODE_MISMATCH,
            title=f"Expected HTTP {expected_status}, received {status_code}",
            summary=f"The endpoint returned HTTP {status_code} where the test expected {expected_status}.",
            confidence_pct=80.0,
            remediation_hint="Confirm whether the endpoint contract changed or the test expectation is stale.",
            matched_signals=[f"status={status_code}", f"expected={expected_status}"],
        )

    if _body_mentions_exception(response_body):
        return RootCauseAssessment(
            category=RootCauseCategory.MALFORMED_PAYLOAD,
            title="Response body contains error markers",
            summary="The payload contains exception text despite a non-error status code.",
            confidence_pct=60.0,
            remediation_hint=(
                "Ensure failures propagate as proper status codes rather than 200 responses "
                "carrying error text."
            ),
            matched_signals=["stack_trace_markers"],
        )

    return RootCauseAssessment(
        category=RootCauseCategory.UNKNOWN,
        title="Unclassified failure",
        summary="No deterministic rule matched the observed signals.",
        confidence_pct=25.0,
        remediation_hint="Inspect the raw evidence bundle manually.",
        matched_signals=signals,
    )


def derive_severity(
    assessment: RootCauseAssessment,
    history: Optional[HistoricalContext] = None
) -> EvidenceSeverity:
    """Translate a root-cause category (and its recurrence) into a triage severity."""
    critical = {
        RootCauseCategory.MISSING_INPUT_VALIDATION,
        RootCauseCategory.SERVER_EXCEPTION,
    }
    high = {
        RootCauseCategory.AUTHENTICATION_FAILURE,
        RootCauseCategory.AUTHORIZATION_FAILURE,
        RootCauseCategory.STATUS_CODE_MISMATCH,
        RootCauseCategory.NETWORK_CONNECTIVITY,
        RootCauseCategory.NETWORK_TIMEOUT,
    }
    medium = {
        RootCauseCategory.RESPONSE_CONTRACT_MISMATCH,
        RootCauseCategory.RESOURCE_NOT_FOUND,
        RootCauseCategory.MALFORMED_PAYLOAD,
        RootCauseCategory.RATE_LIMITED,
    }

    if assessment.category in critical:
        return EvidenceSeverity.CRITICAL
    if assessment.category in high:
        return EvidenceSeverity.HIGH
    if assessment.category in medium:
        # A chronic contract break deserves escalation.
        if history and history.persistence_rating == "CHRONIC":
            return EvidenceSeverity.HIGH
        return EvidenceSeverity.MEDIUM
    if assessment.category == RootCauseCategory.PERFORMANCE_SLA_BREACH:
        return EvidenceSeverity.MEDIUM
    return EvidenceSeverity.LOW
