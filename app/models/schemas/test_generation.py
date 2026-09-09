"""Pydantic Schemas and DTOs for Automatic Test Generation (Stage 15)."""
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, ConfigDict, Field

from app.models.schemas.request_config import BodyType
from app.models.schemas.test_case import TestCaseSeverity


class TestGenerationStrategy(str, Enum):
    """Strategies used for automated test case synthesis."""
    HAPPY_PATH = "happy_path"
    MISSING_REQUIRED = "missing_required"
    INVALID_TYPE = "invalid_type"
    BOUNDARY_VALUE = "boundary_value"
    NULL_INJECTION = "null_injection"
    ALL = "all"


class GeneratedTestCategory(str, Enum):
    """Classification category of generated test scenarios."""
    POSITIVE = "positive"
    NEGATIVE = "negative"
    SECURITY = "security"
    BOUNDARY = "boundary"


class StagedTestCase(BaseModel):
    """A synthesized test case staged in-memory for review, editing, and acceptance."""
    temporary_id: str = Field(..., description="Unique transient ID within the staged session (e.g. STG-001)")
    name: str = Field(..., min_length=1, max_length=150, description="Clear, descriptive scenario name")
    description: Optional[str] = Field(default=None, description="Detailed explanation of what this test verifies")
    category: GeneratedTestCategory = Field(default=GeneratedTestCategory.POSITIVE, description="Test classification category")
    strategy: TestGenerationStrategy = Field(default=TestGenerationStrategy.HAPPY_PATH, description="Synthesis strategy applied")
    severity: TestCaseSeverity = Field(default=TestCaseSeverity.MEDIUM, description="Business criticality and severity rating")
    tags: List[str] = Field(default_factory=list, description="Classification tags (e.g. ['auto-generated', 'positive'])")
    path_params: Dict[str, Any] = Field(default_factory=dict, description="Concrete path parameter mapping")
    query_params: Dict[str, Any] = Field(default_factory=dict, description="Concrete query parameter mapping")
    headers: Dict[str, str] = Field(default_factory=dict, description="Request headers")
    body_type: BodyType = Field(default=BodyType.JSON, description="Body serialization format")
    body: Optional[Any] = Field(default=None, description="Request payload body")
    expected_status: int = Field(default=200, description="Expected HTTP response status code")
    assertions: Dict[str, Any] = Field(default_factory=dict, description="Generated assertion rules dictionary")
    is_selected: bool = Field(default=True, description="Whether this test case is selected for acceptance into the database")


class TestGenerationOptions(BaseModel):
    """Configurable options governing automatic test generation."""
    strategies: List[TestGenerationStrategy] = Field(
        default=[TestGenerationStrategy.ALL],
        description="Target strategies to generate"
    )
    include_positive: bool = Field(default=True, description="Include valid happy path tests")
    include_negative: bool = Field(default=True, description="Include edge cases and negative mutation tests")
    max_tests_per_endpoint: int = Field(default=15, ge=1, le=50, description="Maximum test cases to synthesize per endpoint")
    default_headers: Dict[str, str] = Field(default_factory=dict, description="Global default headers to attach")
    custom_path_params: Dict[str, Any] = Field(default_factory=dict, description="User-supplied path param overrides")
    custom_query_params: Dict[str, Any] = Field(default_factory=dict, description="User-supplied query param overrides")


class AdHocTestGenerationRequest(BaseModel):
    """Request payload for synthesizing test cases from raw parameters/schemas."""
    method: str = Field(default="GET", description="HTTP method (GET, POST, PUT, DELETE, PATCH)")
    path: str = Field(..., description="API route path, e.g. /users/{user_id}")
    headers: Dict[str, str] = Field(default_factory=dict, description="Default headers")
    query_params: Dict[str, Any] = Field(default_factory=dict, description="Sample or schema query parameters")
    path_params: Dict[str, Any] = Field(default_factory=dict, description="Sample path parameters")
    body_schema: Optional[Dict[str, Any]] = Field(default=None, description="JSON Schema definition for request body")
    expected_status: Optional[int] = Field(default=None, description="Default expected HTTP status code")
    options: TestGenerationOptions = Field(default_factory=TestGenerationOptions, description="Generation configuration options")


class EndpointTestGenerationRequest(BaseModel):
    """Request payload for generating tests against a stored endpoint entity."""
    options: TestGenerationOptions = Field(default_factory=TestGenerationOptions, description="Generation configuration options")


class TestGenerationStagingResponse(BaseModel):
    """Staging area preview response containing synthesized test cases for review."""
    endpoint_id: Optional[int] = Field(default=None, description="Target endpoint ID if stored in DB")
    endpoint_name: Optional[str] = Field(default=None, description="Target endpoint name")
    method: str = Field(..., description="HTTP Method")
    path: str = Field(..., description="Endpoint Path")
    total_generated: int = Field(..., description="Total synthesized test cases")
    positive_count: int = Field(..., description="Number of positive test scenarios")
    negative_count: int = Field(..., description="Number of negative/boundary test scenarios")
    staged_tests: List[StagedTestCase] = Field(default_factory=list, description="List of staged test cases for inspection")


class AcceptStagedTestsRequest(BaseModel):
    """Payload to approve and persist selected staged test cases into the database."""
    staged_tests: List[StagedTestCase] = Field(..., description="List of approved staged test cases to save")
    activate_immediately: bool = Field(default=True, description="Whether saved test cases should be marked is_active=True")


class AcceptStagedTestsResponse(BaseModel):
    """Response returned upon successfully persisting staged test cases into database."""
    endpoint_id: int = Field(..., description="Target Endpoint ID")
    total_accepted: int = Field(..., description="Number of test cases persisted into database")
    created_test_case_ids: List[int] = Field(default_factory=list, description="List of newly created TestCase primary keys")
    message: str = Field(..., description="Human-readable status summary")


class BulkProjectTestGenerationRequest(BaseModel):
    """Request to synthesize test suites across multiple or all endpoints in a Project."""
    endpoint_ids: Optional[List[int]] = Field(default=None, description="Specific endpoint IDs to generate for (all if omitted)")
    options: TestGenerationOptions = Field(default_factory=TestGenerationOptions, description="Generation configuration options")
    auto_accept: bool = Field(default=False, description="If True, directly persist generated tests into database without staging review")


class BulkProjectTestGenerationResponse(BaseModel):
    """Summary of bulk test generation across a project."""
    project_id: int = Field(..., description="Project ID")
    total_endpoints_processed: int = Field(..., description="Number of endpoints processed")
    total_tests_generated: int = Field(..., description="Total test cases synthesized across all endpoints")
    total_tests_accepted: int = Field(default=0, description="Total test cases persisted if auto_accept was enabled")
    endpoint_results: List[TestGenerationStagingResponse] = Field(default_factory=list, description="Per-endpoint staging summaries")
