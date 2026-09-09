"""Deterministic rule-based fallback recommendation engine (Sub-Stage 19.02).

Guarantees high-quality, actionable remediation advice and code snippets even when running
completely offline or without a configured Gemini API key.
"""
from typing import List
from app.models.schemas.ai_recommendation import (
    FixRecommendation,
    RecommendationSeverity,
    RecommendationSource,
)
from app.models.schemas.failure_analysis import FailureEvidence, RootCauseCategory


def recommend_from_evidence(evidence: FailureEvidence) -> FixRecommendation:
    """Generate deterministic, expert-crafted remediation advice based on failure taxonomy."""
    cat = evidence.root_cause.category
    sev = RecommendationSeverity(evidence.severity.value)

    if cat == RootCauseCategory.MISSING_INPUT_VALIDATION:
        likely_cause = (
            f"Endpoint [{evidence.request.http_method}] {evidence.request.url} crashed with an unhandled "
            f"500 Internal Server Error when sent malformed/adversarial input. The server failed to validate "
            f"the payload before processing, exposing an unhandled exception."
        )
        suggested_fix = (
            "1. Define a strict Pydantic/DTO schema for all incoming request payloads.\n"
            "2. Ensure FastAPI/framework validation intercepts missing fields, nulls, and type inversions.\n"
            "3. Reject malformed payloads with HTTP 400 Bad Request or HTTP 422 Unprocessable Entity."
        )
        code_snippet = (
            "from pydantic import BaseModel, Field\n"
            "from fastapi import FastAPI, HTTPException, status\n\n"
            "class ItemRequest(BaseModel):\n"
            "    name: str = Field(..., min_length=1, max_length=100)\n"
            "    price: float = Field(..., gt=0.0)\n"
            "    quantity: int = Field(default=1, ge=1)\n\n"
            "@app.post('/items', status_code=status.HTTP_201_CREATED)\n"
            "async def create_item(payload: ItemRequest):\n"
            "    # Payload is guaranteed valid; will never crash with KeyError/TypeError\n"
            "    return {'status': 'created', 'data': payload.model_dump()}"
        )
        refs = ["https://docs.pydantic.dev/latest/concepts/models/", "https://fastapi.tiangolo.com/tutorial/body/"]

    elif cat == RootCauseCategory.SERVER_EXCEPTION:
        likely_cause = (
            f"The server encountered an unhandled exception (HTTP {evidence.response.status_code}) "
            f"during execution. Possible root causes include unhandled null pointers, database disconnects, or unhandled runtime exceptions."
        )
        suggested_fix = (
            "1. Wrap the endpoint controller in defensive try/except blocks.\n"
            "2. Attach a global exception filter to catch unexpected runtime errors and log structured traces.\n"
            "3. Ensure database connections and external client calls use resilient session pools."
        )
        code_snippet = (
            "from fastapi import Request, status\n"
            "from fastapi.responses import JSONResponse\n\n"
            "@app.exception_handler(Exception)\n"
            "async def global_exception_handler(request: Request, exc: Exception):\n"
            "    logger.error(f'Unhandled error on {request.url}: {exc}', exc_info=True)\n"
            "    return JSONResponse(\n"
            "        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,\n"
            "        content={'error': 'INTERNAL_ERROR', 'message': 'An unexpected error occurred. Please contact support.'}\n"
            "    )"
        )
        refs = ["https://fastapi.tiangolo.com/tutorial/handling-errors/"]

    elif cat == RootCauseCategory.RESPONSE_CONTRACT_MISMATCH:
        likely_cause = (
            "The response body returned by the API did not match its registered JSON Schema or OpenAPI contract. "
            "Required fields were missing or types differed from the contract specification."
        )
        suggested_fix = (
            "1. Review the endpoint response model to ensure all required fields are populated.\n"
            "2. Explicitly bind `response_model` in the route definition.\n"
            "3. Ensure nullability is explicitly declared (`Optional[T] = None`) for nullable fields."
        )
        code_snippet = (
            "from typing import Optional\n"
            "from pydantic import BaseModel\n\n"
            "class UserResponse(BaseModel):\n"
            "    id: int\n"
            "    username: str\n"
            "    email: str\n"
            "    bio: Optional[str] = None  # Declare optional if field can be null\n\n"
            "@app.get('/users/{id}', response_model=UserResponse)\n"
            "async def get_user(id: int):\n"
            "    user = await get_user_by_id(id)\n"
            "    return user"
        )
        refs = ["https://fastapi.tiangolo.com/tutorial/response-model/"]

    elif cat == RootCauseCategory.PERFORMANCE_SLA_BREACH:
        latency = evidence.response.latency_ms or 0.0
        max_lat = evidence.max_latency_ms or 500.0
        likely_cause = (
            f"Endpoint latency ({latency:.1f}ms) breached the configured SLA threshold ({max_lat:.1f}ms). "
            f"Likely caused by unindexed database queries, N+1 query patterns, or un-cached downstream calls."
        )
        suggested_fix = (
            "1. Add database indexes on frequently queried columns in `WHERE` and `JOIN` clauses.\n"
            "2. Use eager loading (`joinedload` / `selectinload`) to eliminate N+1 queries.\n"
            "3. Implement in-memory (Redis/cachetools) caching for read-heavy endpoints."
        )
        code_snippet = (
            "# SQLAlchemy Eager Loading to eliminate N+1 latency:\n"
            "from sqlalchemy.orm import selectinload\n\n"
            "async def get_orders_optimized(db: AsyncSession, user_id: int):\n"
            "    stmt = (\n"
            "        select(Order)\n"
            "        .where(Order.user_id == user_id)\n"
            "        .options(selectinload(Order.items))  # Eager load items in a single query\n"
            "    )\n"
            "    result = await db.execute(stmt)\n"
            "    return result.scalars().all()"
        )
        refs = ["https://docs.sqlalchemy.org/en/20/orm/queryguide/relationships.html#selectin-eager-loading"]

    elif cat == RootCauseCategory.NETWORK_TIMEOUT:
        likely_cause = (
            f"Request timed out or failed to connect to the target service ({evidence.response.network_error or 'Timeout'}). "
            f"Remote server may be unresponsive or network routing is blocked."
        )
        suggested_fix = (
            "1. Verify the remote service is healthy and reachable from the host.\n"
            "2. Configure proper connection pool timeout limits and retries with exponential backoff.\n"
            "3. Use a circuit breaker pattern to prevent cascading timeouts."
        )
        code_snippet = (
            "import httpx\n\n"
            "timeout_config = httpx.Timeout(10.0, connect=5.0, read=10.0)\n"
            "limits = httpx.Limits(max_keepalive_connections=20, max_connections=50)\n\n"
            "async with httpx.AsyncClient(timeout=timeout_config, limits=limits) as client:\n"
            "    response = await client.get('https://remote.service.com/api')"
        )
        refs = ["https://www.python-httpx.org/advanced/#timeout-configuration"]

    elif cat in {RootCauseCategory.AUTHENTICATION_FAILURE, RootCauseCategory.AUTHORIZATION_FAILURE}:
        likely_cause = (
            f"Request failed security validation (HTTP {evidence.response.status_code}). "
            f"The credentials supplied were either missing, expired, or lacked the required permission scope."
        )
        suggested_fix = (
            "1. Verify authentication headers (`Authorization: Bearer <token>`).\n"
            "2. Ensure token expiration is handled gracefully with auto-refresh.\n"
            "3. Verify RBAC permissions and user role assignments."
        )
        code_snippet = (
            "from fastapi import Depends, HTTPException, status\n"
            "from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials\n\n"
            "security = HTTPBearer()\n\n"
            "async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):\n"
            "    token = credentials.credentials\n"
            "    if not is_valid_jwt(token):\n"
            "        raise HTTPException(\n"
            "            status_code=status.HTTP_401_UNAUTHORIZED,\n"
            "            detail='Invalid or expired authentication token'\n"
            "        )\n"
            "    return get_current_user(token)"
        )
        refs = ["https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/"]

    else:
        likely_cause = (
            f"Test scenario '{evidence.test_name}' failed expectation. "
            f"Expected status: {evidence.expected_status or '200'}, Actual: {evidence.response.status_code}."
        )
        suggested_fix = (
            "1. Review the endpoint logic and verify if the behavioral change is intentional.\n"
            "2. Update the test case assertions if the new behavior represents a valid specification update."
        )
        code_snippet = (
            "# Ensure route returns correct HTTP status code:\n"
            "@app.get('/endpoint', status_code=200)\n"
            "async def endpoint():\n"
            "    return {'status': 'ok'}"
        )
        refs = ["https://fastapi.tiangolo.com/tutorial/"]

    return FixRecommendation(
        evidence_id=evidence.evidence_id,
        root_cause_category=cat.value,
        likely_cause=likely_cause,
        severity=sev,
        suggested_fix=suggested_fix,
        code_snippet=code_snippet,
        confidence_pct=90.0,
        source=RecommendationSource.RULE_BASED_HEURISTIC,
        model_name="HeuristicEngine-v1.0",
        references=refs,
    )
