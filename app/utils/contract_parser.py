"""Utilities for parsing URL path parameters, validating JSON schemas, and verifying API contracts."""
import re
from typing import List, Dict, Any, Tuple, Optional
import jsonschema
from jsonschema.exceptions import SchemaError


def extract_path_variables(path: str) -> List[str]:
    """Extract path parameter placeholder variable names from a URL path template.
    
    Example:
        '/api/v1/stores/{store_id}/products/{product_id}' -> ['store_id', 'product_id']
    """
    if not path:
        return []
    # Match {variable_name} adhering to standard identifier rules
    matches = re.findall(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", path)
    return list(dict.fromkeys(matches))  # Preserve order while removing any duplicates


def validate_json_schema(schema: Optional[Dict[str, Any]]) -> Tuple[bool, Optional[str]]:
    """Validate whether a dictionary is a valid JSON Schema according to Draft 7 / Draft 2020-12.
    
    Returns:
        (True, None) if valid or empty.
        (False, error_message) if schema syntax is invalid.
    """
    if not schema or schema == {}:
        return True, None

    if not isinstance(schema, dict):
        return False, "JSON Schema must be a dictionary object"

    try:
        jsonschema.Draft7Validator.check_schema(schema)
        return True, None
    except SchemaError as exc:
        return False, exc.message
    except Exception as exc:
        return False, str(exc)


def validate_contract_specification(
    path: str,
    path_params: Dict[str, Any],
    body_schema: Optional[Dict[str, Any]] = None,
    response_schema: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Inspect and validate the completeness of an endpoint contract specification.
    
    Checks:
    - Identifies all URL path variable placeholders.
    - Flags any path variables not mapped in path_params.
    - Validates request body JSON Schema syntax.
    - Validates expected response body JSON Schema syntax.
    """
    errors: List[str] = []
    path_vars = extract_path_variables(path)
    
    # Check for missing path parameters
    missing_params = [var for var in path_vars if var not in path_params or path_params[var] in (None, "")]

    # Validate Request Body Schema
    if body_schema:
        valid_req, req_err = validate_json_schema(body_schema)
        if not valid_req:
            errors.append(f"Invalid request body schema: {req_err}")

    # Validate Response Body Schema
    if response_schema:
        valid_res, res_err = validate_json_schema(response_schema)
        if not valid_res:
            errors.append(f"Invalid response body schema: {res_err}")

    is_valid = (len(errors) == 0) and (len(missing_params) == 0)

    return {
        "is_valid": is_valid,
        "path_variables": path_vars,
        "missing_path_params": missing_params,
        "errors": errors
    }


def merge_declared_path_params(
    path: Optional[str],
    supplied: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Ensure every {placeholder} declared in a path template appears in path_params.

    Placeholders the caller did not supply a value for are recorded with an empty string,
    so the stored contract always advertises which variables an endpoint requires.
    """
    merged: Dict[str, Any] = dict(supplied or {})
    for variable in extract_path_variables(path or ""):
        merged.setdefault(variable, "")
    return merged
