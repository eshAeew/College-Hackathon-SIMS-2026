"""Pydantic DTO models for Request Configuration, compilation, pre-flight validation, and serialization."""
from enum import Enum
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field, field_validator, ConfigDict
from app.models.schemas.endpoint import HTTPMethod


class BodyType(str, Enum):
    """Supported request body encoding types."""
    JSON = "json"
    FORM_DATA = "form_data"
    RAW_TEXT = "raw_text"
    EMPTY = "empty"


class RequestCompileOverride(BaseModel):
    """Runtime parameter overrides applied during request compilation or pre-flight validation."""
    base_url: Optional[str] = Field(None, description="Override project base URL (e.g. for staging or mock targets)")
    path_params: Optional[Dict[str, Any]] = Field(None, description="Override path variable values")
    query_params: Optional[Dict[str, Any]] = Field(None, description="Override query parameters")
    headers: Optional[Dict[str, str]] = Field(None, description="Additional or override request headers")
    body: Optional[Any] = Field(None, description="Override request payload body")
    body_type: Optional[BodyType] = Field(None, description="Override body encoding format")


class DirectRequestBuilderRequest(BaseModel):
    """Direct request compilation payload without database lookup."""
    base_url: str = Field(..., description="Target server base URL (e.g. https://api.store.com)")
    method: HTTPMethod = Field(default=HTTPMethod.GET, description="HTTP Method")
    path: str = Field(..., description="URL path with optional {variable} placeholders")
    path_params: Dict[str, Any] = Field(default_factory=dict, description="Path variable concrete values")
    query_params: Dict[str, Any] = Field(default_factory=dict, description="Query parameters")
    headers: Dict[str, str] = Field(default_factory=dict, description="Request headers")
    body: Optional[Any] = Field(None, description="Request payload body")
    body_type: BodyType = Field(default=BodyType.JSON, description="Body encoding type")

    @field_validator("path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith("/"):
            raise ValueError("Path must start with a leading slash '/' (e.g. '/api/v1/items')")
        return v

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, v: str) -> str:
        v = v.strip().rstrip("/")
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("Base URL must begin with 'http://' or 'https://'")
        return v


class CompiledRequestResponse(BaseModel):
    """Resolved, executable HTTP request metadata ready for network execution."""
    method: str = Field(..., description="HTTP Method")
    url: str = Field(..., description="Fully resolved target URL including query parameters")
    base_url: str = Field(..., description="Resolved base URL")
    resolved_path: str = Field(..., description="Path with interpolated variables")
    headers: Dict[str, str] = Field(default_factory=dict, description="Merged effective request headers")
    query_params: Dict[str, Any] = Field(default_factory=dict, description="Effective query parameters")
    path_params: Dict[str, Any] = Field(default_factory=dict, description="Effective path parameters")
    body_type: BodyType = Field(..., description="Body encoding format")
    body: Optional[Any] = Field(None, description="Resolved body object/payload")
    raw_body_preview: Optional[str] = Field(None, description="Raw serialized string representation of body")
    curl_command: str = Field(..., description="Executable cURL command string representation")

    model_config = ConfigDict(from_attributes=True)


class PreflightValidationRequest(BaseModel):
    """Ad-hoc pre-flight validation request payload."""
    base_url: str = Field(..., description="Target server base URL (e.g. https://api.store.com)")
    method: HTTPMethod = Field(default=HTTPMethod.GET, description="HTTP Method")
    path: str = Field(..., description="URL path with optional {variable} placeholders")
    path_params: Dict[str, Any] = Field(default_factory=dict, description="Path variable concrete values")
    query_params: Dict[str, Any] = Field(default_factory=dict, description="Query parameters")
    headers: Dict[str, str] = Field(default_factory=dict, description="Request headers")
    body: Optional[Any] = Field(None, description="Request payload body")
    body_type: BodyType = Field(default=BodyType.JSON, description="Body encoding type")


class PreflightValidationReport(BaseModel):
    """Comprehensive diagnostic report verifying request execution safety."""
    is_valid: bool = Field(..., description="Whether the request is completely safe and valid for execution")
    target_url: Optional[str] = Field(None, description="Preview of fully resolved target URL if valid")
    url_valid: bool = Field(..., description="Whether the base URL and path are syntactically valid")
    scheme_valid: bool = Field(..., description="Whether the scheme is valid (http/https)")
    host_valid: bool = Field(..., description="Whether the hostname/domain is valid")
    port_valid: bool = Field(..., description="Whether the port is within valid range (1-65535)")
    path_params_complete: bool = Field(..., description="Whether all URL path variables are resolved")
    missing_path_params: List[str] = Field(default_factory=list, description="Unassigned path variables if any")
    body_valid: bool = Field(..., description="Whether the body payload syntax matches body_type")
    headers_valid: bool = Field(..., description="Whether request headers comply with HTTP standards")
    errors: List[str] = Field(default_factory=list, description="List of blocking errors preventing execution")
    warnings: List[str] = Field(default_factory=list, description="Helpful non-blocking suggestions and security warnings")

    model_config = ConfigDict(from_attributes=True)
