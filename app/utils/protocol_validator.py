"""Protocol Validation Engine: Status Code Matcher, MIME Type Normalizer, and Payload Syntax Validator."""
import json
import logging
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger("app.utils.protocol_validator")

# Common Content-Type Aliases
CONTENT_TYPE_ALIASES = {
    "json": "application/json",
    "xml": "application/xml",
    "text": "text/plain",
    "plain": "text/plain",
    "html": "text/html",
    "form": "application/x-www-form-urlencoded",
    "form_data": "application/x-www-form-urlencoded",
    "form-data": "application/x-www-form-urlencoded",
    "multipart": "multipart/form-data",
    "binary": "application/octet-stream",
    "pdf": "application/pdf"
}


def normalize_content_type(ct: Optional[str]) -> Optional[str]:
    """Normalize and strip parameters (e.g. charset=utf-8) from Content-Type string."""
    if not ct or not isinstance(ct, str):
        return None
    cleaned = ct.split(";")[0].strip().lower()
    return CONTENT_TYPE_ALIASES.get(cleaned, cleaned)


def validate_status_code(
    actual: int,
    expected: Union[int, List[int], str]
) -> Tuple[bool, str]:
    """Validate whether actual status code satisfies expected specification.
    
    Supports:
    - Exact int: 200
    - List of ints: [200, 201, 204]
    - Status class range: "2xx", "4xx", "5xx"
    - Numeric range string: "200-299"
    """
    if expected is None:
        return True, "No expected status code specified (skipped)."

    # Case 1: Exact integer
    if isinstance(expected, int):
        if actual == expected:
            return True, f"HTTP status {actual} matches expected {expected}."
        return False, f"Expected HTTP status {expected}, but received {actual}."

    # Case 2: List or tuple of integers
    if isinstance(expected, (list, tuple, set)):
        expected_ints = []
        for item in expected:
            try:
                expected_ints.append(int(item))
            except (ValueError, TypeError):
                pass

        if actual in expected_ints:
            return True, f"HTTP status {actual} is in allowed list: {expected_ints}."
        return False, f"Expected HTTP status in {expected_ints}, but received {actual}."

    # Case 3: String range or class (e.g. "2xx", "200-299")
    if isinstance(expected, str):
        exp_str = expected.strip().lower()

        # Check "2xx", "3xx", "4xx", "5xx"
        if len(exp_str) == 3 and exp_str.endswith("xx") and exp_str[0].isdigit():
            lead_digit = int(exp_str[0])
            actual_lead = actual // 100
            if actual_lead == lead_digit:
                return True, f"HTTP status {actual} satisfies {expected.upper()} range."
            return False, f"Expected HTTP status in range {expected.upper()}, but received {actual}."

        # Check numeric range "200-299"
        if "-" in exp_str:
            parts = exp_str.split("-")
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                low, high = int(parts[0]), int(parts[1])
                if low <= actual <= high:
                    return True, f"HTTP status {actual} is within range [{low}, {high}]."
                return False, f"Expected HTTP status in range [{low}, {high}], but received {actual}."

        # Single string integer "200"
        if exp_str.isdigit():
            exp_int = int(exp_str)
            if actual == exp_int:
                return True, f"HTTP status {actual} matches expected {exp_int}."
            return False, f"Expected HTTP status {exp_int}, but received {actual}."

    return False, f"Unknown status code expectation format: '{expected}'."


def validate_content_type(
    actual_ct: Optional[str],
    expected_ct: str
) -> Tuple[bool, str]:
    """Validate whether actual Content-Type matches expected format, normalizing charsets and aliases."""
    if not expected_ct:
        return True, "No expected Content-Type specified (skipped)."

    norm_actual = normalize_content_type(actual_ct)
    norm_expected = normalize_content_type(expected_ct)

    if not norm_actual:
        return False, f"Expected Content-Type '{norm_expected}', but no Content-Type header was returned."

    # Exact or alias match
    if norm_actual == norm_expected:
        return True, f"Content-Type '{norm_actual}' matches expected '{norm_expected}'."

    # Substring / structured suffix match (e.g., application/problem+json matches application/json)
    if norm_expected in norm_actual or (norm_expected.endswith("/json") and "+json" in norm_actual):
        return True, f"Content-Type '{norm_actual}' matches compatible expected '{norm_expected}'."

    return False, f"Expected Content-Type '{norm_expected}', but received '{norm_actual}'."


def validate_payload_syntax(
    raw_body: Any,
    expected_format: str
) -> Tuple[bool, Optional[Any], Optional[str], str]:
    """Validate that response body complies with the expected format syntax (JSON/XML/Text).
    
    Returns:
        (passed, parsed_body, error_message, description)
    """
    fmt = expected_format.strip().lower()

    if raw_body is None or raw_body == "":
        if fmt in ("empty", "none"):
            return True, None, None, "Payload is correctly empty."
        return False, None, "Empty payload", f"Expected {fmt.upper()} payload, but response body was empty."

    # Convert to string if bytes
    body_str = raw_body.decode("utf-8") if isinstance(raw_body, bytes) else str(raw_body)

    # 1. JSON Syntax Validation
    if fmt in ("json", "application/json"):
        if isinstance(raw_body, (dict, list)):
            return True, raw_body, None, "Valid JSON payload (already parsed structure)."
        try:
            parsed = json.loads(body_str)
            return True, parsed, None, "Valid JSON payload syntax."
        except json.JSONDecodeError as exc:
            err_msg = f"Malformed JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
            return False, None, err_msg, err_msg
        except Exception as exc:
            return False, None, str(exc), f"Failed to parse JSON payload: {str(exc)}"

    # 2. XML Syntax Validation (Defensive against XXE)
    elif fmt in ("xml", "application/xml", "text/xml"):
        try:
            parser = ET.XMLParser()
            parsed_xml = ET.fromstring(body_str, parser=parser)
            return True, parsed_xml.tag, None, f"Valid XML payload syntax with root element <{parsed_xml.tag}>."
        except ET.ParseError as exc:
            err_msg = f"Malformed XML syntax: {str(exc)}"
            return False, None, err_msg, err_msg
        except Exception as exc:
            return False, None, str(exc), f"Failed to parse XML payload: {str(exc)}"

    # 3. Plain Text Validation
    elif fmt in ("text", "text/plain", "plain"):
        return True, body_str, None, f"Valid text payload ({len(body_str)} characters)."

    # 4. Binary / Raw format
    elif fmt in ("binary", "raw", "octet-stream"):
        return True, body_str, None, "Binary / Raw payload accepted."

    return False, None, f"Unsupported payload format '{expected_format}'", f"Format '{expected_format}' is not recognized."
