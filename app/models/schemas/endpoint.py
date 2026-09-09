"""Pydantic DTO models for API Endpoint registration, updates, and responses."""
from enum import Enum
from datetime import datetime
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, field_validator, ConfigDict


class HTTPMethod(str, Enum):
    """Supported HTTP Methods for API testing."""
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


class EndpointBase(BaseModel):
    """Base schema for API Endpoint properties."""
    name: str = Field(..., min_length=1, max_length=150, description="Descriptive name of the API endpoint")
    description: Optional[str] = Field(None, description="Detailed explanation of endpoint purpose")
    method: HTTPMethod = Field(default=HTTPMethod.GET, description="HTTP Method")
    path: str = Field(..., min_length=1, max_length=500, description="URL path starting with / e.g. /api/v1/products/{id}")
    expected_status: int = Field(default=200, ge=100, le=599, description="Expected HTTP Status Code")
    is_active: bool = Field(default=True, description="Whether endpoint is active for testing")
    headers: Dict[str, str] = Field(default_factory=dict, description="Custom headers sent with request")
    query_params: Dict[str, Any] = Field(default_factory=dict, description="Default query parameters")
    path_params: Dict[str, Any] = Field(default_factory=dict, description="Path variable definitions")
    body_schema: Dict[str, Any] = Field(default_factory=dict, description="Request/response payload JSON schema")

    @field_validator("path")
    @classmethod
    def validate_path_format(cls, v: str) -> str:
        """Ensure endpoint path begins with a leading forward slash."""
        v = v.strip()
        if not v.startswith("/"):
            raise ValueError("Endpoint path must start with a leading slash '/' (e.g., '/api/v1/items')")
        return v

    @field_validator("name")
    @classmethod
    def validate_name_not_blank(cls, v: str) -> str:
        """Ensure name is not just whitespace."""
        v = v.strip()
        if not v:
            raise ValueError("Endpoint name cannot be blank")
        return v


class EndpointCreate(EndpointBase):
    """Schema for registering a new Endpoint under a Project."""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Get Product By ID",
                "description": "Retrieve product details by unique identifier",
                "method": "GET",
                "path": "/api/v1/products/{id}",
                "expected_status": 200,
                "is_active": True,
                "headers": {
                    "Accept": "application/json"
                },
                "query_params": {
                    "include_reviews": "true"
                },
                "path_params": {
                    "id": "101"
                },
                "body_schema": {}
            }
        }
    )


class EndpointUpdate(BaseModel):
    """Schema for updating an existing Endpoint."""
    name: Optional[str] = Field(None, min_length=1, max_length=150, description="Updated endpoint name")
    description: Optional[str] = Field(None, description="Updated endpoint description")
    method: Optional[HTTPMethod] = Field(None, description="Updated HTTP method")
    path: Optional[str] = Field(None, min_length=1, max_length=500, description="Updated path")
    expected_status: Optional[int] = Field(None, ge=100, le=599, description="Updated expected status code")
    is_active: Optional[bool] = Field(None, description="Updated active status")
    headers: Optional[Dict[str, str]] = Field(None, description="Updated request headers")
    query_params: Optional[Dict[str, Any]] = Field(None, description="Updated query parameters")
    path_params: Optional[Dict[str, Any]] = Field(None, description="Updated path parameters")
    body_schema: Optional[Dict[str, Any]] = Field(None, description="Updated body schema")

    @field_validator("path")
    @classmethod
    def validate_path_format(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not v.startswith("/"):
                raise ValueError("Endpoint path must start with a leading slash '/'")
            return v
        return v

    @field_validator("name")
    @classmethod
    def validate_name_not_blank(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("Endpoint name cannot be blank")
            return v
        return v


class EndpointDuplicate(BaseModel):
    """Schema for requesting endpoint duplication."""
    name: Optional[str] = Field(None, max_length=150, description="Optional custom name for the duplicated endpoint")


class EndpointResponse(EndpointBase):
    """Standard response model for API Endpoint records."""
    id: int = Field(..., description="Unique primary key of Endpoint")
    project_id: int = Field(..., description="ID of associated Project workspace")
    created_at: datetime = Field(..., description="Timestamp when endpoint was registered")
    updated_at: datetime = Field(..., description="Timestamp when endpoint was last modified")

    model_config = ConfigDict(from_attributes=True)
