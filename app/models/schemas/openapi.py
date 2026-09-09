"""Pydantic DTO models for OpenAPI 3.0 / Swagger 2.0 Parsing and Importing (Stage 14)."""
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict


class OpenApiSpecVersion(str, Enum):
    """Supported OpenAPI / Swagger specification versions."""
    OPENAPI_3_0 = "OPENAPI_3_0"
    OPENAPI_3_1 = "OPENAPI_3_1"
    SWAGGER_2_0 = "SWAGGER_2_0"
    UNKNOWN = "UNKNOWN"


class ParameterLocation(str, Enum):
    """HTTP parameter placement location."""
    PATH = "path"
    QUERY = "query"
    HEADER = "header"
    COOKIE = "cookie"


class DiscoveredParameter(BaseModel):
    """Parameter extracted from OpenAPI specification."""
    name: str
    location: ParameterLocation
    required: bool = False
    schema_type: str = "string"
    description: Optional[str] = None
    default_value: Optional[Any] = None

    model_config = ConfigDict(extra="forbid")


class DiscoveredOperation(BaseModel):
    """API operation/endpoint discovered inside the OpenAPI specification."""
    path: str
    method: str
    summary: Optional[str] = None
    description: Optional[str] = None
    operation_id: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    
    parameters: List[DiscoveredParameter] = Field(default_factory=list)
    path_parameters: Dict[str, Any] = Field(default_factory=dict)
    query_parameters: Dict[str, Any] = Field(default_factory=dict)
    header_parameters: Dict[str, str] = Field(default_factory=dict)
    
    request_body_type: str = "json"
    request_body_schema: Optional[Dict[str, Any]] = None
    
    response_schemas: Dict[str, Any] = Field(default_factory=dict)
    expected_status_code: int = 200

    model_config = ConfigDict(from_attributes=True)


class ParsedOpenApiSummary(BaseModel):
    """In-memory parsed representation of an OpenAPI document."""
    title: str = "Untitled API"
    version: str = "1.0.0"
    spec_version: OpenApiSpecVersion
    description: Optional[str] = None
    servers: List[str] = Field(default_factory=list)
    total_operations: int
    operations: List[DiscoveredOperation] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class OpenApiParseRequest(BaseModel):
    """Payload to parse and preview an OpenAPI YAML/JSON document without importing."""
    spec_content: str = Field(..., min_length=5, description="Raw OpenAPI YAML or JSON specification string")

    model_config = ConfigDict(extra="forbid")


class OpenApiImportRequest(BaseModel):
    """Payload to parse and commit OpenAPI endpoints to a project."""
    spec_content: str = Field(..., min_length=5, description="Raw OpenAPI YAML or JSON specification string")
    overwrite_existing: bool = Field(default=True, description="Update existing endpoints with matching method and path")
    create_smoke_tests: bool = Field(default=False, description="Automatically generate a default smoke test case for each imported endpoint")

    model_config = ConfigDict(extra="forbid")


class ImportedEndpointDetail(BaseModel):
    """Record of an individual endpoint imported into the database."""
    id: int
    name: str
    method: str
    path: str
    status: str  # CREATED, UPDATED, SKIPPED

    model_config = ConfigDict(from_attributes=True)


class OpenApiImportReport(BaseModel):
    """Complete summary report of an OpenAPI import transaction."""
    project_id: int
    spec_title: str
    spec_version: str
    total_discovered: int
    created_count: int
    updated_count: int
    skipped_count: int
    endpoints: List[ImportedEndpointDetail] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
