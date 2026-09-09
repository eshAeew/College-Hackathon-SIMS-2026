"""Validation Schemas: DTOs for Status Code, Content-Type, Payload Syntax, and JSON Schema Validation."""
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


class ValidationCheckResult(BaseModel):
    """Result of an individual validation assertion/check."""
    check_type: str = Field(..., description="Type of check performed (e.g. status_code, content_type, payload_syntax, json_schema)")
    passed: bool = Field(..., description="Whether the check satisfied expectations")
    expected: Optional[Any] = Field(None, description="Expected value or pattern")
    actual: Optional[Any] = Field(None, description="Actual value or outcome observed")
    message: str = Field(..., description="Human-readable result summary or failure explanation")
    details: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional contextual details")


class StatusValidationRequest(BaseModel):
    """Request payload for validating HTTP status code expectations."""
    actual_status: int = Field(..., ge=100, le=599, description="Actual HTTP response status code", example=200)
    expected_status: Union[int, List[int], str] = Field(
        ...,
        description="Expected status: exact int (200), list of ints ([200, 201]), class ('2xx'), or range ('200-299')",
        example="2xx"
    )


class ContentTypeValidationRequest(BaseModel):
    """Request payload for validating Content-Type headers."""
    actual_content_type: Optional[str] = Field(
        None,
        description="Actual Content-Type header returned by server",
        example="application/json; charset=utf-8"
    )
    expected_content_type: str = Field(
        ...,
        description="Expected Content-Type MIME type or format alias (e.g. 'json', 'application/json', 'xml')",
        example="application/json"
    )


class PayloadSyntaxValidationRequest(BaseModel):
    """Request payload for validating body structure and syntax against a format specifier."""
    payload: Any = Field(..., description="Response body content to parse and validate", example='{"status": "ok"}')
    expected_format: str = Field(..., description="Expected format: 'json', 'xml', 'text', 'binary'", example="json")


class ProtocolValidationRequest(BaseModel):
    """Comprehensive protocol validation request checking status, headers, and payload syntax together."""
    actual_status: int = Field(..., ge=100, le=599, description="Actual HTTP response status code", example=200)
    expected_status: Optional[Union[int, List[int], str]] = Field(None, description="Expected status specifier", example="2xx")
    actual_content_type: Optional[str] = Field(None, description="Actual Content-Type header", example="application/json; charset=utf-8")
    expected_content_type: Optional[str] = Field(None, description="Expected Content-Type or alias", example="json")
    raw_payload: Optional[Any] = Field(None, description="Raw response body string or object", example='{"status": "ok"}')
    expected_payload_format: Optional[str] = Field(None, description="Expected payload syntax format (e.g. 'json', 'xml')", example="json")


class ProtocolValidationReport(BaseModel):
    """Consolidated report of all protocol validation assertions."""
    all_passed: bool = Field(..., description="True if all executed checks passed, False if any failed")
    total_checks: int = Field(..., description="Total number of checks executed")
    passed_checks: int = Field(..., description="Number of passed checks")
    failed_checks: int = Field(..., description="Number of failed checks")
    checks: List[ValidationCheckResult] = Field(..., description="Individual check results")
    parsed_payload: Optional[Any] = Field(None, description="Parsed structured payload if syntax validation succeeded")
    summary: str = Field(..., description="Summary statement of protocol validation")


# --- JSON Schema Validation Schemas ---

class SchemaErrorDetail(BaseModel):
    """Granular field-level error detail encountered during JSON schema evaluation."""
    path: str = Field(..., description="JSONPath / dot-notation location of the erroneous field (e.g. 'users[0].address.zipcode')", example="users[0].email")
    field: Optional[str] = Field(None, description="Leaf field name that triggered the error", example="email")
    error_type: str = Field(..., description="Category of error (e.g. required_property_missing, type_mismatch, enum_constraint_violation)", example="type_mismatch")
    message: str = Field(..., description="Human-readable explanation of the schema violation")
    schema_path: str = Field(..., description="Location inside the JSON Schema definition where the rule failed", example="properties.users.items.properties.email")
    expected: Optional[Any] = Field(None, description="Expected type, pattern, or property state")
    actual: Optional[Any] = Field(None, description="Actual received type or value")


class TypeMismatchDetail(BaseModel):
    """Specific detail for data type mismatch errors."""
    path: str = Field(..., description="Path where the type mismatch occurred", example="data.count")
    expected: Any = Field(..., description="Expected type (e.g. 'integer', 'string', ['string', 'null'])", example="integer")
    actual: str = Field(..., description="Actual Python type observed (e.g. 'str', 'NoneType')", example="str")
    value: Optional[Any] = Field(None, description="Actual observed value")


class JsonSchemaValidationRequest(BaseModel):
    """Request payload for validating a JSON instance against an arbitrary JSON Schema."""
    instance: Any = Field(..., description="JSON data instance (dict, list, string, number, etc.) to validate", example={"id": 101, "name": "Item A"})
    schema_definition: Dict[str, Any] = Field(
        ...,
        description="Draft-7 JSON Schema dictionary defining expected structure, types, and constraints",
        example={
            "type": "object",
            "required": ["id", "name"],
            "properties": {
                "id": {"type": "integer"},
                "name": {"type": "string"}
            }
        }
    )


class JsonSchemaValidationReport(BaseModel):
    """Comprehensive evaluation report for JSON Schema validation."""
    is_valid: bool = Field(..., description="True if payload completely adheres to schema without errors, False otherwise")
    total_errors: int = Field(..., description="Count of schema rule violations detected")
    missing_fields: List[str] = Field(default_factory=list, description="List of required field paths absent from the instance")
    type_mismatches: List[TypeMismatchDetail] = Field(default_factory=list, description="List of data type mismatch violations")
    errors: List[SchemaErrorDetail] = Field(default_factory=list, description="All granular schema error details")
    summary: str = Field(..., description="Human-readable summary diff of validation results")


class EndpointResponseSchemaValidationRequest(BaseModel):
    """Request payload for validating response JSON against a registered endpoint's response schema."""
    response_payload: Any = Field(..., description="Actual response body (parsed JSON object/array or JSON string) to validate against the endpoint's contract", example={"id": 1, "name": "Alpha"})
