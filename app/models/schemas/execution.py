"""Pydantic Schemas and DTOs for API Execution Engine and Telemetry."""
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field
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


class RedirectStep(BaseModel):
    """A single step in a multi-hop HTTP redirect chain."""
    url: str = Field(..., description="Intermediate URL redirected from")
    status_code: int = Field(..., description="HTTP 3xx status code")
    location: Optional[str] = Field(default=None, description="Location header target")


class NetworkErrorDetail(BaseModel):
    """Categorized diagnostic detail for network and execution exceptions."""
    error_type: str = Field(..., description="Exception class name (e.g. DNSLookupError, TimeoutException)")
    error_category: Literal["dns", "network", "timeout", "security", "redirect", "protocol", "unknown"] = Field(
        default="unknown",
        description="Standardized error category"
    )
    message: str = Field(..., description="Human-readable error description")
    is_retryable: bool = Field(default=False, description="True if the request may succeed on immediate or backoff retry")
    troubleshooting_hint: str = Field(..., description="Actionable recommendation to resolve the failure")


class ExecutionResultResponse(BaseModel):
    """Complete execution result and network telemetry response."""
    url: str = Field(..., description="Final URL requested")
    method: str = Field(..., description="HTTP Method used")
    status_code: Optional[int] = Field(default=None, description="HTTP status code (null if connection failed)")
    status_text: Optional[str] = Field(default=None, description="HTTP status reason phrase")
    headers: Dict[str, str] = Field(default_factory=dict, description="Response headers received")
    cookies: Dict[str, str] = Field(default_factory=dict, description="Response cookies extracted from Set-Cookie")
    body: Optional[Any] = Field(default=None, description="Decoded response body (parsed JSON or text string)")
    is_binary: bool = Field(default=False, description="True if response is binary (image, pdf, stream)")
    raw_body_base64: Optional[str] = Field(default=None, description="Base64 encoded binary payload if is_binary is True")
    is_success: bool = Field(default=False, description="True if status_code is 2xx")
    is_redirect: bool = Field(default=False, description="True if status_code is 3xx")
    is_client_error: bool = Field(default=False, description="True if status_code is 4xx")
    is_server_error: bool = Field(default=False, description="True if status_code is 5xx")
    http_version: str = Field(default="HTTP/1.1", description="HTTP protocol version")
    elapsed_ms: float = Field(default=0.0, description="Total request execution latency in milliseconds with sub-millisecond precision")
    redirect_count: int = Field(default=0, description="Number of HTTP redirects followed")
    redirect_history: List[RedirectStep] = Field(default_factory=list, description="Chain of redirects followed")
    content_length: int = Field(default=0, description="Response body size in bytes")
    content_type: Optional[str] = Field(default=None, description="MIME content-type of response")
    error: Optional[str] = Field(default=None, description="Error message if execution failed before response")
    error_type: Optional[str] = Field(default=None, description="Error class name if execution failed")
    error_detail: Optional[NetworkErrorDetail] = Field(default=None, description="Structured diagnostic error breakdown")

    @classmethod
    def from_httpx_response(
        cls,
        response: Any,
        elapsed_ms: float,
        redirect_count: int = 0,
        redirect_history: Optional[List[RedirectStep]] = None,
        cookies: Optional[Dict[str, str]] = None,
        body: Optional[Any] = None,
        is_binary: bool = False,
        raw_body_base64: Optional[str] = None,
        content_type: Optional[str] = None
    ) -> "ExecutionResultResponse":
        """Factory constructor converting httpx.Response into ExecutionResultResponse."""
        status_code = response.status_code
        status_text = ""
        try:
            status_text = http.HTTPStatus(status_code).phrase
        except ValueError:
            status_text = response.reason_phrase or "Unknown"

        headers_dict = dict(response.headers)
        ct = content_type or response.headers.get("content-type")

        return cls(
            url=str(response.url),
            method=response.request.method if response.request else "GET",
            status_code=status_code,
            status_text=status_text,
            headers=headers_dict,
            cookies=cookies or {},
            body=body,
            is_binary=is_binary,
            raw_body_base64=raw_body_base64,
            is_success=(200 <= status_code < 300),
            is_redirect=(300 <= status_code < 400),
            is_client_error=(400 <= status_code < 500),
            is_server_error=(status_code >= 500),
            http_version=response.http_version or "HTTP/1.1",
            elapsed_ms=round(elapsed_ms, 3),
            redirect_count=redirect_count,
            redirect_history=redirect_history or [],
            content_length=len(response.content),
            content_type=ct or None,
            error=None,
            error_type=None,
            error_detail=None
        )


class ClientInfoResponse(BaseModel):
    """Current connection pool and HTTP client configuration metadata."""
    is_active: bool
    default_timeout: float
    max_concurrency: int
    max_keepalive: int
    environment: str
