"""Adversarial & Negative Test Response Classifier.

Heuristic classification engine distinguishing proper client rejection from unhandled server crashes:
- 4xx (400, 422, 401, 403, 404) -> PROPERLY_HANDLED_4XX (PASS)
- 5xx (500, 502, 503, 504) -> UNHANDLED_SERVER_EXCEPTION_5XX (CRITICAL DEFECT)
- 2xx (200, 201, 204) -> UNVALIDATED_ACCEPTANCE_2XX (HIGH DEFECT)
"""
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("app.utils.adversarial_classifier")


def classify_negative_response(
    status_code: int,
    response_body: Optional[Any] = None,
    mutation_info: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Evaluate response from an intentionally invalid/adversarial request.
    
    Returns structured diagnostic dict:
    - passed: bool
    - classification: str
    - severity: str ('NONE', 'CRITICAL', 'HIGH', 'MEDIUM')
    - verdict: str ('PASS', 'FAIL_CRITICAL', 'FAIL_HIGH', 'WARN')
    - message: str
    - defect_type: Optional[str]
    - recommendation: Optional[str]
    """
    target_field = mutation_info.get("target_field", "unknown") if mutation_info else "input_payload"
    strategy = mutation_info.get("strategy", "adversarial_mutation") if mutation_info else "negative_test"

    # Case 1: 4xx Client Error (Proper Rejection)
    if 400 <= status_code < 500:
        return {
            "passed": True,
            "status_code": status_code,
            "classification": "PROPERLY_HANDLED_4XX",
            "severity": "NONE",
            "verdict": "PASS",
            "message": f"Server correctly rejected adversarial input for '{target_field}' with HTTP {status_code}.",
            "defect_type": None,
            "recommendation": None
        }

    # Case 2: 5xx Server Error (Unhandled Exception / Crash Vulnerability)
    if 500 <= status_code < 600:
        return {
            "passed": False,
            "status_code": status_code,
            "classification": "UNHANDLED_SERVER_EXCEPTION_5XX",
            "severity": "CRITICAL",
            "verdict": "FAIL_CRITICAL",
            "message": f"CRITICAL VULNERABILITY: Adversarial input on '{target_field}' ({strategy}) crashed the server with HTTP {status_code}.",
            "defect_type": "Unhandled Server Exception / Missing Validation",
            "recommendation": (
                f"Implement pre-handler schema and type validation on '{target_field}' to ensure "
                f"invalid input is rejected with HTTP 400 Bad Request or HTTP 422 Unprocessable Entity "
                f"instead of crashing the backend with HTTP {status_code}."
            )
        }

    # Case 3: 2xx Success (Silent Acceptance of Corrupted / Invalid Input)
    if 200 <= status_code < 300:
        return {
            "passed": False,
            "status_code": status_code,
            "classification": "UNVALIDATED_ACCEPTANCE_2XX",
            "severity": "HIGH",
            "verdict": "FAIL_HIGH",
            "message": f"HIGH VULNERABILITY: Corrupted adversarial input on '{target_field}' ({strategy}) was accepted with HTTP {status_code} without validation.",
            "defect_type": "Missing Input Validation / Silent Data Corruption Risk",
            "recommendation": (
                f"Enforce mandatory validation checks on '{target_field}'. "
                f"The server must reject corrupted or out-of-boundary payloads with HTTP 400/422."
            )
        }

    # Case 4: Other unexpected status code (3xx or out-of-range)
    return {
        "passed": False,
        "status_code": status_code,
        "classification": "OTHER_STATUS",
        "severity": "MEDIUM",
        "verdict": "WARN",
        "message": f"Unexpected HTTP status {status_code} received for adversarial input on '{target_field}'.",
        "defect_type": "Unexpected Status Code",
        "recommendation": "Review endpoint routing, middleware, and redirection logic for invalid client requests."
    }
