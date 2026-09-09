"""Validation API Endpoints: Status Code, Content-Type, Payload Syntax, and JSON Schema Verification."""
from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.schemas.response import StandardResponse
from app.models.schemas.validation import (
    ValidationCheckResult,
    StatusValidationRequest,
    ContentTypeValidationRequest,
    PayloadSyntaxValidationRequest,
    ProtocolValidationRequest,
    ProtocolValidationReport,
    JsonSchemaValidationRequest,
    JsonSchemaValidationReport,
    EndpointResponseSchemaValidationRequest,
)
from app.services.validation_service import ValidationService

router = APIRouter(prefix="/validations", tags=["Validation Engine"])


@router.post(
    "/status-code",
    response_model=StandardResponse[ValidationCheckResult],
    status_code=status.HTTP_200_OK,
    summary="Validate HTTP Status Code",
    description="Validates an actual HTTP status code against exact values, list of codes, '2xx' range classes, or numeric ranges ('200-299')."
)
async def validate_status_code_endpoint(
    req: StatusValidationRequest
) -> StandardResponse[ValidationCheckResult]:
    """Validate HTTP status code expectation."""
    result = ValidationService.validate_status(req.actual_status, req.expected_status)
    return StandardResponse(
        success=result.passed,
        data=result,
        message=result.message
    )


@router.post(
    "/content-type",
    response_model=StandardResponse[ValidationCheckResult],
    status_code=status.HTTP_200_OK,
    summary="Validate Content-Type Header",
    description="Validates a Content-Type header against expected MIME types or aliases, stripping parameters like charset."
)
async def validate_content_type_endpoint(
    req: ContentTypeValidationRequest
) -> StandardResponse[ValidationCheckResult]:
    """Validate Content-Type header expectation."""
    result = ValidationService.validate_content_type_header(req.actual_content_type, req.expected_content_type)
    return StandardResponse(
        success=result.passed,
        data=result,
        message=result.message
    )


@router.post(
    "/payload-syntax",
    response_model=StandardResponse[ValidationCheckResult],
    status_code=status.HTTP_200_OK,
    summary="Validate Payload Syntax (JSON/XML/Text)",
    description="Safely validates and parses response body payloads to ensure adherence to JSON, XML, or plain text syntax."
)
async def validate_payload_syntax_endpoint(
    req: PayloadSyntaxValidationRequest
) -> StandardResponse[ValidationCheckResult]:
    """Validate body payload syntax."""
    result, _ = ValidationService.validate_syntax(req.payload, req.expected_format)
    return StandardResponse(
        success=result.passed,
        data=result,
        message=result.message
    )


@router.post(
    "/protocol",
    response_model=StandardResponse[ProtocolValidationReport],
    status_code=status.HTTP_200_OK,
    summary="Comprehensive Protocol & Format Validation",
    description="Executes composite protocol validation across status code, Content-Type headers, and payload structure in a single call."
)
async def validate_protocol_endpoint(
    req: ProtocolValidationRequest
) -> StandardResponse[ProtocolValidationReport]:
    """Execute composite protocol validation."""
    report = ValidationService.validate_protocol(req)
    return StandardResponse(
        success=report.all_passed,
        data=report,
        message=report.summary
    )


@router.post(
    "/json-schema",
    response_model=StandardResponse[JsonSchemaValidationReport],
    status_code=status.HTTP_200_OK,
    summary="Validate JSON Payload Against Draft-7 JSON Schema",
    description="Exhaustively validates any JSON instance against a Draft-7 / Draft 2020-12 schema, reporting field-level missing properties, type mismatches, and constraint diffs."
)
async def validate_json_schema_endpoint(
    req: JsonSchemaValidationRequest
) -> StandardResponse[JsonSchemaValidationReport]:
    """Validate ad-hoc JSON instance against provided schema definition."""
    report = ValidationService.validate_json_schema(req.instance, req.schema_definition)
    return StandardResponse(
        success=report.is_valid,
        data=report,
        message=report.summary
    )


@router.post(
    "/endpoints/{endpoint_id}/response-schema",
    response_model=StandardResponse[JsonSchemaValidationReport],
    status_code=status.HTTP_200_OK,
    summary="Validate Observed Response Against Stored Endpoint Contract",
    description="Validates an actual response payload directly against the registered response_schema of a saved API endpoint."
)
async def validate_endpoint_response_schema_endpoint(
    endpoint_id: int = Path(..., description="Target Endpoint ID", ge=1),
    req: EndpointResponseSchemaValidationRequest = ...,
    db: Session = Depends(get_db)
) -> StandardResponse[JsonSchemaValidationReport]:
    """Validate response payload against stored endpoint contract."""
    report = ValidationService.validate_endpoint_response_schema(endpoint_id, req.response_payload, db)
    return StandardResponse(
        success=report.is_valid,
        data=report,
        message=report.summary
    )
