"""Utility primitives for evidence packaging, credential redaction, and root-cause categorization."""
import hashlib
import json
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

from app.models.schemas.failure_analysis import (
    FailureSeverity,
    HistoricalRecurrenceContext,
    RequestEvidence,
    ResponseEvidence,
    RootCauseAssessment,
    RootCauseCategory,
)

SENSITIVE_HEADER_KEYS = {
    "authorization",
    "proxy-authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "apikey",
    "api-key",
    "token",
    "secret",
    "password",
    "x-auth-token",
}


def mask_sensitive_headers(headers: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """Return a copy of headers with sensitive keys replaced with redaction placeholder."""
    if not headers:
        return {}
    sanitized: Dict[str, str] = {}
    for key, value in headers.items():
        if key.lower() in SENSITIVE_HEADER_KEYS:
            sanitized[key] = "***REDACTED***"
        else:
            sanitized[key] = str(value)
    return sanitized


def snippet_body(body: Any, max_len: int = 4096) -> str:
    """Format and bound body payload to prevent memory exhaustion and large log blobs."""
    if body is None:
        return ""
    if isinstance(body, (dict, list)):
        try:
            text = json.dumps(body)
        except (TypeError, ValueError):
            text = str(body)
    else:
        text = str(body)

    if len(text) > max_len:
        return text[:max_len] + f"... [truncated {len(text) - max_len} bytes]"
    return text


def build_curl_command(
    http_method: str,
    url: str,
    headers: Optional[Dict[str, Any]] = None,
    body: Optional[Any] = None,
    query_params: Optional[Dict[str, Any]] = None,
) -> str:
    """Generate a reproducible cURL command with masked secrets and properly encoded parameters."""
    method = (http_method or "GET").upper()
    target_url = url
    if query_params:
        qs = urlencode(query_params, doseq=True)
        delimiter = "&" if "?" in target_url else "?"
        target_url = f"{target_url}{delimiter}{qs}"

    parts = [f"curl -X {method} \"{target_url}\""]
    masked = mask_sensitive_headers(headers)
    for k, v in masked.items():
        parts.append(f"-H \"{k}: {v}\"")

    if body is not None and method in {"POST", "PUT", "PATCH", "DELETE"}:
        if isinstance(body, (dict, list)):
            body_str = json.dumps(body)
        else:
            body_str = str(body)
        # Escape quotes for shell safety
        safe_body = body_str.replace('"', '\\"')
        parts.append(f'-d "{safe_body}"')

    return " ".join(parts)


def build_historical_context(
    previous_failures: int = 0,
    total_observations: int = 1,
    consecutive_streak: int = 0,
) -> HistoricalRecurrenceContext:
    """Compute recurrence context and persistence rating from historical observations."""
    total = max(1, total_observations)
    failures = max(0, min(total, previous_failures))
    rate = round((failures / total) * 100.0, 1)

    if failures == 0:
        persistence = "NEW" if total <= 1 else "HEALTHY"
    elif rate >= 80.0:
        persistence = "CHRONIC"
    elif rate >= 20.0:
        persistence = "INTERMITTENT"
    else:
        persistence = "RESOLVED" if consecutive_streak == 0 else "NEW"

    return HistoricalRecurrenceContext(
        persistence_rating=persistence,
        failure_rate_pct=rate,
        consecutive_failure_streak=consecutive_streak,
        total_observations=total,
    )


def build_evidence_id(
    test_name: str, url: str, status_code: Optional[int], category: str
) -> str:
    """Generate a deterministic evidence ID."""
    token = f"{test_name}|{url}|{status_code or 'none'}|{category}"
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]
    return f"EV-{digest.upper()}"


def build_request_evidence(
    http_method: str,
    url: str,
    headers: Optional[Dict[str, Any]] = None,
    query_params: Optional[Dict[str, Any]] = None,
    path_params: Optional[Dict[str, Any]] = None,
    body: Optional[Any] = None,
) -> RequestEvidence:
    """Construct sanitized RequestEvidence DTO."""
    return RequestEvidence(
        http_method=(http_method or "GET").upper(),
        url=url,
        headers=mask_sensitive_headers(headers),
        query_params=query_params or {},
        path_params=path_params or {},
        body_snippet=snippet_body(body) if body is not None else None,
        curl_command=build_curl_command(
            http_method=http_method,
            url=url,
            headers=headers,
            body=body,
            query_params=query_params,
        ),
    )


def build_response_evidence(
    status_code: Optional[int],
    headers: Optional[Dict[str, Any]] = None,
    body: Optional[Any] = None,
    latency_ms: Optional[float] = None,
    network_error: Optional[str] = None,
) -> ResponseEvidence:
    """Construct ResponseEvidence DTO."""
    return ResponseEvidence(
        status_code=status_code,
        headers=mask_sensitive_headers(headers),
        body_snippet=snippet_body(body) if body is not None else None,
        latency_ms=latency_ms,
        network_error=network_error,
    )


def categorize_root_cause(
    status_code: Optional[int] = None,
    expected_status: Optional[int] = None,
    response_body: Optional[str] = None,
    latency_ms: Optional[float] = None,
    max_latency_ms: Optional[float] = None,
    network_error: Optional[str] = None,
    is_negative_test: bool = False,
    schema_errors: Optional[List[str]] = None,
    assertion_failures: Optional[List[Any]] = None,
) -> RootCauseAssessment:
    """Classify execution failure signals into the 13-category root-cause taxonomy."""
    # 1. Network / Socket level errors
    if network_error:
        err_lower = network_error.lower()
        if "timeout" in err_lower:
            return RootCauseAssessment(
                category=RootCauseCategory.NETWORK_TIMEOUT,
                confidence_pct=95.0,
                description=f"Request timed out: {network_error}",
                troubleshooting_hint="Verify remote service availability, latency, or increase the execution timeout ceiling.",
            )
        return RootCauseAssessment(
            category=RootCauseCategory.NETWORK_TIMEOUT,
            confidence_pct=90.0,
            description=f"Network transport error: {network_error}",
            troubleshooting_hint="Check DNS resolution, host connectivity, routing, and firewall rules.",
        )

    # 2. Adversarial / Negative test unhandled 500 crash
    if is_negative_test and status_code is not None and status_code >= 500:
        return RootCauseAssessment(
            category=RootCauseCategory.MISSING_INPUT_VALIDATION,
            confidence_pct=95.0,
            description=f"Server crashed with HTTP {status_code} on malformed adversarial input instead of rejecting with 4xx.",
            troubleshooting_hint="Add explicit request payload validation (e.g. Pydantic schema / DTO checks) before processing fields.",
        )

    # 3. General Server 5xx crash
    if status_code is not None and status_code >= 500:
        return RootCauseAssessment(
            category=RootCauseCategory.SERVER_EXCEPTION,
            confidence_pct=90.0,
            description=f"Server encountered an unhandled internal exception (HTTP {status_code}).",
            troubleshooting_hint="Inspect server application logs and exception stack traces around the request timestamp.",
        )

    # 4. JSON Schema / Contract violations
    if schema_errors and len(schema_errors) > 0:
        return RootCauseAssessment(
            category=RootCauseCategory.RESPONSE_CONTRACT_MISMATCH,
            confidence_pct=95.0,
            description=f"Response payload failed schema contract validation ({len(schema_errors)} errors).",
            troubleshooting_hint=f"Align endpoint response serializer with OpenAPI/Draft-7 contract: {schema_errors[0]}",
        )

    # 5. Performance SLA breach
    if max_latency_ms is not None and latency_ms is not None and latency_ms > max_latency_ms:
        return RootCauseAssessment(
            category=RootCauseCategory.PERFORMANCE_SLA_BREACH,
            confidence_pct=90.0,
            description=f"Execution latency ({latency_ms:.1f}ms) breached the SLA ceiling ({max_latency_ms:.1f}ms).",
            troubleshooting_hint="Profile endpoint database queries, downstream microservice calls, and consider caching.",
        )

    # 6. HTTP 401 Unauthorized
    if status_code == 401:
        return RootCauseAssessment(
            category=RootCauseCategory.AUTHENTICATION_FAILURE,
            confidence_pct=95.0,
            description="Request rejected due to missing or invalid authentication credentials.",
            troubleshooting_hint="Verify API keys, Bearer tokens, or OAuth session expiration.",
        )

    # 7. HTTP 403 Forbidden
    if status_code == 403:
        return RootCauseAssessment(
            category=RootCauseCategory.AUTHORIZATION_FAILURE,
            confidence_pct=95.0,
            description="Client lacks required permissions or scopes to access this resource.",
            troubleshooting_hint="Check role-based access control (RBAC) policies and user scope assignments.",
        )

    # 8. HTTP 429 Too Many Requests
    if status_code == 429:
        return RootCauseAssessment(
            category=RootCauseCategory.RATE_LIMITED,
            confidence_pct=95.0,
            description="Request throttled by rate limiter.",
            troubleshooting_hint="Implement exponential backoff or request higher quota tier.",
        )

    # 9. HTTP 404 Not Found
    if status_code == 404:
        return RootCauseAssessment(
            category=RootCauseCategory.ENDPOINT_NOT_FOUND,
            confidence_pct=90.0,
            description="Target URL path or resource identifier not found.",
            troubleshooting_hint="Verify endpoint route registration, base URL, and path parameter values.",
        )

    # 10. HTTP 405 Method Not Allowed
    if status_code == 405:
        return RootCauseAssessment(
            category=RootCauseCategory.METHOD_NOT_ALLOWED,
            confidence_pct=95.0,
            description="HTTP method is not supported by this endpoint.",
            troubleshooting_hint="Verify allowed methods (GET, POST, PUT, DELETE) in endpoint route definition.",
        )

    # 11. Status code mismatch
    if expected_status is not None and status_code is not None and status_code != expected_status:
        return RootCauseAssessment(
            category=RootCauseCategory.STATUS_CODE_MISMATCH,
            confidence_pct=85.0,
            description=f"Received HTTP {status_code}, expected HTTP {expected_status}.",
            troubleshooting_hint="Verify endpoint logic or update test expectation if the API behavior intentionally changed.",
        )

    # 12. Body / field assertion failure
    if assertion_failures and len(assertion_failures) > 0:
        return RootCauseAssessment(
            category=RootCauseCategory.BODY_ASSERTION_FAILURE,
            confidence_pct=85.0,
            description=f"Response assertion rules failed ({len(assertion_failures)} failure(s)).",
            troubleshooting_hint="Review specific field assertion expectations against actual response values.",
        )

    # 13. Unknown fallback
    return RootCauseAssessment(
        category=RootCauseCategory.UNKNOWN_FAILURE,
        confidence_pct=50.0,
        description="Unclassified test execution anomaly.",
        troubleshooting_hint="Inspect raw response body snippet and headers for context.",
    )


def derive_severity(
    assessment: RootCauseAssessment,
    history: Optional[HistoricalRecurrenceContext] = None,
) -> FailureSeverity:
    """Derive impact severity based on root-cause category and persistence history."""
    cat = assessment.category
    if cat in {RootCauseCategory.MISSING_INPUT_VALIDATION, RootCauseCategory.SERVER_EXCEPTION}:
        return FailureSeverity.CRITICAL
    if cat in {
        RootCauseCategory.AUTHENTICATION_FAILURE,
        RootCauseCategory.AUTHORIZATION_FAILURE,
        RootCauseCategory.RESPONSE_CONTRACT_MISMATCH,
    }:
        return FailureSeverity.HIGH
    if cat in {
        RootCauseCategory.NETWORK_TIMEOUT,
        RootCauseCategory.PERFORMANCE_SLA_BREACH,
        RootCauseCategory.RATE_LIMITED,
        RootCauseCategory.STATUS_CODE_MISMATCH,
    }:
        if history and history.persistence_rating == "CHRONIC":
            return FailureSeverity.HIGH
        return FailureSeverity.MEDIUM
    if cat in {RootCauseCategory.ENDPOINT_NOT_FOUND, RootCauseCategory.METHOD_NOT_ALLOWED}:
        return FailureSeverity.MEDIUM
    return FailureSeverity.LOW
