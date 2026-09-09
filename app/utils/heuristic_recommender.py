"""Offline rule-based remediation engine (Stage 19, sub-stage 02 fallback).

This engine is why API Sentinel stays fully functional with no LLM API key: every
root-cause category maps to a deterministic, human-reviewed remediation card.
"""
from typing import Dict

from app.models.schemas.ai_recommendation import (
    FixRecommendation,
    RecommendationSeverity,
    RecommendationSource,
)
from app.models.schemas.failure_analysis import FailureEvidence, RootCauseCategory

_VALIDATION_SNIPPET = (
    "from fastapi import HTTPException, status\n"
    "from pydantic import BaseModel, EmailStr, Field\n\n\n"
    "class LoginRequest(BaseModel):\n"
    '    """Reject malformed input before it reaches business logic."""\n'
    "    email: EmailStr\n"
    "    password: str = Field(..., min_length=8)\n\n\n"
    '@app.post("/api/auth/login")\n'
    "async def login(payload: LoginRequest):\n"
    "    # FastAPI now returns 422 automatically instead of raising KeyError -> 500.\n"
    "    user = await authenticate(payload.email, payload.password)\n"
    "    if not user:\n"
    '        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")\n'
    '    return {"token": issue_token(user)}'
)

_EXCEPTION_SNIPPET = (
    "@app.exception_handler(Exception)\n"
    "async def unhandled_exception_handler(request: Request, exc: Exception):\n"
    '    """Convert any unhandled error into a structured 500 without leaking a trace."""\n'
    '    logger.exception("Unhandled error on %s %s", request.method, request.url.path)\n'
    "    return JSONResponse(\n"
    "        status_code=500,\n"
    '        content={"error": {"code": "INTERNAL_ERROR", "message": "Unexpected server error"}},\n'
    "    )"
)

_CONTRACT_SNIPPET = (
    "class ProductResponse(BaseModel):\n"
    '    """Declare the response contract so serialization drift fails fast in CI."""\n'
    "    id: int\n"
    "    name: str\n"
    '    price: float          # not "29.99 USD" - keep the type numeric\n'
    "    stock: int            # required field must always be emitted\n\n\n"
    '@app.get("/api/products/{product_id}", response_model=ProductResponse)\n'
    "async def get_product(product_id: int):\n"
    "    return await repository.fetch(product_id)"
)

_LATENCY_SNIPPET = (
    "# Replace the N+1 query pattern with a single joined fetch.\n"
    "stmt = (\n"
    "    select(Order)\n"
    "    .options(selectinload(Order.items))     # one round trip, not one per row\n"
    "    .where(Order.user_id == user_id)\n"
    ")\n"
    "orders = (await session.execute(stmt)).scalars().all()"
)

_AUTH_SNIPPET = (
    "# Attach credentials at the project level so every test inherits them.\n"
    "PUT /api/v1/projects/{project_id}\n"
    "{\n"
    '  "global_headers": {"Authorization": "Bearer <token>"}\n'
    "}"
)

_TIMEOUT_SNIPPET = (
    "# Bound slow dependencies so one hung call cannot exhaust the pool.\n"
    "async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=2.0)) as client:\n"
    "    response = await client.get(upstream_url)"
)

_RATE_LIMIT_SNIPPET = (
    "POST /api/v1/projects/{project_id}/runs\n"
    "{\n"
    '  "name": "Nightly Suite",\n'
    '  "concurrency": 2          # stay inside the upstream rate limit\n'
    "}"
)

# category -> (likely_cause, severity, suggested_fix, code_snippet, confidence, references)
_PLAYBOOK: Dict[RootCauseCategory, tuple] = {
    RootCauseCategory.MISSING_INPUT_VALIDATION: (
        "The handler reads request fields directly without validating them, so malformed "
        "input raises an unhandled exception instead of being rejected.",
        RecommendationSeverity.CRITICAL,
        "Bind the request body to a Pydantic model so invalid payloads are rejected with "
        "HTTP 422 before any business logic executes. Never index into the raw payload.",
        _VALIDATION_SNIPPET,
        92.0,
        [
            "https://docs.pydantic.dev/latest/concepts/models/",
            "https://fastapi.tiangolo.com/tutorial/body/",
        ],
    ),
    RootCauseCategory.SERVER_EXCEPTION: (
        "An unhandled exception escaped the request handler and surfaced as HTTP 5xx.",
        RecommendationSeverity.CRITICAL,
        "Locate the stack trace in the server logs, add explicit error handling around the "
        "failing operation, and register a global exception handler so raw traces never "
        "reach clients.",
        _EXCEPTION_SNIPPET,
        85.0,
        ["https://fastapi.tiangolo.com/tutorial/handling-errors/"],
    ),
    RootCauseCategory.RESPONSE_CONTRACT_MISMATCH: (
        "The response payload no longer matches the declared schema - a field is missing, "
        "renamed, or emitted with the wrong type.",
        RecommendationSeverity.HIGH,
        "Declare a response_model on the route so serialization drift is caught at the "
        "boundary, then either fix the serializer or update the published contract.",
        _CONTRACT_SNIPPET,
        90.0,
        ["https://fastapi.tiangolo.com/tutorial/response-model/"],
    ),
    RootCauseCategory.STATUS_CODE_MISMATCH: (
        "The endpoint returned a different status code than the contract promises.",
        RecommendationSeverity.HIGH,
        "Confirm whether the endpoint intentionally changed. If so, update the test "
        "expectation; if not, restore the documented status code.",
        None,
        75.0,
        ["https://developer.mozilla.org/en-US/docs/Web/HTTP/Status"],
    ),
    RootCauseCategory.PERFORMANCE_SLA_BREACH: (
        "The endpoint responded correctly but exceeded its latency budget, typically due to "
        "unindexed queries, N+1 access patterns, or synchronous third-party calls.",
        RecommendationSeverity.MEDIUM,
        "Profile the handler, eager-load related rows in a single query, add indexes on the "
        "filtered columns, and move non-essential work to a background task.",
        _LATENCY_SNIPPET,
        80.0,
        ["https://docs.sqlalchemy.org/en/20/orm/queryguide/relationships.html"],
    ),
    RootCauseCategory.NETWORK_TIMEOUT: (
        "The target did not respond within the configured timeout window.",
        RecommendationSeverity.HIGH,
        "Verify the service is healthy and not blocked on a dependency, then set explicit "
        "connect and read timeouts so a hung upstream cannot stall the suite.",
        _TIMEOUT_SNIPPET,
        82.0,
        ["https://www.python-httpx.org/advanced/timeouts/"],
    ),
    RootCauseCategory.NETWORK_CONNECTIVITY: (
        "The request never reached the target: DNS resolution, TLS negotiation, or the TCP "
        "connection itself failed.",
        RecommendationSeverity.HIGH,
        "Confirm the hostname resolves, the port is listening, and the certificate chain is "
        "valid. Check that the base URL in the project workspace is current.",
        None,
        84.0,
        [],
    ),
    RootCauseCategory.AUTHENTICATION_FAILURE: (
        "The request was rejected because credentials were missing, expired, or malformed.",
        RecommendationSeverity.HIGH,
        "Refresh the access token and store it as a project-level global header so every "
        "test in the workspace inherits valid credentials.",
        _AUTH_SNIPPET,
        88.0,
        [],
    ),
    RootCauseCategory.AUTHORIZATION_FAILURE: (
        "The caller authenticated successfully but lacks permission for this operation.",
        RecommendationSeverity.HIGH,
        "Grant the test identity the required role or scope, or point the test at a "
        "resource the identity legitimately owns.",
        None,
        86.0,
        [],
    ),
    RootCauseCategory.RESOURCE_NOT_FOUND: (
        "The path resolved to a resource that does not exist, usually a stale fixture id "
        "or an unregistered route.",
        RecommendationSeverity.MEDIUM,
        "Seed the fixture the test depends on, or interpolate a path parameter captured "
        "earlier in the suite instead of hard-coding an id.",
        None,
        78.0,
        [],
    ),
    RootCauseCategory.RATE_LIMITED: (
        "The suite issued requests faster than the target permits and was throttled.",
        RecommendationSeverity.MEDIUM,
        "Reduce run concurrency or introduce an inter-request delay so the suite stays "
        "within the published rate limit.",
        _RATE_LIMIT_SNIPPET,
        90.0,
        [],
    ),
    RootCauseCategory.MALFORMED_PAYLOAD: (
        "The response body could not be parsed as the declared format, or carries error "
        "text under a success status code.",
        RecommendationSeverity.MEDIUM,
        "Ensure the handler serializes through the framework rather than emitting hand-built "
        "strings, and surface failures as proper status codes.",
        None,
        76.0,
        [],
    ),
}

_UNKNOWN = (
    "No deterministic rule matched the observed signals, so the underlying cause could not "
    "be narrowed automatically.",
    RecommendationSeverity.LOW,
    "Review the packaged evidence bundle - request payload, response body, and timing - and "
    "reproduce the call with the generated cURL command.",
    None,
    30.0,
    [],
)


def recommend_from_evidence(evidence: FailureEvidence) -> FixRecommendation:
    """Produce a deterministic remediation card for a packaged failure."""
    cause, severity, fix, snippet, confidence, refs = _PLAYBOOK.get(
        evidence.root_cause.category, _UNKNOWN
    )

    # A chronic failure is more urgent than a first sighting of the same class.
    if evidence.history.persistence_rating == "CHRONIC" and severity == RecommendationSeverity.MEDIUM:
        severity = RecommendationSeverity.HIGH

    detail = evidence.root_cause.summary
    likely_cause = f"{cause} {detail}".strip() if detail else cause

    return FixRecommendation(
        evidence_id=evidence.evidence_id,
        root_cause_category=evidence.root_cause.category.value,
        likely_cause=likely_cause,
        severity=severity,
        suggested_fix=fix,
        code_snippet=snippet,
        confidence_pct=confidence,
        source=RecommendationSource.RULE_BASED_HEURISTIC,
        model_name=None,
        references=list(refs),
    )
