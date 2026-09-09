"""Pydantic schemas and DTOs for Performance Analysis & SLA Benchmarking (Stage 10)."""
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.models.schemas.endpoint import HTTPMethod
from app.models.schemas.request_config import BodyType


class LatencyBucket(str, Enum):
    """Categorized response time tiers."""
    FAST = "FAST (<200ms)"
    ACCEPTABLE = "ACCEPTABLE (200-500ms)"
    SLOW = "SLOW (500-1000ms)"
    CRITICAL = "CRITICAL (>1000ms)"


class SLAPerformanceRating(str, Enum):
    """Overall SLA threshold compliance rating."""
    OPTIMAL = "OPTIMAL"
    ACCEPTABLE = "ACCEPTABLE"
    DEGRADED = "DEGRADED"
    BREACHED = "BREACHED"


class SLAPolicy(BaseModel):
    """Configurable Service Level Agreement (SLA) threshold expectations."""
    target_p95_ms: float = Field(
        default=500.0,
        gt=0.0,
        description="Target 95th percentile latency limit in ms",
        examples=[500.0]
    )
    target_p99_ms: float = Field(
        default=1000.0,
        gt=0.0,
        description="Target 99th percentile latency limit in ms",
        examples=[1000.0]
    )
    max_acceptable_latency_ms: float = Field(
        default=1500.0,
        gt=0.0,
        description="Hard maximum acceptable ceiling for any single request in ms",
        examples=[1500.0]
    )
    warn_threshold_ms: float = Field(
        default=400.0,
        gt=0.0,
        description="Average latency warning threshold in ms",
        examples=[400.0]
    )
    max_error_rate_pct: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Maximum tolerable error rate percentage",
        examples=[0.0]
    )


class LatencyDistributionSummary(BaseModel):
    """Bucket count and percentage breakdown across latency tiers."""
    fast_count: int = Field(default=0, description="Requests <200ms")
    acceptable_count: int = Field(default=0, description="Requests 200-500ms")
    slow_count: int = Field(default=0, description="Requests 500-1000ms")
    critical_count: int = Field(default=0, description="Requests >1000ms")
    fast_pct: float = Field(default=0.0, description="Percentage <200ms")
    acceptable_pct: float = Field(default=0.0, description="Percentage 200-500ms")
    slow_pct: float = Field(default=0.0, description="Percentage 500-1000ms")
    critical_pct: float = Field(default=0.0, description="Percentage >1000ms")


class LatencyPercentileMetrics(BaseModel):
    """Comprehensive sub-millisecond statistical performance metrics."""
    sample_count: int = Field(..., description="Number of execution samples analyzed")
    min_ms: float = Field(..., description="Fastest request latency in ms")
    max_ms: float = Field(..., description="Slowest request latency in ms")
    mean_ms: float = Field(..., description="Arithmetic mean response time in ms")
    median_p50_ms: float = Field(..., description="50th percentile (median) latency in ms")
    p90_ms: float = Field(..., description="90th percentile latency in ms")
    p95_ms: float = Field(..., description="95th percentile latency in ms")
    p99_ms: float = Field(..., description="99th percentile latency in ms")
    std_dev_ms: float = Field(..., description="Sample standard deviation in ms")
    jitter_ms: float = Field(..., description="Latency jitter (max - min) in ms")
    cv_percent: float = Field(..., description="Coefficient of variation ((std_dev / mean) * 100)")
    distribution: LatencyDistributionSummary = Field(..., description="Latency tier distribution")


class SLAEvaluationResult(BaseModel):
    """Outcome of SLA threshold compliance evaluation."""
    sla_met: bool = Field(..., description="True if all strict SLA thresholds were satisfied")
    rating: SLAPerformanceRating = Field(..., description="SLA rating classification")
    compliance_percentage: float = Field(..., ge=0.0, le=100.0, description="Overall compliance score percentage")
    breaches: List[str] = Field(default_factory=list, description="List of SLA criteria that failed")
    warnings: List[str] = Field(default_factory=list, description="List of non-critical SLA performance warnings")
    recommendations: List[str] = Field(default_factory=list, description="Actionable optimization suggestions")


class PerformanceBenchmarkIteration(BaseModel):
    """Single sample recorded during a performance benchmark run."""
    iteration: int = Field(..., description="Iteration number (1-based)")
    status_code: Optional[int] = Field(default=None, description="HTTP status code received")
    latency_ms: float = Field(..., description="Elapsed latency in ms")
    bucket: LatencyBucket = Field(..., description="Latency tier bucket")
    success: bool = Field(..., description="True if 2xx response")


class PerformanceReport(BaseModel):
    """Complete performance benchmark analysis and SLA report."""
    target_url: Optional[str] = Field(default=None, description="Target API endpoint URL")
    http_method: Optional[str] = Field(default=None, description="HTTP verb executed")
    total_requests: int = Field(..., description="Total benchmark requests dispatched")
    successful_requests: int = Field(..., description="Successful requests (2xx status)")
    failed_requests: int = Field(..., description="Failed requests (4xx/5xx or network errors)")
    error_rate_pct: float = Field(..., description="Failure rate percentage")
    throughput_rps: float = Field(..., description="Estimated throughput (requests per second)")
    metrics: LatencyPercentileMetrics = Field(..., description="Calculated statistical percentiles")
    sla_result: SLAEvaluationResult = Field(..., description="SLA compliance evaluation")
    iterations: List[PerformanceBenchmarkIteration] = Field(default_factory=list, description="Individual iteration telemetry")
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Report generation timestamp")


class DirectBenchmarkRequest(BaseModel):
    """Request specification for running a performance benchmark against an ad-hoc URL."""
    base_url: str = Field(..., description="Target server base URL", examples=["https://httpbin.org"])
    method: HTTPMethod = Field(default=HTTPMethod.GET, description="HTTP verb")
    path: str = Field(default="", description="Path template or concrete path", examples=["/get"])
    path_params: Dict[str, Any] = Field(default_factory=dict, description="Values for {param} tokens in path")
    query_params: Dict[str, Any] = Field(default_factory=dict, description="URL query parameters")
    headers: Dict[str, str] = Field(default_factory=dict, description="Custom HTTP headers")
    body_type: BodyType = Field(default=BodyType.EMPTY, description="Payload serialization format")
    body: Optional[Any] = Field(default=None, description="Request body payload")
    repetition_count: int = Field(default=10, ge=2, le=100, description="Number of benchmark iterations")
    concurrency_limit: int = Field(default=1, ge=1, le=20, description="Max concurrent requests (1 for sequential)")
    delay_ms: float = Field(default=0.0, ge=0.0, le=5000.0, description="Delay between requests in ms (sequential mode)")
    sla_policy: SLAPolicy = Field(default_factory=SLAPolicy, description="SLA thresholds to evaluate against")


class EndpointBenchmarkRequest(BaseModel):
    """Request specification for benchmarking a stored endpoint."""
    repetition_count: int = Field(default=10, ge=2, le=100, description="Number of benchmark iterations")
    concurrency_limit: int = Field(default=1, ge=1, le=20, description="Max concurrent requests (1 for sequential)")
    delay_ms: float = Field(default=0.0, ge=0.0, le=5000.0, description="Delay between requests in ms")
    path_params: Optional[Dict[str, Any]] = Field(default=None, description="Path parameters override")
    query_params: Optional[Dict[str, Any]] = Field(default=None, description="Query parameters override")
    headers: Optional[Dict[str, str]] = Field(default=None, description="Headers override")
    body_type: Optional[BodyType] = Field(default=None, description="Body type override")
    body: Optional[Any] = Field(default=None, description="Body override")
    sla_policy: Optional[SLAPolicy] = Field(default=None, description="Optional custom SLA policy override")


class AnalyzeLatencyBatchRequest(BaseModel):
    """Request specification for evaluating pre-recorded latency values against an SLA policy."""
    latencies: List[float] = Field(..., min_length=1, description="List of recorded response latencies in ms")
    error_count: int = Field(default=0, ge=0, description="Number of recorded failed requests")
    sla_policy: SLAPolicy = Field(default_factory=SLAPolicy, description="SLA policy criteria to evaluate")