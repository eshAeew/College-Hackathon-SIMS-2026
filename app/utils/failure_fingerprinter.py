"""Fingerprinting and pattern clustering engine for recurring API failures."""
import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.models.schemas.recurring_failure import (
    FailureCategory,
    FailureCluster,
    HistoricalExecutionSample,
    PersistenceRating,
)


def normalize_error_message(msg: Optional[str]) -> str:
    """
    Normalize raw error strings by stripping variable parameters, timestamps,
    hex memory addresses, and UUIDs to produce stable deterministic signatures.
    """
    if not msg or not isinstance(msg, str):
        return "Unknown error trace"

    cleaned = msg.strip()

    # Strip ISO timestamps: 2026-09-09T18:30:00.000Z
    cleaned = re.sub(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})?', '<TIMESTAMP>', cleaned)
    
    # Strip UUIDs: e.g. 123e4567-e89b-12d3-a456-426614174000
    cleaned = re.sub(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}', '<UUID>', cleaned)

    # Strip Hex memory pointers: e.g. 0x7ffd5a89b4c0
    cleaned = re.sub(r'0x[0-9a-fA-F]+', '<HEX_ADDR>', cleaned)

    # Strip large numeric IDs: e.g. id=91823912
    cleaned = re.sub(r'\b\d{4,}\b', '<NUM_ID>', cleaned)

    # Collapse multiple whitespaces
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def categorize_failure(
    status_code: Optional[int],
    error_msg: Optional[str],
    assertion_failures: Optional[List[str]] = None
) -> FailureCategory:
    """Classify the root cause category of a test failure based on status code and error messages."""
    text_to_check = f"{error_msg or ''} {' '.join(assertion_failures or [])}".lower()

    if status_code in (408, 504) or "timeout" in text_to_check or "timed out" in text_to_check:
        return FailureCategory.TIMEOUT

    if "connecterror" in text_to_check or "connection refused" in text_to_check or "dns" in text_to_check:
        return FailureCategory.NETWORK_ERROR

    if status_code in (401, 403) or "unauthorized" in text_to_check or "forbidden" in text_to_check or "jwt" in text_to_check:
        return FailureCategory.AUTH_FAILURE

    if status_code == 500 or (status_code is not None and 500 <= status_code < 600):
        return FailureCategory.SERVER_CRASH

    if "schema" in text_to_check or "json schema" in text_to_check or "type mismatch" in text_to_check:
        return FailureCategory.SCHEMA_MISMATCH

    if status_code in (400, 422) or "validation" in text_to_check or "invalid parameter" in text_to_check:
        return FailureCategory.VALIDATION_ERROR

    if assertion_failures and len(assertion_failures) > 0:
        return FailureCategory.ASSERTION_FAILED

    return FailureCategory.UNKNOWN


def generate_failure_fingerprint(
    category: FailureCategory,
    status_code: Optional[int],
    normalized_msg: str
) -> Tuple[str, str]:
    """
    Generate a stable SHA-256 fingerprint hash and short human-readable Cluster ID.
    
    Returns:
        (cluster_id, fingerprint_hash)
    """
    raw_signature = f"{category.value}:{status_code}:{normalized_msg.lower()}"
    fp_hash = hashlib.sha256(raw_signature.encode("utf-8")).hexdigest()
    short_hash = fp_hash[:6]

    code_str = str(status_code) if status_code else "ERR"
    cluster_id = f"FC-{category.value[:8]}-{code_str}-{short_hash}"
    return cluster_id, fp_hash


def calculate_persistence_rating(
    history_pass_flags: List[bool]
) -> Tuple[PersistenceRating, int, float, bool]:
    """
    Calculate persistence classification, consecutive failure streak, failure rate, and flapping flag.
    
    Args:
        history_pass_flags: Chronological list of booleans (True = Pass, False = Fail)
        
    Returns:
        (rating: PersistenceRating, consecutive_failures: int, failure_rate_pct: float, is_flapping: bool)
    """
    if not history_pass_flags:
        return PersistenceRating.HEALTHY, 0, 0.0, False

    total = len(history_pass_flags)
    fails = sum(1 for p in history_pass_flags if not p)
    failure_rate_pct = round((fails / total * 100.0), 1)

    # 1. Compute consecutive failures from the latest executions backward
    consecutive_fails = 0
    for p in reversed(history_pass_flags):
        if not p:
            consecutive_fails += 1
        else:
            break

    # 2. Compute state transitions (flapping check)
    transitions = 0
    for i in range(1, total):
        if history_pass_flags[i] != history_pass_flags[i - 1]:
            transitions += 1

    is_flapping = transitions >= 2 and 0.0 < failure_rate_pct < 100.0

    # 3. Determine Persistence Rating
    latest_passed = history_pass_flags[-1] if total > 0 else True

    if fails == 0:
        rating = PersistenceRating.HEALTHY
    elif latest_passed and fails > 0:
        rating = PersistenceRating.RESOLVED
    elif consecutive_fails >= 3 or failure_rate_pct >= 70.0:
        rating = PersistenceRating.CHRONIC
    elif is_flapping or (0 < failure_rate_pct < 70.0 and total >= 3):
        rating = PersistenceRating.INTERMITTENT
    else:
        rating = PersistenceRating.NEW

    return rating, consecutive_fails, failure_rate_pct, is_flapping


def cluster_failure_samples(samples: List[HistoricalExecutionSample]) -> List[FailureCluster]:
    """
    Group failed execution samples into clusters sharing identical normalized root-cause fingerprints.
    """
    failed_samples = [s for s in samples if not s.passed]
    if not failed_samples:
        return []

    clusters_map: Dict[str, Dict[str, Any]] = {}

    for sample in failed_samples:
        norm_msg = normalize_error_message(sample.error_message or " ".join(sample.assertion_failures))
        category = categorize_failure(sample.status_code, sample.error_message, sample.assertion_failures)
        cluster_id, fp_hash = generate_failure_fingerprint(category, sample.status_code, norm_msg)

        if fp_hash not in clusters_map:
            # Generate descriptive titles and suggestions based on category
            title_map = {
                FailureCategory.SERVER_CRASH: f"Unhandled Server Exception ({sample.status_code or 500})",
                FailureCategory.AUTH_FAILURE: f"Authentication / Authorization Failure ({sample.status_code or 401})",
                FailureCategory.VALIDATION_ERROR: f"Request Payload Validation Rejection ({sample.status_code or 400})",
                FailureCategory.TIMEOUT: f"Gateway or Service Timeout Breach ({sample.status_code or 504})",
                FailureCategory.SCHEMA_MISMATCH: "Response Schema / Field Contract Violation",
                FailureCategory.ASSERTION_FAILED: "Assertion Expectation Rule Failure",
                FailureCategory.NETWORK_ERROR: "Network Connection / DNS Resolution Error",
                FailureCategory.UNKNOWN: "Uncategorized Failure Pattern",
            }
            suggestion_map = {
                FailureCategory.SERVER_CRASH: "Check server-side error logs and unhandled exception tracebacks.",
                FailureCategory.AUTH_FAILURE: "Verify Bearer tokens, API keys, and authorization scope headers.",
                FailureCategory.VALIDATION_ERROR: "Review required request body parameters and data type constraints.",
                FailureCategory.TIMEOUT: "Optimize slow database queries, check connection pool saturation, and adjust timeouts.",
                FailureCategory.SCHEMA_MISMATCH: "Align OpenAPI specification with the actual JSON payload serialization model.",
                FailureCategory.ASSERTION_FAILED: "Review test expectation thresholds and verify business logic correctness.",
                FailureCategory.NETWORK_ERROR: "Verify service DNS, firewall rules, and target server availability.",
                FailureCategory.UNKNOWN: "Investigate application logs for sporadic failures.",
            }

            clusters_map[fp_hash] = {
                "cluster_id": cluster_id,
                "fingerprint": fp_hash,
                "category": category,
                "title": title_map.get(category, "Recurring Failure Pattern"),
                "description": f"Encountered repeated {category.value} with signature: '{norm_msg[:100]}...'",
                "affected_endpoint_ids": set(),
                "affected_test_case_ids": set(),
                "occurrence_count": 0,
                "first_seen_at": sample.timestamp,
                "last_seen_at": sample.timestamp,
                "sample_error_message": sample.error_message or (sample.assertion_failures[0] if sample.assertion_failures else None),
                "suggested_action": suggestion_map.get(category, "Investigate root cause."),
            }

        entry = clusters_map[fp_hash]
        entry["occurrence_count"] += 1
        if sample.endpoint_id:
            entry["affected_endpoint_ids"].add(sample.endpoint_id)
        if sample.test_case_id:
            entry["affected_test_case_ids"].add(sample.test_case_id)

        if sample.timestamp < entry["first_seen_at"]:
            entry["first_seen_at"] = sample.timestamp
        if sample.timestamp > entry["last_seen_at"]:
            entry["last_seen_at"] = sample.timestamp

    # Convert to FailureCluster Pydantic models
    cluster_list: List[FailureCluster] = []
    for fp_hash, item in clusters_map.items():
        cluster_list.append(
            FailureCluster(
                cluster_id=item["cluster_id"],
                fingerprint=item["fingerprint"],
                category=item["category"],
                title=item["title"],
                description=item["description"],
                affected_endpoint_ids=sorted(list(item["affected_endpoint_ids"])),
                affected_test_case_ids=sorted(list(item["affected_test_case_ids"])),
                occurrence_count=item["occurrence_count"],
                first_seen_at=item["first_seen_at"],
                last_seen_at=item["last_seen_at"],
                sample_error_message=item["sample_error_message"],
                suggested_action=item["suggested_action"],
            )
        )

    # Sort clusters by occurrence count descending
    return sorted(cluster_list, key=lambda c: c.occurrence_count, reverse=True)