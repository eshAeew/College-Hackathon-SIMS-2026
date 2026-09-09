"""Pydantic DTOs for side-by-side run comparison and delta visualization (Stage 21)."""
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ChangeKind(str, Enum):
    """How a single test changed between the baseline run and the current run."""
    BROKEN = "BROKEN"                  # was passing, now failing
    FIXED = "FIXED"                    # was failing, now passing
    STILL_FAILING = "STILL_FAILING"
    STILL_PASSING = "STILL_PASSING"
    SLOWER = "SLOWER"                  # passing on both sides, but materially slower
    FASTER = "FASTER"
    ADDED = "ADDED"                    # only present in the current run
    REMOVED = "REMOVED"                # only present in the baseline run


class BadgeTone(str, Enum):
    """Visual tone used by the delta visualizer."""
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    NEUTRAL = "NEUTRAL"
    WARNING = "WARNING"


class ComparisonVerdict(str, Enum):
    """Overall judgement of the current run against its baseline."""
    IMPROVED = "IMPROVED"
    CLEAN = "CLEAN"
    DEGRADED = "DEGRADED"
    CRITICAL_REGRESSIONS_FOUND = "CRITICAL_REGRESSIONS_FOUND"


class RunSnapshot(BaseModel):
    """Headline metrics for one side of the comparison."""
    run_id: int
    name: str
    status: str
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    warning_tests: int = 0
    error_tests: int = 0
    pass_rate_pct: float = 0.0
    avg_latency_ms: float = 0.0
    duration_ms: float = 0.0
    executed_at: Optional[datetime] = None


class MetricDelta(BaseModel):
    """Signed change in a single headline metric."""
    metric: str
    baseline: float
    current: float
    delta: float
    delta_pct: Optional[float] = None
    tone: BadgeTone = BadgeTone.NEUTRAL


class TestChange(BaseModel):
    """Per-test difference between the two runs."""
    test_name: str
    test_case_id: Optional[int] = None
    endpoint_id: Optional[int] = None
    change: ChangeKind
    tone: BadgeTone = BadgeTone.NEUTRAL
    badge: str = Field(default="", description="Short label for the visualizer")
    baseline_status: Optional[str] = None
    current_status: Optional[str] = None
    baseline_code: Optional[int] = None
    current_code: Optional[int] = None
    baseline_latency_ms: Optional[float] = None
    current_latency_ms: Optional[float] = None
    latency_delta_pct: Optional[float] = None
    detail: str = ""


class LatencyShift(BaseModel):
    """Distribution movement across the two runs."""
    baseline_avg_ms: float = 0.0
    current_avg_ms: float = 0.0
    delta_ms: float = 0.0
    delta_pct: Optional[float] = None
    baseline_max_ms: float = 0.0
    current_max_ms: float = 0.0
    tone: BadgeTone = BadgeTone.NEUTRAL
    summary: str = ""


class RunComparisonReport(BaseModel):
    """Complete side-by-side comparison of two runs."""
    project_id: Optional[int] = None
    baseline: RunSnapshot
    current: RunSnapshot
    metric_deltas: List[MetricDelta] = Field(default_factory=list)
    changes: List[TestChange] = Field(default_factory=list)
    latency_shift: LatencyShift = Field(default_factory=LatencyShift)
    broken_count: int = 0
    fixed_count: int = 0
    slower_count: int = 0
    faster_count: int = 0
    added_count: int = 0
    removed_count: int = 0
    net_quality_delta_pct: float = Field(
        default=0.0, description="Pass-rate movement: positive means improved"
    )
    verdict: ComparisonVerdict = ComparisonVerdict.CLEAN
    headline: str = ""
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DeltaBadge(BaseModel):
    """A single rendered badge for the visualizer strip."""
    label: str
    value: str
    tone: BadgeTone
    hint: str = ""


class DeltaVisualization(BaseModel):
    """View-model consumed by the run-comparison UI (sub-stage 21.02)."""
    baseline_label: str
    current_label: str
    verdict: ComparisonVerdict
    headline: str
    badges: List[DeltaBadge] = Field(default_factory=list)
    regressions: List[TestChange] = Field(default_factory=list)
    improvements: List[TestChange] = Field(default_factory=list)
    latency_shift: LatencyShift = Field(default_factory=LatencyShift)
    pass_rate_series: Dict[str, float] = Field(default_factory=dict)
    status_matrix: Dict[str, Any] = Field(default_factory=dict)
