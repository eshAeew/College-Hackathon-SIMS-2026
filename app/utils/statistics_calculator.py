"""Statistical, Entropy, and Flakiness Calculation Engine.

Provides statistical analysis across multi-execution runs:
- Latency metrics: min, max, mean, median, standard deviation, P95, P99, jitter, coefficient of variation.
- Status Code Entropy: Shannon entropy, status code frequency distribution, state transition tracking.
- Payload Drift Detection: Deterministic SHA-256 body hashing and consistency ratio.
- Composite Flakiness Scoring & Risk Classification.
"""
import hashlib
import json
import math
import statistics
from typing import Any, Dict, List, Optional, Tuple


def compute_latency_stats(latencies: List[float]) -> Dict[str, Any]:
    """Compute comprehensive statistical distribution over request latency measurements.
    
    Returns:
    - min_latency_ms
    - max_latency_ms
    - mean_latency_ms
    - median_latency_ms
    - std_dev_latency_ms
    - p95_latency_ms
    - p99_latency_ms
    - jitter_ms (max - min)
    - coefficient_of_variation_percent (std_dev / mean * 100)
    """
    if not latencies:
        return {
            "min_latency_ms": 0.0,
            "max_latency_ms": 0.0,
            "mean_latency_ms": 0.0,
            "median_latency_ms": 0.0,
            "std_dev_latency_ms": 0.0,
            "p95_latency_ms": 0.0,
            "p99_latency_ms": 0.0,
            "jitter_ms": 0.0,
            "coefficient_of_variation_percent": 0.0
        }

    sorted_lats = sorted(latencies)
    n = len(sorted_lats)
    min_lat = round(sorted_lats[0], 3)
    max_lat = round(sorted_lats[-1], 3)
    mean_lat = round(statistics.mean(sorted_lats), 3)
    median_lat = round(statistics.median(sorted_lats), 3)
    std_dev = round(statistics.stdev(sorted_lats), 3) if n > 1 else 0.0
    jitter = round(max_lat - min_lat, 3)

    # Percentile interpolation
    def percentile(data: List[float], p: float) -> float:
        if len(data) == 1:
            return data[0]
        k = (len(data) - 1) * p
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return data[int(k)]
        return data[f] * (c - k) + data[c] * (k - f)

    p95 = round(percentile(sorted_lats, 0.95), 3)
    p99 = round(percentile(sorted_lats, 0.99), 3)
    cv = round((std_dev / mean_lat) * 100, 2) if mean_lat > 0 else 0.0

    return {
        "min_latency_ms": min_lat,
        "max_latency_ms": max_lat,
        "mean_latency_ms": mean_lat,
        "median_latency_ms": median_lat,
        "std_dev_latency_ms": std_dev,
        "p95_latency_ms": p95,
        "p99_latency_ms": p99,
        "jitter_ms": jitter,
        "coefficient_of_variation_percent": cv
    }


def compute_status_entropy(status_codes: List[Optional[int]]) -> Dict[str, Any]:
    """Compute Shannon entropy, distribution, and transitions over observed HTTP status codes.
    
    Shannon Entropy H = - sum(p_i * log2(p_i))
    H = 0.0 indicates 100% deterministic status codes across runs.
    H > 0.0 indicates non-deterministic status code variation.
    """
    cleaned_codes: List[int] = [sc if sc is not None else 0 for sc in status_codes]
    total = len(cleaned_codes)
    if total == 0:
        return {
            "status_code_distribution": {},
            "distinct_status_codes_count": 0,
            "is_status_consistent": True,
            "shannon_entropy": 0.0,
            "status_transitions": []
        }

    distribution: Dict[int, int] = {}
    for sc in cleaned_codes:
        distribution[sc] = distribution.get(sc, 0) + 1

    entropy = 0.0
    for count in distribution.values():
        p_i = count / total
        if p_i > 0:
            entropy -= p_i * math.log2(p_i)
    entropy = round(entropy, 4)

    # Track sequential transitions e.g. ["200 -> 200", "200 -> 503"]
    transitions: List[str] = []
    for i in range(len(cleaned_codes) - 1):
        from_code = cleaned_codes[i]
        to_code = cleaned_codes[i + 1]
        transitions.append(f"{from_code} -> {to_code}")

    distinct_count = len(distribution)
    is_consistent = (distinct_count == 1)

    return {
        "status_code_distribution": distribution,
        "distinct_status_codes_count": distinct_count,
        "is_status_consistent": is_consistent,
        "shannon_entropy": entropy,
        "status_transitions": transitions
    }


def compute_payload_hashes(bodies: List[Any]) -> Dict[str, Any]:
    """Generate SHA-256 hashes of response bodies to detect content variation or drift."""
    if not bodies:
        return {
            "distinct_payload_hashes_count": 0,
            "is_payload_consistent": True,
            "payload_drift_detected": False,
            "payload_hash_distribution": {}
        }

    hash_distribution: Dict[str, int] = {}
    for body in bodies:
        if body is None:
            raw_str = "__EMPTY_OR_NULL__"
        elif isinstance(body, (dict, list)):
            try:
                raw_str = json.dumps(body, sort_keys=True)
            except Exception:
                raw_str = str(body)
        else:
            raw_str = str(body)

        body_hash = hashlib.sha256(raw_str.encode("utf-8")).hexdigest()[:12]
        hash_distribution[body_hash] = hash_distribution.get(body_hash, 0) + 1

    distinct_count = len(hash_distribution)
    is_consistent = (distinct_count <= 1)
    drift_detected = (distinct_count > 1)

    return {
        "distinct_payload_hashes_count": distinct_count,
        "is_payload_consistent": is_consistent,
        "payload_drift_detected": drift_detected,
        "payload_hash_distribution": hash_distribution
    }


def evaluate_flakiness(
    total_runs: int,
    status_analysis: Dict[str, Any],
    latency_stats: Dict[str, Any],
    payload_analysis: Dict[str, Any]
) -> Tuple[float, str, List[str], List[str]]:
    """Synthesize a composite flakiness score (0-100%) and determine risk verdict.
    
    Returns:
        (flakiness_score, verdict, findings, recommendations)
    """
    if total_runs <= 1:
        return 0.0, "DETERMINISTIC_PASS", ["Only 1 iteration executed; insufficient data for variance scoring."], []

    findings: List[str] = []
    recommendations: List[str] = []
    flakiness_penalty = 0.0

    # 1. Status Code Variation Penalty (Weight: up to 60 points)
    entropy = status_analysis.get("shannon_entropy", 0.0)
    distinct_statuses = status_analysis.get("distinct_status_codes_count", 1)
    if distinct_statuses > 1:
        dist_str = ", ".join([f"HTTP {k} ({v}x)" for k, v in status_analysis.get("status_code_distribution", {}).items()])
        findings.append(f"Non-deterministic status codes detected across runs: {dist_str} (Entropy: {entropy}).")
        # Entropy of 1.0 (e.g. 50% 200, 50% 500) gives 60 points penalty
        status_penalty = min(60.0, entropy * 45.0 + (distinct_statuses - 1) * 15.0)
        flakiness_penalty += status_penalty
        recommendations.append("Investigate intermittent backend exceptions, unhandled database lock contention, or upstream service timeouts causing status code switching.")

    # 2. Payload Content Drift (Weight: up to 20 points)
    if payload_analysis.get("payload_drift_detected"):
        hashes_count = payload_analysis.get("distinct_payload_hashes_count", 1)
        findings.append(f"Response payload drift detected ({hashes_count} distinct payload variations observed).")
        flakiness_penalty += min(20.0, (hashes_count - 1) * 10.0)
        recommendations.append("Verify whether dynamic timestamps, non-deterministic database ordering, or unseeded random values in the response body are expected.")

    # 3. Latency Jitter & High Variance (Weight: up to 20 points)
    cv = latency_stats.get("coefficient_of_variation_percent", 0.0)
    jitter = latency_stats.get("jitter_ms", 0.0)
    if cv > 50.0 or jitter > 500.0:
        findings.append(f"High latency jitter observed: Min {latency_stats['min_latency_ms']}ms to Max {latency_stats['max_latency_ms']}ms (CV: {cv}%).")
        if cv > 100.0:
            flakiness_penalty += 20.0
        elif cv > 50.0:
            flakiness_penalty += 10.0
        recommendations.append("Profile endpoint performance for cold starts, garbage collection pauses, or database connection pool starvation.")

    flakiness_score = round(min(100.0, flakiness_penalty), 2)

    # Determine Verdict
    if flakiness_score == 0.0:
        verdict = "DETERMINISTIC_PASS"
        findings.append("Endpoint demonstrated 100% consistent behavior across all iterations.")
    elif flakiness_score < 30.0:
        verdict = "MODERATE_FLAKINESS_WARN"
    else:
        verdict = "CRITICAL_INTERMITTENT_FAILURE"

    return flakiness_score, verdict, findings, recommendations
