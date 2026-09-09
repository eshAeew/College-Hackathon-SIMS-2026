"""Assertion evaluation engine for validating HTTP responses against structured test case expectations."""
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

from app.models.schemas.test_case import (
    AssertionRuleResult,
    BodyFieldAssertionRule,
    ComparisonOperator,
    HeaderAssertionRule,
    TestCaseAssertionReport,
    TestCaseAssertions,
)
from app.utils.protocol_validator import validate_content_type, validate_status_code
from app.utils.schema_validator import validate_json_schema_instance


def extract_field_value(data: Any, path: str) -> Tuple[bool, Any]:
    """
    Extract a nested field value using dot-bracket notation.
    """
    if data is None or not path:
        return False, None

    normalized_path = re.sub(r'\[(\d+)\]', r'.\1', path.strip())
    if normalized_path.startswith('.'):
        normalized_path = normalized_path[1:]

    tokens = normalized_path.split('.')
    current = data

    for token in tokens:
        if current is None:
            return False, None

        if isinstance(current, dict):
            if token in current:
                current = current[token]
            else:
                return False, None
        elif isinstance(current, (list, tuple)):
            try:
                index = int(token)
                if 0 <= index < len(current):
                    current = current[index]
                else:
                    return False, None
            except ValueError:
                return False, None
        else:
            return False, None

    return True, current


def evaluate_operator(operator: Union[ComparisonOperator, str], actual: Any, expected: Any) -> Tuple[bool, str]:
    """
    Evaluate a comparison operator between actual observed value and expected value.
    """
    op_str = operator.value if isinstance(operator, ComparisonOperator) else str(operator).lower()

    # Null existence checks
    if op_str == ComparisonOperator.EXISTS.value:
        passed = actual is not None
        msg = f"Field exists (value={actual!r})" if passed else "Field does not exist or is None"
        return passed, msg

    if op_str == ComparisonOperator.NOT_EXISTS.value:
        passed = actual is None
        msg = "Field does not exist as expected" if passed else f"Field exists unexpectedly (value={actual!r})"
        return passed, msg

    # Empty / Non-empty checks
    if op_str == ComparisonOperator.IS_EMPTY.value:
        if actual is None:
            return True, "Field is empty (None)"
        if isinstance(actual, (str, list, dict, set, tuple)):
            passed = len(actual) == 0
            msg = "Field is empty" if passed else f"Field is not empty (length={len(actual)})"
            return passed, msg
        return False, f"Cannot check is_empty on non-collection type: {type(actual).__name__}"

    if op_str == ComparisonOperator.IS_NOT_EMPTY.value:
        if actual is None:
            return False, "Field is empty (None)"
        if isinstance(actual, (str, list, dict, set, tuple)):
            passed = len(actual) > 0
            msg = f"Field is not empty (length={len(actual)})" if passed else "Field is empty"
            return passed, msg
        return True, f"Field is non-empty scalar value: {actual!r}"

    # Type matching
    if op_str == ComparisonOperator.TYPE_MATCH.value:
        expected_type_name = str(expected).lower().strip()
        type_mapping = {
            'str': str, 'string': str, 'text': str,
            'int': int, 'integer': int,
            'float': (int, float), 'number': (int, float), 'numeric': (int, float),
            'bool': bool, 'boolean': bool,
            'list': list, 'array': list,
            'dict': dict, 'object': dict,
            'null': type(None), 'none': type(None)
        }
        target_py_type = type_mapping.get(expected_type_name)
        if target_py_type is None:
            return False, f"Unknown type specification '{expected}'"
        
        if expected_type_name in ('int', 'integer'):
            passed = isinstance(actual, int) and not isinstance(actual, bool)
        elif expected_type_name in ('float', 'number', 'numeric'):
            passed = (isinstance(actual, (int, float))) and not isinstance(actual, bool)
        else:
            passed = isinstance(actual, target_py_type)

        msg = f"Type is '{type(actual).__name__}' matching expected '{expected}'" if passed else f"Type mismatch: expected '{expected}', got '{type(actual).__name__}'"
        return passed, msg

    # Regular Expression matching
    if op_str == ComparisonOperator.REGEX_MATCH.value:
        if expected is None:
            return False, "Expected regex pattern cannot be None"
        try:
            passed = bool(re.search(str(expected), str(actual)))
            msg = f"Value '{actual}' matches pattern '{expected}'" if passed else f"Value '{actual}' failed to match regex pattern '{expected}'"
            return passed, msg
        except re.error as e:
            return False, f"Invalid regex pattern '{expected}': {e}"

    # Equality & Non-equality
    if op_str == ComparisonOperator.EQUALS.value:
        passed = actual == expected
        msg = f"Value equals {expected!r}" if passed else f"Expected {expected!r}, but got {actual!r}"
        return passed, msg

    if op_str == ComparisonOperator.NOT_EQUALS.value:
        passed = actual != expected
        msg = f"Value differs from {expected!r}" if passed else f"Expected value not to equal {expected!r}"
        return passed, msg

    # Contains & Not-Contains
    if op_str == ComparisonOperator.CONTAINS.value:
        if actual is None:
            return False, "Cannot evaluate 'contains' on None"
        if isinstance(actual, (str, list, dict, tuple, set)):
            passed = expected in actual if not isinstance(actual, str) else str(expected) in actual
            msg = f"Container contains {expected!r}" if passed else f"Expected {expected!r} to be inside {actual!r}"
            return passed, msg
        return False, f"Cannot evaluate 'contains' on type {type(actual).__name__}"

    if op_str == ComparisonOperator.NOT_CONTAINS.value:
        if actual is None:
            return True, "None does not contain value"
        if isinstance(actual, (str, list, dict, tuple, set)):
            passed = expected not in actual if not isinstance(actual, str) else str(expected) not in actual
            msg = f"Container does not contain {expected!r}" if passed else f"Expected {expected!r} NOT to be inside {actual!r}"
            return passed, msg
        return True, "Non-container does not contain value"

    # Numeric & Relational Comparisons
    if op_str in (
        ComparisonOperator.GREATER_THAN.value,
        ComparisonOperator.LESS_THAN.value,
        ComparisonOperator.GREATER_EQUAL.value,
        ComparisonOperator.LESS_EQUAL.value,
    ):
        try:
            num_actual = float(actual)
            num_expected = float(expected)
            if op_str == ComparisonOperator.GREATER_THAN.value:
                passed = num_actual > num_expected
                sym = '>'
            elif op_str == ComparisonOperator.LESS_THAN.value:
                passed = num_actual < num_expected
                sym = '<'
            elif op_str == ComparisonOperator.GREATER_EQUAL.value:
                passed = num_actual >= num_expected
                sym = '>='
            else:
                passed = num_actual <= num_expected
                sym = '<='

            msg = f"Passed: {num_actual} {sym} {num_expected}" if passed else f"Failed: actual {num_actual} is not {sym} {num_expected}"
            return passed, msg
        except (ValueError, TypeError):
            return False, f"Relational comparison '{op_str}' failed: incompatible types (actual={actual!r}, expected={expected!r})"

    return False, f"Unsupported comparison operator '{operator}'"


def evaluate_assertions(
    assertions: Union[TestCaseAssertions, Dict[str, Any]],
    status_code: Optional[int],
    latency_ms: float,
    headers: Dict[str, str],
    body: Optional[Any],
    content_type: Optional[str] = None,
    test_case_id: Optional[int] = None,
    test_case_name: Optional[str] = None,
) -> TestCaseAssertionReport:
    """
    Evaluate all configured assertion rules against HTTP execution telemetry.
    """
    if isinstance(assertions, dict):
        assertions = TestCaseAssertions(**assertions)

    results: List[AssertionRuleResult] = []

    # 1. Status Code Assertion
    if assertions.expected_status is not None:
        if status_code is None:
            results.append(
                AssertionRuleResult(
                    rule_type="STATUS_CODE",
                    target="HTTP Status",
                    operator="match",
                    expected=assertions.expected_status,
                    actual=None,
                    passed=False,
                    message="No HTTP status code received (network error or timeout).",
                )
            )
        else:
            status_passed, status_msg = validate_status_code(status_code, assertions.expected_status)
            results.append(
                AssertionRuleResult(
                    rule_type="STATUS_CODE",
                    target="HTTP Status",
                    operator="match",
                    expected=assertions.expected_status,
                    actual=status_code,
                    passed=status_passed,
                    message=status_msg,
                )
            )

    # 2. Maximum Latency Threshold
    if assertions.max_latency_ms is not None:
        passed = latency_ms <= assertions.max_latency_ms
        msg = (
            f"Latency {latency_ms:.2f}ms within threshold <= {assertions.max_latency_ms}ms."
            if passed
            else f"Latency {latency_ms:.2f}ms exceeded maximum threshold {assertions.max_latency_ms}ms (breach: +{latency_ms - assertions.max_latency_ms:.2f}ms)."
        )
        results.append(
            AssertionRuleResult(
                rule_type="LATENCY_THRESHOLD",
                target="Response Latency",
                operator="less_equal",
                expected=assertions.max_latency_ms,
                actual=latency_ms,
                passed=passed,
                message=msg,
            )
        )

    # 3. Content-Type Assertion
    if assertions.expected_content_type:
        actual_ct = content_type or headers.get("content-type") or headers.get("Content-Type")
        ct_passed, ct_msg = validate_content_type(actual_ct, assertions.expected_content_type)
        results.append(
            AssertionRuleResult(
                rule_type="CONTENT_TYPE",
                target="Header: Content-Type",
                operator="match",
                expected=assertions.expected_content_type,
                actual=actual_ct,
                passed=ct_passed,
                message=ct_msg,
            )
        )

    # 4. Header Assertions
    if assertions.headers:
        normalized_headers = {k.lower(): v for k, v in headers.items()}
        for rule in assertions.headers:
            header_key = rule.name.lower().strip()
            actual_header_val = normalized_headers.get(header_key)

            passed, msg = evaluate_operator(
                rule.operator,
                actual_header_val,
                rule.expected_value,
            )
            results.append(
                AssertionRuleResult(
                    rule_type="HEADER",
                    target=f"Header '{rule.name}'",
                    operator=rule.operator.value if isinstance(rule.operator, ComparisonOperator) else str(rule.operator),
                    expected=rule.expected_value,
                    actual=actual_header_val,
                    passed=passed,
                    message=msg,
                )
            )

    # 5. JSON Body Field Assertions
    if assertions.body_fields:
        for field_rule in assertions.body_fields:
            found, actual_val = extract_field_value(body, field_rule.path)
            op_val = field_rule.operator.value if isinstance(field_rule.operator, ComparisonOperator) else str(field_rule.operator)
            
            if op_val == ComparisonOperator.NOT_EXISTS.value:
                passed = not found or actual_val is None
                msg = f"Field '{field_rule.path}' does not exist as expected." if passed else f"Field '{field_rule.path}' exists unexpectedly (value={actual_val!r})."
            elif op_val == ComparisonOperator.EXISTS.value:
                passed = found and actual_val is not None
                msg = f"Field '{field_rule.path}' exists (value={actual_val!r})." if passed else f"Field '{field_rule.path}' was not found in response body."
            else:
                if not found:
                    passed = False
                    msg = f"Field '{field_rule.path}' was not found in response payload."
                else:
                    passed, msg = evaluate_operator(field_rule.operator, actual_val, field_rule.expected_value)

            if field_rule.description:
                msg = f"[{field_rule.description}] {msg}"

            results.append(
                AssertionRuleResult(
                    rule_type="BODY_FIELD",
                    target=f"Field '{field_rule.path}'",
                    operator=op_val,
                    expected=field_rule.expected_value,
                    actual=actual_val if found else None,
                    passed=passed,
                    message=msg,
                )
            )

    # 6. JSON Schema Draft-7 Validation
    schema_to_val = assertions.json_schema
    if schema_to_val:
        if body is None:
            results.append(
                AssertionRuleResult(
                    rule_type="JSON_SCHEMA",
                    target="Response Body Schema",
                    operator="schema_validate",
                    expected=schema_to_val,
                    actual=None,
                    passed=False,
                    message="Cannot validate JSON schema against empty/null response body.",
                )
            )
        else:
            is_valid, err_list, stats = validate_json_schema_instance(body, schema_to_val)
            results.append(
                AssertionRuleResult(
                    rule_type="JSON_SCHEMA",
                    target="Response Body Schema",
                    operator="schema_validate",
                    expected=schema_to_val,
                    actual=f"Validated payload with {len(err_list)} violations",
                    passed=is_valid,
                    message=stats.get("summary", "JSON Schema evaluated."),
                )
            )

    total_rules = len(results)
    passed_rules = sum(1 for r in results if r.passed)
    failed_rules = total_rules - passed_rules
    all_passed = total_rules > 0 and failed_rules == 0

    return TestCaseAssertionReport(
        test_case_id=test_case_id,
        test_case_name=test_case_name,
        all_passed=all_passed,
        total_rules=total_rules,
        passed_rules=passed_rules,
        failed_rules=failed_rules,
        results=results,
        evaluated_at=datetime.now(timezone.utc),
    )