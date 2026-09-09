"""Pydantic Schemas and DTOs for API Execution Engine."""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator
import http

from app.models.schemas.endpoint import HTTPMethod
from app.models.schemas.request_config import BodyType


class ExecutionOptions(BaseModel):
    """Configuration options controlling HTTP execution behavior."""
    timeout_seconds: float = Field(
        default=10.0,
        gt=0.0,
        le=300.0,
        description="Per-request execution timeout in seconds"
    )
    follow_redirects: bool = Field(
        default=True,
        description="Whether to automatically follow HTTP 3xx redirects"
    )
    max_redirects: int = Field(
        default=20,
        ge=0,
        le=50,
        description="Maximum number of redirects to follow before raising an error"
    )
    verify_ssl: bool = Field(
        default=True,
        description="Whether to enforce SSL/TLS certificate verification"
    )


class DirectExecutionRequest(BaseModel):
    """Payload for executing an ad-hoc HTTP request on the fly."""
    base_url: str = Field(..., description="Target server base URL", examples=["https://httpbin.org"])
    method: HTTPMethod = Field(default=HTTPMethod.GET, description="HTTP verb")
    path: str = Field(default="", description="Path template or concrete path", examples=["/get"])
    path_params: Dict[str, Any] = Field(default_factory=dict, description="Values for {param} tokens in path")
    query_params: Dict[str, Any] = Field(default_factory=dict, description="URL query parameters")
    headers: Dict[str, str] = Field(default_factory=dict, description="Custom HTTP headers")
    body_type: BodyType = Field(default=BodyType.EMPTY, description="Payload serialization format")
    body: Optional[Any] = Field(default=None, description="Request body payload")
    options: ExecutionOptions = Field(default_factory=ExecutionOptions, description="Execution options")


class EndpointExecutionRequest(BaseModel):
    """Payload for executing a stored project endpoint with optional runtime overrides."""
    path_params: Optional[Dict[str, Any]] = Field(default=None, description="Override path parameters")
    query_params: Optional[Dict[str, Any]] = Field(default=None, description="Override query parameters")
    headers: Optional[Dict[str, str]] = Field(default=None, description="Override or additional headers")
    body_type: Optional[BodyType] = Field(default=None, description="Override body format type")
    body: Optional[Any] = Field(default=None, description="Override request body payload")
    options: ExecutionOptions = Field(default_factory=ExecutionOptions, description="Execution options")


class ExecutionResultResponse(BaseModel):
    """Complete execution result and network telemetry response."""
    url: str = Field(..., description="Final URL requested")
    method: str = Field(..., description="HTTP Method used")
    status_code: Optional[int] = Field(default=None, description="HTTP status code (null if connection failed)")
    status_text: Optional[str] = Field(default=None, description="HTTP status reason phrase")
    headers: Dict[str, str] = Field(default_factory=dict, description="Response headers received")
    body: Optional[Any] = Field(default=None, description="Decoded response body (parsed JSON or text string)")
    is_success: bool = Field(default=False, description="True if status_code is 2xx")
    is_redirect: bool = Field(default=False, description="True if status_code is 3xx")
    is_client_error: bool = Field(default=False, description="True if status_code is 4xx")
    is_server_error: bool = Field(default=False, description="True if status_code is 5xx")
    http_version: str = Field(default="HTTP/1.1", description="HTTP protocol version")
    elapsed_ms: float = Field(default=0.0, description="Total request execution latency in milliseconds")
    redirect_count: int = Field(default=0, description="Number of HTTP redirects followed")
    content_length: int = Field(default=0, description="Response body size in bytes")
    content_type: Optional[str] = Field(default=None, description="MIME content-type of response")
    error: Optional[str] = Field(default=None, description="Error message if execution failed before response")
    error_type: Optional[str] = Field(default=None, description="Error class name if execution failed")

    @classmethod
    def from_httpx_response(
        cls,
        response: Any,
        elapsed_ms: float,
        redirect_count: int = 0
    ) -> "ExecutionResultResponse":
        """Factory constructor converting httpx.Response into ExecutionResultResponse."""
        status_code = response.status_code
        status_text = ""
        try:
            status_text = http.HTTPStatus(status_code).phrase
        except ValueError:
            status_text = response.reason_phrase or "Unknown"

        # Try parsing JSON if content-type is json
        body_content: Any = None
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type or "+json" in content_type:
            try:
                body_content = response.json()
            except Exception:
                body_content = response.text
        else:
            body_content = response.text

        headers_dict = dict(response.headers)

        return cls(
            url=str(response.url),
            method=response.request.method if response.request else "GET",
            status_code=status_code,
            status_text=status_text,
            headers=headers_dict,
            body=body_content,
            is_success=(200 <= status_code < 300),
            is_redirect=(300 <= status_code < 400),
            is_client_error=(400 <= status_code < 500),
            is_server_error=(status_code >= 500),
            http_version=response.http_version or "HTTP/1.1",
            elapsed_ms=round(elapsed_ms, 2),
            redirect_count=redirect_count,
            content_length=len(response.content),
            content_type=content_type or None,
            error=None,
            error_type=None
        )


class ClientInfoResponse(BaseModel):
    """Current connection pool and HTTP client configuration metadata."""
    is_active: bool
    default_timeout: float
    max_concurrency: int
    max_keepalive: int
    environment: str
