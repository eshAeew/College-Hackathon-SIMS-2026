"""Validation Service: Protocol, Header, and Payload Syntax Verification Engine."""
import logging
from typing import Any, Dict, List, Optional, Union, Tuple

from app.models.schemas.validation import (
    ValidationCheckResult,
    StatusValidationRequest,
    ContentTypeValidationRequest,
    PayloadSyntaxValidationRequest,
    ProtocolValidationRequest,
    ProtocolValidationReport,
)
from app.utils.protocol_validator import (
    validate_status_code,
    validate_content_type,
    validate_payload_syntax,
    normalize_content_type,
)

logger = logging.getLogger("app.services.validation_service")


class ValidationService:
    """Service layer managing protocol and format verification."""

    @staticmethod
    def validate_status(
        actual_status: int,
        expected_status: Union[int, List[int], str]
    ) -> ValidationCheckResult:
        """Validate actual status code against expectation."""
        passed, msg = validate_status_code(actual_status, expected_status)
        return ValidationCheckResult(
            check_type="status_code",
            passed=passed,
            expected=expected_status,
            actual=actual_status,
            message=msg,
            details={"actual_status": actual_status, "expected_status": expected_status}
        )

    @staticmethod
    def validate_content_type_header(
        actual_ct: Optional[str],
        expected_ct: str
    ) -> ValidationCheckResult:
        """Validate actual Content-Type header against expectation."""
        passed, msg = validate_content_type(actual_ct, expected_ct)
        return ValidationCheckResult(
            check_type="content_type",
            passed=passed,
            expected=expected_ct,
            actual=actual_ct,
            message=msg,
            details={
                "actual_normalized": normalize_content_type(actual_ct),
                "expected_normalized": normalize_content_type(expected_ct)
            }
        )

    @staticmethod
    def validate_syntax(
        payload: Any,
        expected_format: str
    ) -> Tuple[ValidationCheckResult, Optional[Any]]:
        """Validate payload syntax (JSON, XML, Text, Binary)."""
        passed, parsed, err_msg, desc = validate_payload_syntax(payload, expected_format)
        check = ValidationCheckResult(
            check_type="payload_syntax",
            passed=passed,
            expected=expected_format,
            actual=type(parsed).__name__ if passed and parsed is not None else "invalid_or_empty",
            message=desc,
            details={"error": err_msg, "format": expected_format} if err_msg else {"format": expected_format}
        )
        return check, parsed

    @classmethod
    def validate_protocol(
        cls,
        req: ProtocolValidationRequest
    ) -> ProtocolValidationReport:
        """Perform combined protocol validation over status code, content-type, and payload syntax."""
        checks: List[ValidationCheckResult] = []
        parsed_payload: Optional[Any] = None

        # 1. Status Code Check (if expected_status provided)
        if req.expected_status is not None:
            status_check = cls.validate_status(req.actual_status, req.expected_status)
            checks.append(status_check)

        # 2. Content-Type Check (if expected_content_type provided)
        if req.expected_content_type is not None:
            ct_check = cls.validate_content_type_header(req.actual_content_type, req.expected_content_type)
            checks.append(ct_check)

        # 3. Payload Syntax Check (if expected_payload_format provided)
        if req.expected_payload_format is not None:
            syntax_check, parsed = cls.validate_syntax(req.raw_payload, req.expected_payload_format)
            checks.append(syntax_check)
            if syntax_check.passed:
                parsed_payload = parsed

        total = len(checks)
        passed_count = sum(1 for c in checks if c.passed)
        failed_count = total - passed_count
        all_passed = (failed_count == 0) if total > 0 else True

        summary = (
            f"All {total} protocol assertions passed successfully."
            if all_passed and total > 0
            else f"{failed_count} out of {total} protocol assertion(s) failed."
            if total > 0
            else "No protocol validation assertions were configured."
        )

        return ProtocolValidationReport(
            all_passed=all_passed,
            total_checks=total,
            passed_checks=passed_count,
            failed_checks=failed_count,
            checks=checks,
            parsed_payload=parsed_payload,
            summary=summary
        )
