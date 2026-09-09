"""Pydantic Schemas and DTOs for TestCase Management."""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.models.schemas.request_config import BodyType


class TestCaseSeverity(str, Enum):
    """Business criticality and failure severity level."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TestCaseBase(BaseModel):
    """Base schema for TestCase entity shared across Create, Update, and Response."""
    name: str = Field(
        ...,
        min_length=1,
        max_length=150,
        description="Clear, descriptive name of test scenario",
        examples=["Create Order - Valid Cart with Standard Shipping"]
    )
    description: Optional[str] = Field(
        default=None,
        description="Detailed scenario explanation and execution prerequisites",
        examples=["Verify that standard orders with authenticated customer ID return 201 Created."]
    )
    is_active: bool = Field(
        default=True,
        description="Whether this test case is enabled during automated test runs"
    )
    severity: TestCaseSeverity = Field(
        default=TestCaseSeverity.MEDIUM,
        description="Business impact severity rating"
    )
    tags: List[str] = Field(
        default_factory=list,
        description="Categorization tags (e.g. ['smoke', 'regression', 'security', 'negative'])",
        examples=[["smoke", "regression"]]
    )
    path_params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Path variables mapped to concrete values for this test",
        examples=[{"user_id": "usr-100", "order_id": "ord-200"}]
    )
    query_params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Query parameters for this test scenario",
        examples=[{"notify": "true", "format": "detailed"}]
    )
    headers: Dict[str, str] = Field(
        default_factory=dict,
        description="Scenario-specific HTTP headers",
        examples=[{"Authorization": "Bearer test-user-token"}]
    )
    body_type: BodyType = Field(
        default=BodyType.JSON,
        description="Payload serialization format"
    )
    body: Optional[Any] = Field(
        default=None,
        description="Request body payload data"
    )
    assertions: Dict[str, Any] = Field(
        default_factory=dict,
        description="Assertion rules and expectation specifications"
    )


class TestCaseCreate(TestCaseBase):
    """Payload for creating a new test scenario under an endpoint."""
    pass


class TestCaseUpdate(BaseModel):
    """Payload for updating an existing test scenario (all fields optional)."""
    name: Optional[str] = Field(default=None, min_length=1, max_length=150)
    description: Optional[str] = None
    is_active: Optional[bool] = None
    severity: Optional[TestCaseSeverity] = None
    tags: Optional[List[str]] = None
    path_params: Optional[Dict[str, Any]] = None
    query_params: Optional[Dict[str, Any]] = None
    headers: Optional[Dict[str, str]] = None
    body_type: Optional[BodyType] = None
    body: Optional[Any] = None
    assertions: Optional[Dict[str, Any]] = None


class TestCaseDuplicate(BaseModel):
    """Payload for duplicating an existing test scenario."""
    name: Optional[str] = Field(
        default=None,
        description="Custom name for the duplicated test case (defaults to '[Original Name] (Copy)')"
    )


class TestCaseResponse(TestCaseBase):
    """Complete TestCase response DTO."""
    id: int
    endpoint_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
