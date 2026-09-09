"""Structured exception hierarchy for API Sentinel platform errors."""
from typing import Any, Dict, Optional


class SentinelBaseException(Exception):
    """Base exception class for all custom API Sentinel exceptions."""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_PLATFORM_ERROR",
        status_code: int = 500,
        details: Optional[Any] = None,
        hint: Optional[str] = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details
        self.hint = hint or "Check platform logs or verify request configuration."


class EntityNotFoundException(SentinelBaseException):
    """Raised when a requested workspace, endpoint, test case, or run does not exist."""

    def __init__(self, entity_name: str, entity_id: Any, hint: Optional[str] = None):
        super().__init__(
            message=f"{entity_name} with ID '{entity_id}' was not found.",
            code="ENTITY_NOT_FOUND",
            status_code=404,
            details={"entity": entity_name, "id": str(entity_id)},
            hint=hint or f"Verify the {entity_name} ID and ensure it has not been deleted.",
        )


class ContractValidationException(SentinelBaseException):
    """Raised when request parameters, JSON Schema, or headers violate endpoint contracts."""

    def __init__(self, message: str, details: Optional[Any] = None, hint: Optional[str] = None):
        super().__init__(
            message=message,
            code="CONTRACT_VALIDATION_ERROR",
            status_code=422,
            details=details,
            hint=hint or "Review parameter schemas and required fields against endpoint definition.",
        )


class ExecutionTimeoutException(SentinelBaseException):
    """Raised when an HTTP probe to a target API exceeds the configured timeout threshold."""

    def __init__(self, target_url: str, timeout_seconds: float, hint: Optional[str] = None):
        super().__init__(
            message=f"Request to '{target_url}' timed out after {timeout_seconds}s.",
            code="EXECUTION_TIMEOUT",
            status_code=504,
            details={"target_url": target_url, "timeout_seconds": timeout_seconds},
            hint=hint or "Check target server health, network connectivity, or increase timeout ceiling.",
        )


class NetworkConnectivityException(SentinelBaseException):
    """Raised when low-level DNS, socket connect, or SSL errors occur."""

    def __init__(self, target_url: str, error_type: str, details: Optional[Any] = None, hint: Optional[str] = None):
        super().__init__(
            message=f"Network error ({error_type}) connecting to '{target_url}'.",
            code="NETWORK_CONNECTIVITY_ERROR",
            status_code=502,
            details={"target_url": target_url, "error_type": error_type, "raw_error": str(details)},
            hint=hint or "Verify target hostname, port, and DNS resolution.",
        )


class SafetyViolationException(SentinelBaseException):
    """Raised when a target host is not allowlisted or a destructive action lacks authorization."""

    def __init__(self, message: str, details: Optional[Any] = None, hint: Optional[str] = None):
        super().__init__(
            message=message,
            code="SAFETY_VIOLATION",
            status_code=403,
            details=details,
            hint=hint or "Check project host allowlist and destructive operation policies.",
        )


class CircuitBreakerOpenException(SentinelBaseException):
    """Raised when a target host's circuit breaker is in OPEN state."""

    def __init__(self, host: str, cooldown_remaining: float, consecutive_failures: int):
        super().__init__(
            message=f"Circuit breaker for host '{host}' is OPEN ({consecutive_failures} consecutive failures). Request blocked to protect system.",
            code="CIRCUIT_BREAKER_OPEN",
            status_code=503,
            details={
                "host": host,
                "cooldown_remaining_seconds": round(cooldown_remaining, 1),
                "consecutive_failures": consecutive_failures,
            },
            hint=f"Target host '{host}' is repeatedly failing. Wait {round(cooldown_remaining, 1)}s for half-open trial probe or reset manually via /api/v1/resilience/circuit-breakers/{host}/reset.",
        )


class ParserException(SentinelBaseException):
    """Raised when input payload format (JSON/XML/YAML) is malformed."""

    def __init__(self, format_type: str, raw_error: str, hint: Optional[str] = None):
        super().__init__(
            message=f"Failed to parse {format_type} payload: {raw_error}",
            code="PAYLOAD_PARSE_ERROR",
            status_code=400,
            details={"format": format_type, "error": raw_error},
            hint=hint or f"Ensure payload conforms to valid {format_type} syntax.",
        )
