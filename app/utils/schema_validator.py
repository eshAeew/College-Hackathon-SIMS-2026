"""JSON Schema & Strict Type Validator Utility.

Provides exhaustive field-level validation, path resolution, type mismatch extraction,
and human-readable diff reporting using jsonschema Draft 7 / Draft 2020-12 standards.
"""
import logging
from typing import Any, Dict, List, Optional, Tuple
import jsonschema
from jsonschema.exceptions import SchemaError, ValidationError

logger = logging.getLogger("app.utils.schema_validator")


def format_json_path(path_deque) -> str:
    """Format a jsonschema error path deque into standard dot/bracket notation.
    
    Example:
        ['users', 0, 'address', 'city'] -> "users[0].address.city"
        [] -> "$"
    """
    if not path_deque:
        return "$"
    parts = []
    for item in path_deque:
        if isinstance(item, int):
            parts.append(f"[{item}]")
        else:
            if parts and not parts[-1].endswith("]"):
                parts.append(f".{item}")
            elif not parts:
                parts.append(str(item))
            else:
                parts.append(f".{item}")
    return "".join(parts)


def validate_json_schema_instance(
    instance: Any,
    schema: Optional[Dict[str, Any]]
) -> Tuple[bool, List[Dict[str, Any]], Dict[str, Any]]:
    """Validate a JSON data instance against a JSON Schema definition.
    
    Returns:
        (is_valid, error_list, summary_stats)
    """
    if schema is None or schema == {}:
        return True, [], {"total_errors": 0, "missing_fields": [], "type_mismatches": [], "summary": "No schema provided (validation skipped)."}

    if not isinstance(schema, dict):
        return False, [{
            "path": "$",
            "field": None,
            "error_type": "invalid_schema",
            "message": "JSON Schema must be a valid dictionary object.",
            "schema_path": "#",
            "expected": "dict",
            "actual": type(schema).__name__
        }], {
            "total_errors": 1,
            "missing_fields": [],
            "type_mismatches": [],
            "summary": "Schema definition is invalid."
        }

    # Verify schema syntax integrity first
    try:
        jsonschema.Draft7Validator.check_schema(schema)
    except SchemaError as exc:
        return False, [{
            "path": "$",
            "field": None,
            "error_type": "schema_syntax_error",
            "message": f"Malformed JSON Schema syntax: {exc.message}",
            "schema_path": format_json_path(exc.schema_path),
            "expected": None,
            "actual": None
        }], {
            "total_errors": 1,
            "missing_fields": [],
            "type_mismatches": [],
            "summary": f"Malformed JSON Schema: {exc.message}"
        }

    validator = jsonschema.Draft7Validator(schema)
    errors: List[Dict[str, Any]] = []
    missing_fields: List[str] = []
    type_mismatches: List[Dict[str, Any]] = []

    for err in validator.iter_errors(instance):
        path_str = format_json_path(err.path)
        schema_path_str = format_json_path(err.schema_path)
        validator_name = err.validator
        field_name = str(err.path[-1]) if err.path else None

        # 1. Missing Required Properties
        if validator_name == "required":
            missing_prop = None
            if "'" in err.message:
                missing_prop = err.message.split("'")[1]
            elif hasattr(err, "validator_value") and isinstance(err.validator_value, list):
                for prop in err.validator_value:
                    if isinstance(err.instance, dict) and prop not in err.instance:
                        missing_prop = prop
                        break

            target_path = f"{path_str}.{missing_prop}" if path_str != "$" else (missing_prop or "$")
            missing_fields.append(target_path)
            errors.append({
                "path": target_path,
                "field": missing_prop,
                "error_type": "required_property_missing",
                "message": f"Missing required property '{missing_prop}' at path '{path_str}'",
                "schema_path": schema_path_str,
                "expected": f"property '{missing_prop}' present",
                "actual": "absent"
            })

        # 2. Data Type Mismatch
        elif validator_name == "type":
            actual_type = type(err.instance).__name__
            expected_type = err.validator_value
            type_mismatches.append({
                "path": path_str,
                "expected": expected_type,
                "actual": actual_type,
                "value": err.instance
            })
            errors.append({
                "path": path_str,
                "field": field_name,
                "error_type": "type_mismatch",
                "message": f"Type mismatch at '{path_str}': Expected type {expected_type}, but received {actual_type} ({repr(err.instance)})",
                "schema_path": schema_path_str,
                "expected": expected_type,
                "actual": actual_type
            })

        # 3. Enum Constraints
        elif validator_name == "enum":
            errors.append({
                "path": path_str,
                "field": field_name,
                "error_type": "enum_constraint_violation",
                "message": f"Invalid enum value at '{path_str}': '{err.instance}' is not one of {err.validator_value}",
                "schema_path": schema_path_str,
                "expected": err.validator_value,
                "actual": err.instance
            })

        # 4. Numeric Range (minimum, maximum, etc.)
        elif validator_name in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"):
            errors.append({
                "path": path_str,
                "field": field_name,
                "error_type": f"range_{validator_name}_violation",
                "message": f"Numeric constraint violated at '{path_str}': {err.message}",
                "schema_path": schema_path_str,
                "expected": f"{validator_name} {err.validator_value}",
                "actual": err.instance
            })

        # 5. String / Array Length Constraints
        elif validator_name in ("minLength", "maxLength", "minItems", "maxItems"):
            actual_len = len(err.instance) if hasattr(err.instance, "__len__") else err.instance
            errors.append({
                "path": path_str,
                "field": field_name,
                "error_type": f"length_{validator_name}_violation",
                "message": f"Length constraint violated at '{path_str}': {err.message} (actual length: {actual_len})",
                "schema_path": schema_path_str,
                "expected": f"{validator_name} {err.validator_value}",
                "actual": actual_len
            })

        # 6. Regex Pattern Matching
        elif validator_name == "pattern":
            errors.append({
                "path": path_str,
                "field": field_name,
                "error_type": "pattern_mismatch",
                "message": f"Pattern mismatch at '{path_str}': Value '{err.instance}' does not match pattern '{err.validator_value}'",
                "schema_path": schema_path_str,
                "expected": err.validator_value,
                "actual": err.instance
            })

        # 7. Additional Forbidden Properties
        elif validator_name == "additionalProperties":
            errors.append({
                "path": path_str,
                "field": field_name,
                "error_type": "additional_property_forbidden",
                "message": f"Forbidden additional property at '{path_str}': {err.message}",
                "schema_path": schema_path_str,
                "expected": "no additional properties",
                "actual": err.message
            })

        # 8. General / Fallback Errors
        else:
            errors.append({
                "path": path_str,
                "field": field_name,
                "error_type": f"schema_{validator_name}_error",
                "message": f"Schema validation error at '{path_str}': {err.message}",
                "schema_path": schema_path_str,
                "expected": str(err.validator_value),
                "actual": repr(err.instance)
            })

    total_errs = len(errors)
    is_valid = (total_errs == 0)

    # Build human-readable summary
    if is_valid:
        summary = "JSON payload matches schema definition perfectly with 0 violations."
    else:
        err_snippets = []
        if missing_fields:
            err_snippets.append(f"Missing required field(s): {', '.join(missing_fields)}")
        if type_mismatches:
            types_str = "; ".join([f"{m['path']} expected {m['expected']} got {m['actual']}" for m in type_mismatches])
            err_snippets.append(f"Type mismatch(es): {types_str}")
        other_count = total_errs - len(missing_fields) - len(type_mismatches)
        if other_count > 0:
            err_snippets.append(f"{other_count} other constraint violation(s)")

        summary = f"JSON Schema validation failed ({total_errs} error{'s' if total_errs > 1 else ''}): " + " | ".join(err_snippets)

    stats = {
        "total_errors": total_errs,
        "missing_fields": missing_fields,
        "type_mismatches": type_mismatches,
        "summary": summary
    }

    return is_valid, errors, stats
