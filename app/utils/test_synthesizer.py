"""Synthesizer engine for automatic positive and negative test case generation (Stage 15)."""
import copy
import json
import logging
from typing import Any, Dict, List, Optional

from app.models.schemas.request_config import BodyType
from app.models.schemas.test_case import TestCaseSeverity
from app.models.schemas.test_generation import (
    GeneratedTestCategory,
    StagedTestCase,
    TestGenerationOptions,
    TestGenerationStrategy,
)
from app.utils.contract_parser import extract_path_variables

logger = logging.getLogger("app.utils.test_synthesizer")


def generate_mock_value_for_schema(schema: Dict[str, Any], field_name: str = "") -> Any:
    """
    Synthesize a valid mock value compliant with a given JSON Schema property descriptor.
    """
    if not isinstance(schema, dict):
        return "sample_value"

    # 1. Check explicit examples or defaults
    if "example" in schema:
        return schema["example"]
    if "default" in schema:
        return schema["default"]
    if "examples" in schema and isinstance(schema["examples"], list) and schema["examples"]:
        return schema["examples"][0]

    # 2. Check Enum
    if "enum" in schema and isinstance(schema["enum"], list) and schema["enum"]:
        return schema["enum"][0]

    schema_type = schema.get("type", "string")

    # 3. Handle Types
    if schema_type == "string":
        fmt = schema.get("format", "").lower()
        fn_lower = field_name.lower()
        if fmt == "email" or "email" in fn_lower:
            return f"user.{field_name or 'test'}@example.com"
        elif fmt == "uuid" or "uuid" in fn_lower or "id" == fn_lower:
            return "123e4567-e89b-12d3-a456-426614174000"
        elif fmt in ("date-time", "datetime"):
            return "2026-09-09T12:00:00Z"
        elif fmt == "date":
            return "2026-09-09"
        elif fmt in ("uri", "url") or "url" in fn_lower:
            return "https://api.example.com/resource"
        elif fmt == "ipv4":
            return "192.168.1.1"
        elif "password" in fn_lower:
            return "P@ssword123!"
        elif "phone" in fn_lower or "mobile" in fn_lower:
            return "+1-555-0199"
        elif "name" in fn_lower:
            return f"Sample {field_name.capitalize()}"
        
        # Check string length bounds
        min_len = schema.get("minLength", 1)
        base_str = f"test_{field_name}" if field_name else "test_str"
        if len(base_str) < min_len:
            base_str = base_str + ("a" * (min_len - len(base_str)))
        return base_str

    elif schema_type in ("integer", "number"):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if minimum is not None:
            val = minimum if schema_type == "integer" else float(minimum)
        elif maximum is not None:
            val = maximum if schema_type == "integer" else float(maximum)
        else:
            val = 42 if "id" in field_name.lower() or "count" in field_name.lower() else 1
            if schema_type == "number":
                val = float(val) + 0.5
        return val

    elif schema_type == "boolean":
        return True

    elif schema_type == "array":
        items_schema = schema.get("items", {})
        item_val = generate_mock_value_for_schema(items_schema, field_name=f"{field_name}_item")
        min_items = schema.get("minItems", 1)
        return [item_val] * max(min_items, 1)

    elif schema_type == "object":
        properties = schema.get("properties", {})
        obj = {}
        for prop_name, prop_schema in properties.items():
            obj[prop_name] = generate_mock_value_for_schema(prop_schema, field_name=prop_name)
        return obj

    return "sample_value"


def synthesize_happy_path_payload(schema: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Generate a fully populated valid JSON mock object conforming to the schema."""
    if not schema or not isinstance(schema, dict):
        return None
    return generate_mock_value_for_schema(schema)


def synthesize_mock_path_params(
    path: str,
    existing_params: Optional[Dict[str, Any]] = None,
    custom_overrides: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Generate mock concrete path parameters matching all {placeholder} in path."""
    extracted = extract_path_variables(path)
    res = {}
    existing = existing_params or {}
    overrides = custom_overrides or {}

    for var in extracted:
        if var in overrides:
            res[var] = overrides[var]
        elif var in existing:
            res[var] = existing[var]
        else:
            var_lower = var.lower()
            if "id" in var_lower:
                res[var] = 1 if "num" in var_lower else "101"
            elif "slug" in var_lower or "name" in var_lower:
                res[var] = f"sample-{var}"
            else:
                res[var] = f"val_{var}"
    return res


def synthesize_mock_query_params(
    query_params_dict: Optional[Dict[str, Any]] = None,
    custom_overrides: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Generate mock query parameters."""
    res = {}
    existing = query_params_dict or {}
    overrides = custom_overrides or {}

    for k, v in existing.items():
        if isinstance(v, dict):
            res[k] = generate_mock_value_for_schema(v, field_name=k)
        else:
            res[k] = v

    for k, v in overrides.items():
        res[k] = v

    return res


def generate_test_suite_for_endpoint(
    method: str,
    path: str,
    headers: Optional[Dict[str, str]] = None,
    query_params: Optional[Dict[str, Any]] = None,
    path_params: Optional[Dict[str, Any]] = None,
    body_schema: Optional[Dict[str, Any]] = None,
    expected_status: Optional[int] = None,
    options: Optional[TestGenerationOptions] = None
) -> List[StagedTestCase]:
    """
    Main generator synthesizing positive and negative staged test cases for an endpoint contract.
    """
    opt = options or TestGenerationOptions()
    method_upper = method.upper()
    target_strategies = set(opt.strategies)
    allow_all = TestGenerationStrategy.ALL in target_strategies

    staged: List[StagedTestCase] = []
    idx = 1

    # Base request parts
    base_headers = {"Content-Type": "application/json"}
    if headers:
        base_headers.update(headers)
    if opt.default_headers:
        base_headers.update(opt.default_headers)

    valid_path_params = synthesize_mock_path_params(
        path,
        existing_params=path_params,
        custom_overrides=opt.custom_path_params
    )
    valid_query_params = synthesize_mock_query_params(
        query_params_dict=query_params,
        custom_overrides=opt.custom_query_params
    )
    valid_body = synthesize_happy_path_payload(body_schema)

    # Determine default success status code
    if expected_status:
        happy_status = expected_status
    elif method_upper == "POST":
        happy_status = 201
    elif method_upper == "DELETE":
        happy_status = 204
    else:
        happy_status = 200

    has_body = method_upper in ("POST", "PUT", "PATCH") and (body_schema or valid_body)
    body_type = BodyType.JSON if has_body else BodyType.EMPTY

    # -------------------------------------------------------------
    # 1. POSITIVE: Happy Path
    # -------------------------------------------------------------
    if opt.include_positive and (allow_all or TestGenerationStrategy.HAPPY_PATH in target_strategies):
        staged.append(
            StagedTestCase(
                temporary_id=f"STG-{idx:03d}",
                name=f"Positive - {method_upper} {path} Standard Success",
                description=f"Happy path execution verifying {method_upper} {path} returns {happy_status} OK with valid inputs.",
                category=GeneratedTestCategory.POSITIVE,
                strategy=TestGenerationStrategy.HAPPY_PATH,
                severity=TestCaseSeverity.HIGH,
                tags=["auto-generated", "positive", "happy-path", "smoke"],
                path_params=copy.deepcopy(valid_path_params),
                query_params=copy.deepcopy(valid_query_params),
                headers=copy.deepcopy(base_headers),
                body_type=body_type,
                body=copy.deepcopy(valid_body) if has_body else None,
                expected_status=happy_status,
                assertions={
                    "expected_status": happy_status,
                    "max_latency_ms": 3000.0,
                    "expected_content_type": "application/json" if happy_status != 204 else None
                },
                is_selected=True
            )
        )
        idx += 1

    # -------------------------------------------------------------
    # 2. NEGATIVE: Missing Required Fields
    # -------------------------------------------------------------
    if opt.include_negative and (allow_all or TestGenerationStrategy.MISSING_REQUIRED in target_strategies):
        if has_body and isinstance(valid_body, dict) and isinstance(body_schema, dict):
            required_fields = body_schema.get("required", [])
            # If no explicit 'required', test removing top-level keys
            fields_to_test = required_fields if required_fields else list(valid_body.keys())[:3]

            for field in fields_to_test:
                if len(staged) >= opt.max_tests_per_endpoint:
                    break
                if field in valid_body:
                    mutated_body = copy.deepcopy(valid_body)
                    del mutated_body[field]

                    staged.append(
                        StagedTestCase(
                            temporary_id=f"STG-{idx:03d}",
                            name=f"Negative - Missing Required Field '{field}'",
                            description=f"Verify request without required field '{field}' is rejected with 400/422 Unprocessable Entity.",
                            category=GeneratedTestCategory.NEGATIVE,
                            strategy=TestGenerationStrategy.MISSING_REQUIRED,
                            severity=TestCaseSeverity.MEDIUM,
                            tags=["auto-generated", "negative", "validation", "missing-field"],
                            path_params=copy.deepcopy(valid_path_params),
                            query_params=copy.deepcopy(valid_query_params),
                            headers=copy.deepcopy(base_headers),
                            body_type=body_type,
                            body=mutated_body,
                            expected_status=400,
                            assertions={
                                "expected_status": [400, 422]
                            },
                            is_selected=True
                        )
                    )
                    idx += 1

        # Missing / Empty Path Param Test
        if valid_path_params and len(staged) < opt.max_tests_per_endpoint:
            for p_var in list(valid_path_params.keys())[:1]:
                bad_path_params = copy.deepcopy(valid_path_params)
                bad_path_params[p_var] = "non-existent-id-999999"
                staged.append(
                    StagedTestCase(
                        temporary_id=f"STG-{idx:03d}",
                        name=f"Negative - Invalid Resource ID '{p_var}'",
                        description=f"Verify request with non-existent path parameter '{p_var}' returns 404 Not Found.",
                        category=GeneratedTestCategory.NEGATIVE,
                        strategy=TestGenerationStrategy.MISSING_REQUIRED,
                        severity=TestCaseSeverity.MEDIUM,
                        tags=["auto-generated", "negative", "not-found"],
                        path_params=bad_path_params,
                        query_params=copy.deepcopy(valid_query_params),
                        headers=copy.deepcopy(base_headers),
                        body_type=body_type,
                        body=copy.deepcopy(valid_body) if has_body else None,
                        expected_status=404,
                        assertions={
                            "expected_status": 404
                        },
                        is_selected=True
                    )
                )
                idx += 1

    # -------------------------------------------------------------
    # 3. NEGATIVE: Invalid Data Types
    # -------------------------------------------------------------
    if opt.include_negative and (allow_all or TestGenerationStrategy.INVALID_TYPE in target_strategies):
        if has_body and isinstance(valid_body, dict) and isinstance(body_schema, dict):
            properties = body_schema.get("properties", {})
            for field, val in valid_body.items():
                if len(staged) >= opt.max_tests_per_endpoint:
                    break
                # Invert type
                if isinstance(val, int) and not isinstance(val, bool):
                    inverted_val = "not_an_integer_string"
                elif isinstance(val, float):
                    inverted_val = "not_a_float_string"
                elif isinstance(val, bool):
                    inverted_val = 12345
                elif isinstance(val, str):
                    inverted_val = {"nested": "object_instead_of_string"}
                elif isinstance(val, list):
                    inverted_val = "string_instead_of_array"
                elif isinstance(val, dict):
                    inverted_val = ["array", "instead", "of", "dict"]
                else:
                    inverted_val = True

                mutated_body = copy.deepcopy(valid_body)
                mutated_body[field] = inverted_val

                staged.append(
                    StagedTestCase(
                        temporary_id=f"STG-{idx:03d}",
                        name=f"Negative - Invalid Data Type on '{field}'",
                        description=f"Verify request with type mismatch on '{field}' ({type(val).__name__} -> {type(inverted_val).__name__}) triggers 400/422 validation error.",
                        category=GeneratedTestCategory.NEGATIVE,
                        strategy=TestGenerationStrategy.INVALID_TYPE,
                        severity=TestCaseSeverity.MEDIUM,
                        tags=["auto-generated", "negative", "type-inversion", "schema-validation"],
                        path_params=copy.deepcopy(valid_path_params),
                        query_params=copy.deepcopy(valid_query_params),
                        headers=copy.deepcopy(base_headers),
                        body_type=body_type,
                        body=mutated_body,
                        expected_status=400,
                        assertions={
                            "expected_status": [400, 422]
                        },
                        is_selected=True
                    )
                )
                idx += 1

    # -------------------------------------------------------------
    # 4. BOUNDARY: Extreme & Overflow Values
    # -------------------------------------------------------------
    if opt.include_negative and (allow_all or TestGenerationStrategy.BOUNDARY_VALUE in target_strategies):
        if has_body and isinstance(valid_body, dict):
            for field, val in valid_body.items():
                if len(staged) >= opt.max_tests_per_endpoint:
                    break
                boundary_val = None
                boundary_desc = ""
                if isinstance(val, str):
                    boundary_val = ""
                    boundary_desc = f"Empty string boundary test for '{field}'"
                elif isinstance(val, int) and not isinstance(val, bool):
                    boundary_val = -999999 if val >= 0 else 9999999999
                    boundary_desc = f"Negative/overflow integer boundary test for '{field}'"

                if boundary_val is not None:
                    mutated_body = copy.deepcopy(valid_body)
                    mutated_body[field] = boundary_val

                    staged.append(
                        StagedTestCase(
                            temporary_id=f"STG-{idx:03d}",
                            name=f"Boundary - Edge Value on '{field}'",
                            description=boundary_desc,
                            category=GeneratedTestCategory.BOUNDARY,
                            strategy=TestGenerationStrategy.BOUNDARY_VALUE,
                            severity=TestCaseSeverity.LOW,
                            tags=["auto-generated", "boundary", "edge-case"],
                            path_params=copy.deepcopy(valid_path_params),
                            query_params=copy.deepcopy(valid_query_params),
                            headers=copy.deepcopy(base_headers),
                            body_type=body_type,
                            body=mutated_body,
                            expected_status=400,
                            assertions={
                                "expected_status": [400, 422, happy_status]
                            },
                            is_selected=True
                        )
                    )
                    idx += 1

    # -------------------------------------------------------------
    # 5. SECURITY / NEGATIVE: Null Injections
    # -------------------------------------------------------------
    if opt.include_negative and (allow_all or TestGenerationStrategy.NULL_INJECTION in target_strategies):
        if has_body and isinstance(valid_body, dict):
            for field in list(valid_body.keys())[:2]:
                if len(staged) >= opt.max_tests_per_endpoint:
                    break
                mutated_body = copy.deepcopy(valid_body)
                mutated_body[field] = None

                staged.append(
                    StagedTestCase(
                        temporary_id=f"STG-{idx:03d}",
                        name=f"Negative - Null Injection for '{field}'",
                        description=f"Verify injecting null into '{field}' does not trigger a 500 server crash and is gracefully rejected.",
                        category=GeneratedTestCategory.SECURITY,
                        strategy=TestGenerationStrategy.NULL_INJECTION,
                        severity=TestCaseSeverity.HIGH,
                        tags=["auto-generated", "negative", "null-injection", "security"],
                        path_params=copy.deepcopy(valid_path_params),
                        query_params=copy.deepcopy(valid_query_params),
                        headers=copy.deepcopy(base_headers),
                        body_type=body_type,
                        body=mutated_body,
                        expected_status=400,
                        assertions={
                            "expected_status": [400, 422]
                        },
                        is_selected=True
                    )
                )
                idx += 1

    # Cap to max_tests_per_endpoint
    return staged[:opt.max_tests_per_endpoint]
