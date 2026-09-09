"""Lifecycle State Machine for Test Runs."""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
from app.models.schemas.test_run import RunStatus, TestResultStatus


class InvalidStateTransitionError(ValueError):
    """Raised when an illegal state machine transition is attempted."""
    pass


# Valid Lifecycle Transitions Map: Current State -> Set of Allowed Next States
VALID_TRANSITIONS: Dict[RunStatus, Set[RunStatus]] = {
    RunStatus.QUEUED: {RunStatus.RUNNING, RunStatus.CANCELLED},
    RunStatus.RUNNING: {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED},
    RunStatus.COMPLETED: set(),  # Terminal state
    RunStatus.CANCELLED: set(),  # Terminal state
    RunStatus.FAILED: set(),     # Terminal state
}


def validate_state_transition(current: str, target: str) -> None:
    """
    Validate whether transitioning from `current` to `target` status is legal.
    
    Raises:
        InvalidStateTransitionError: If the transition is prohibited.
    """
    try:
        curr_enum = RunStatus(current)
        target_enum = RunStatus(target)
    except ValueError as e:
        raise InvalidStateTransitionError(f"Invalid state status value: {e}")

    allowed = VALID_TRANSITIONS.get(curr_enum, set())
    if target_enum not in allowed:
        raise InvalidStateTransitionError(
            f"Illegal state transition from '{curr_enum.value}' to '{target_enum.value}'. "
            f"Allowed transitions from '{curr_enum.value}': {[s.value for s in allowed]}"
        )


def calculate_run_metrics(
    results: List[Any],
    started_at: Optional[datetime],
    finished_at: Optional[datetime]
) -> Tuple[int, int, int, int, int, float, float]:
    """
    Calculate totals, passed, failed, warnings, errors, pass rate %, and duration ms.
    
    Returns:
        (total, passed, failed, warnings, errors, pass_rate_pct, duration_ms)
    """
    total = len(results)
    passed = sum(1 for r in results if (r.status == TestResultStatus.PASS or r.status == "PASS"))
    failed = sum(1 for r in results if (r.status == TestResultStatus.FAIL or r.status == "FAIL"))
    warnings = sum(1 for r in results if (r.status == TestResultStatus.WARNING or r.status == "WARNING"))
    errors = sum(1 for r in results if (r.status in (TestResultStatus.ERROR, TestResultStatus.CANCELLED) or r.status in ("ERROR", "CANCELLED")))
    
    pass_rate_pct = round((passed / total * 100.0), 1) if total > 0 else 0.0

    duration_ms = 0.0
    if started_at and finished_at:
        s = started_at.replace(tzinfo=None) if started_at.tzinfo else started_at
        f = finished_at.replace(tzinfo=None) if finished_at.tzinfo else finished_at
        delta = f - s
        duration_ms = max(0.0, round(delta.total_seconds() * 1000.0, 2))

    return total, passed, failed, warnings, errors, pass_rate_pct, duration_ms
