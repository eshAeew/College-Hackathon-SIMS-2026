"""Pydantic Schemas for Multi-Execution Repetitive Runner and Flakiness/Variance Analyzer."""
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.models.schemas.execution import DirectExecutionRequest
from app.models.schemas.request_config import RequestCompileOverride


class ExecutionMode(str, Enum):
    """Execution repetition mode."""
    SEQUENTIAL = "sequential"
    CONCURRENT = "concurrent"


class FlakinessVerdict(str, Enum):
    """Flakiness risk classification verdict."""
    DETERMINISTIC_PASS = "DETERMINISTIC_PASS"
    MODERATE_FLAKINESS_WARN = "MODERATE_FLAKINESS_WARN"
    CRITICAL_INTERMITTENT_FAILURE = "CRITICAL_INTERMITTENT_FAILURE"


class ExecutionIterationResult(BaseModel):
    """Telemetry captured for a single execution iteration."""
    iteration: int = Field(..., description="Iteration sequence number (1-based)", example=1)
    timestamp: str = Field(..., description="ISO 8601 execution timestamp")
    status_code: Optional[int] = Field(None, description="HTTP status code returned", example=200)
    status_text: Optional[str] = Field(None, description="HTTP status text", example="OK")
    elapsed_ms: float = Field(..., description="Execution latency in milliseconds", example=15.42)
    payload_hash: str = Field(..., description="SHA-256 hash prefix of response body", example="a1b2c3d4e5f6")
    is_success: bool = Field(..., description="True if HTTP status code is 2xx", example=True)
    error: Optional[str] = Field(None, description="Network or protocol error message if failed")


class LatencyStatistics(BaseModel):
    """Comprehensive statistical distribution over execution latencies."""
    min_latency_ms: float = Field(..., description="Minimum latency observed")
    max_latency_ms: float = Field(..., description="Maximum latency observed")
    mean_latency_ms: float = Field(..., description="Average latency across iterations")
    median_latency_ms: float = Field(..., description="Median (P50) latency")
    std_dev_latency_ms: float = Field(..., description="Standard deviation of latency")
    p95_latency_ms: float = Field(..., description="95th percentile latency")
    p99_latency_ms: float = Field(..., description="99th percentile latency")
    jitter_ms: float = Field(..., description="Latency jitter (Max - Min)")
    coefficient_of_variation_percent: float = Field(..., description="Relative variability percentage (std_dev / mean * 100)")


class StatusCodeAnalysis(BaseModel):
    """Status code stability, entropy, and transition breakdown."""
    status_code_distribution: Dict[int, int] = Field(..., description="Frequency count per status code", example={200: 9, 503: 1})
    distinct_status_codes_count: int = Field(..., description="Number of different status codes observed")
    is_status_consistent: bool = Field(..., description="True if all iterations returned identical status code")
    shannon_entropy: float = Field(..., description="Shannon entropy score (0.0 = deterministic, >0.0 = unstable/flaky)")
    status_transitions: List[str] = Field(default_factory=list, description="Sequence of status transitions observed across consecutive runs")


class PayloadConsistencyAnalysis(BaseModel):
    """Payload body content drift and hash distribution."""
    distinct_payload_hashes_count: int = Field(..., description="Number of unique body payloads observed")
    is_payload_consistent: bool = Field(..., description="True if all responses returned identical payload content")
    payload_drift_detected: bool = Field(..., description="True if body variation was detected across runs")
    payload_hash_distribution: Dict[str, int] = Field(..., description="Count per payload SHA-256 hash")


class FlakinessReport(BaseModel):
    """Consolidated flakiness, latency variance, and behavior report across multi-execution iterations."""
    target: str = Field(..., description="URL or endpoint identifier tested", example="[GET] /api/v1/orders")
    total_runs: int = Field(..., description="Total execution repetitions completed")
    successful_runs: int = Field(..., description="Count of 2xx successful runs")
    failed_runs: int = Field(..., description="Count of non-2xx or failed runs")
    pass_rate_percent: float = Field(..., description="Percentage of successful runs (0-100%)", example=90.0)
    failure_rate_percent: float = Field(..., description="Percentage of failed runs (0-100%)", example=10.0)
    execution_mode: str = Field(..., description="sequential or concurrent")
    status_analysis: StatusCodeAnalysis = Field(..., description="Status code entropy and stability")
    latency_statistics: LatencyStatistics = Field(..., description="Latency variance, percentiles, and jitter")
    payload_analysis: PayloadConsistencyAnalysis = Field(..., description="Response payload drift analysis")
    flakiness_score: float = Field(..., description="Overall flakiness score from 0.0 (rock solid) to 100.0 (completely unstable)")
    is_flaky: bool = Field(..., description="True if endpoint exhibited non-deterministic behavior or high variance")
    verdict: FlakinessVerdict = Field(..., description="Risk classification verdict")
    findings: List[str] = Field(..., description="Detailed diagnostic findings")
    recommendations: List[str] = Field(..., description="Developer recommendations to resolve flakiness")
    iterations: List[ExecutionIterationResult] = Field(..., description="Telemetry log per execution iteration")
    summary: str = Field(..., description="Executive summary of multi-run analysis")


class MultiExecutionRequest(BaseModel):
    """Request payload for multi-run execution of an ad-hoc HTTP request."""
    direct_request: DirectExecutionRequest = Field(..., description="Ad-hoc request specification")
    iterations: int = Field(default=10, ge=2, le=50, description="Number of repetition iterations to execute")
    mode: ExecutionMode = Field(default=ExecutionMode.SEQUENTIAL, description="Sequential or concurrent dispatch")
    delay_ms: float = Field(default=0.0, ge=0.0, le=5000.0, description="Delay between sequential requests in milliseconds")
    concurrency_limit: int = Field(default=5, ge=1, le=20, description="Maximum concurrent connections when mode is concurrent")


class EndpointMultiExecutionRequest(BaseModel):
    """Request payload for multi-run execution of a stored workspace endpoint."""
    request_override: Optional[RequestCompileOverride] = Field(None, description="Runtime request overrides")
    iterations: int = Field(default=10, ge=2, le=50, description="Number of repetition iterations to execute")
    mode: ExecutionMode = Field(default=ExecutionMode.SEQUENTIAL, description="Sequential or concurrent dispatch")
    delay_ms: float = Field(default=0.0, ge=0.0, le=5000.0, description="Delay between sequential requests in milliseconds")
    concurrency_limit: int = Field(default=5, ge=1, le=20, description="Maximum concurrent connections when mode is concurrent")
    timeout_seconds: float = Field(default=10.0, gt=0.0, le=60.0, description="Per-request timeout")


class AnalyzeBatchRequest(BaseModel):
    """Request payload for analyzing an existing collection of iteration results."""
    iterations: List[ExecutionIterationResult] = Field(..., min_items=1, description="List of iteration results to analyze")
    target_name: Optional[str] = Field(default="External Batch Execution", description="Target identifier name")
