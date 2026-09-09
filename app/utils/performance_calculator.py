"""Performance statistical calculation engine and SLA threshold evaluator."""
import math
import statistics
from typing import List, Tuple

from app.models.schemas.performance import (
    LatencyBucket,
    LatencyDistributionSummary,
    LatencyPercentileMetrics,
    SLAEvaluationResult,
    SLAPerformanceRating,
    SLAPolicy,
)


def calculate_percentile(sorted_data: List[float], p: float) -> float:
    """
    Calculate the p-th percentile of a sorted list using linear interpolation.
    
    Args:
        sorted_data: Sorted list of numeric values (non-empty).
        p: Percentile between 0 and 100.
        
    Returns:
        Interpolated percentile value rounded to 2 decimal places.
    """
    if not sorted_data:
        return 0.0

    n = len(sorted_data)
    if n == 1:
        return round(sorted_data[0], 2)

    if p <= 0:
        return round(sorted_data[0], 2)
    if p >= 100:
        return round(sorted_data[-1], 2)

    rank = (p / 100.0) * (n - 1)
    lower_idx = int(math.floor(rank))
    upper_idx = int(math.ceil(rank))
    weight = rank - lower_idx

    val = sorted_data[lower_idx] + weight * (sorted_data[upper_idx] - sorted_data[lower_idx])
    return round(val, 2)


def classify_latency_bucket(latency_ms: float) -> LatencyBucket:
    """Classify an individual request latency into performance tiers."""
    if latency_ms < 200.0:
        return LatencyBucket.FAST
    elif latency_ms <= 500.0:
        return LatencyBucket.ACCEPTABLE
    elif latency_ms <= 1000.0:
        return LatencyBucket.SLOW
    else:
        return LatencyBucket.CRITICAL


def compute_latency_percentiles(latencies: List[float]) -> LatencyPercentileMetrics:
    """
    Compute full percentile statistics and distribution buckets from a list of latencies.
    """
    if not latencies:
        raise ValueError("Cannot compute percentiles from empty latency list.")

    sorted_lats = sorted(latencies)
    n = len(sorted_lats)

    min_ms = round(sorted_lats[0], 2)
    max_ms = round(sorted_lats[-1], 2)
    mean_ms = round(statistics.mean(sorted_lats), 2)
    median_p50_ms = calculate_percentile(sorted_lats, 50.0)
    p90_ms = calculate_percentile(sorted_lats, 90.0)
    p95_ms = calculate_percentile(sorted_lats, 95.0)
    p99_ms = calculate_percentile(sorted_lats, 99.0)

    std_dev_ms = round(statistics.stdev(sorted_lats), 2) if n > 1 else 0.0
    jitter_ms = round(max_ms - min_ms, 2)
    cv_pct = round((std_dev_ms / mean_ms * 100.0), 2) if mean_ms > 0 else 0.0

    # Bucket distribution counts
    fast_c = sum(1 for lat in sorted_lats if lat < 200.0)
    acc_c = sum(1 for lat in sorted_lats if 200.0 <= lat <= 500.0)
    slow_c = sum(1 for lat in sorted_lats if 500.0 < lat <= 1000.0)
    crit_c = sum(1 for lat in sorted_lats if lat > 1000.0)

    distribution = LatencyDistributionSummary(
        fast_count=fast_c,
        acceptable_count=acc_c,
        slow_count=slow_c,
        critical_count=crit_c,
        fast_pct=round((fast_c / n) * 100.0, 1),
        acceptable_pct=round((acc_c / n) * 100.0, 1),
        slow_pct=round((slow_c / n) * 100.0, 1),
        critical_pct=round((crit_c / n) * 100.0, 1),
    )

    return LatencyPercentileMetrics(
        sample_count=n,
        min_ms=min_ms,
        max_ms=max_ms,
        mean_ms=mean_ms,
        median_p50_ms=median_p50_ms,
        p90_ms=p90_ms,
        p95_ms=p95_ms,
        p99_ms=p99_ms,
        std_dev_ms=std_dev_ms,
        jitter_ms=jitter_ms,
        cv_percent=cv_pct,
        distribution=distribution,
    )


def evaluate_sla_policy(
    metrics: LatencyPercentileMetrics,
    sla_policy: SLAPolicy,
    total_requests: int,
    error_count: int = 0
) -> SLAEvaluationResult:
    """
    Evaluate calculated latency percentiles and error rates against configured SLA thresholds.
    """
    breaches: List[str] = []
    warnings: List[str] = []
    recommendations: List[str] = []

    actual_error_rate_pct = round((error_count / total_requests * 100.0), 2) if total_requests > 0 else 0.0

    # 1. Check Error Rate
    if actual_error_rate_pct > sla_policy.max_error_rate_pct:
        breaches.append(
            f"Error rate {actual_error_rate_pct}% exceeded max tolerable SLA error rate {sla_policy.max_error_rate_pct}% ({error_count}/{total_requests} failed)."
        )
        recommendations.append("Investigate upstream server stability and 5xx exception logs.")

    # 2. Check P95 Threshold
    if metrics.p95_ms > sla_policy.target_p95_ms:
        breaches.append(
            f"P95 latency {metrics.p95_ms:.2f}ms exceeded target SLA limit {sla_policy.target_p95_ms:.2f}ms (+{metrics.p95_ms - sla_policy.target_p95_ms:.2f}ms breach)."
        )
        recommendations.append("Analyze database query plans, index usage, and heavy payload serialization.")

    # 3. Check P99 Threshold
    if metrics.p99_ms > sla_policy.target_p99_ms:
        breaches.append(
            f"P99 latency {metrics.p99_ms:.2f}ms exceeded target SLA limit {sla_policy.target_p99_ms:.2f}ms (+{metrics.p99_ms - sla_policy.target_p99_ms:.2f}ms breach)."
        )
        recommendations.append("Check for resource contention, GC pauses, or connection pool exhaustion.")

    # 4. Check Maximum Acceptable Latency Ceiling
    if metrics.max_ms > sla_policy.max_acceptable_latency_ms:
        breaches.append(
            f"Maximum observed latency {metrics.max_ms:.2f}ms breached hard ceiling {sla_policy.max_acceptable_latency_ms:.2f}ms."
        )

    # 5. Check Mean Latency Warning Threshold
    if metrics.mean_ms > sla_policy.warn_threshold_ms:
        warnings.append(
            f"Average latency {metrics.mean_ms:.2f}ms approached warning threshold {sla_policy.warn_threshold_ms:.2f}ms."
        )
        recommendations.append("Consider implementing edge caching (Redis/CDN) for frequently queried resources.")

    # 6. Check High Jitter / CV% Warning
    if metrics.cv_percent > 50.0 or metrics.jitter_ms > 500.0:
        warnings.append(
            f"High response time variance detected (Jitter: {metrics.jitter_ms:.2f}ms, CV: {metrics.cv_percent:.1f}%)."
        )

    # Determine Rating and Compliance Percentage
    # Total criteria scored = 5 (error_rate, p95, p99, max_ceiling, mean_warn)
    score_penalty = (len(breaches) * 25.0) + (len(warnings) * 10.0)
    compliance_pct = max(0.0, min(100.0, round(100.0 - score_penalty, 1)))

    if len(breaches) == 0 and len(warnings) == 0:
        rating = SLAPerformanceRating.OPTIMAL
        sla_met = True
    elif len(breaches) == 0:
        rating = SLAPerformanceRating.ACCEPTABLE
        sla_met = True
    elif len(breaches) == 1:
        rating = SLAPerformanceRating.DEGRADED
        sla_met = False
    else:
        rating = SLAPerformanceRating.BREACHED
        sla_met = False

    if sla_met and not recommendations:
        recommendations.append("Endpoint performance adheres strictly to all SLA parameters. No remediation needed.")

    return SLAEvaluationResult(
        sla_met=sla_met,
        rating=rating,
        compliance_percentage=compliance_pct,
        breaches=breaches,
        warnings=warnings,
        recommendations=recommendations,
    )