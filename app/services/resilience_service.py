"""Service layer for Circuit Breaker management, error ring-buffer telemetry, and resilience probes."""
import collections
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.core.circuit_breaker import CircuitBreakerRegistry, CircuitState
from app.models.schemas.resilience import (
    CircuitBreakerListResponse,
    CircuitBreakerResetResponse,
    CircuitBreakerStatus,
    ErrorCategoryStat,
    PlatformErrorSummaryResponse,
)

logger = logging.getLogger("app.services.resilience")


class ResilienceService:
    """Service handling host circuit breakers, platform error metrics, and graceful degradation telemetry."""
    
    _error_counts: Dict[str, int] = collections.defaultdict(int)
    _last_error_times: Dict[str, str] = {}
    _latest_messages: Dict[str, str] = {}
    _ai_fallback_count: int = 0
    _lock = threading.RLock()

    @classmethod
    def record_error(cls, category: str, message: str) -> None:
        """Record an error event in the in-memory telemetry tracker."""
        with cls._lock:
            cls._error_counts[category] += 1
            now_iso = datetime.now(timezone.utc).isoformat()
            cls._last_error_times[category] = now_iso
            cls._latest_messages[category] = message[:200]

    @classmethod
    def record_ai_fallback(cls) -> None:
        """Increment counter when AI falls back to offline deterministic heuristics."""
        with cls._lock:
            cls._ai_fallback_count += 1
            cls.record_error("AI_HEURISTIC_FALLBACK", "Google Gemini unavailable; used deterministic heuristic engine.")

    @classmethod
    def get_circuit_breakers(cls) -> CircuitBreakerListResponse:
        """Retrieve telemetry for all registered host circuit breakers."""
        registry = CircuitBreakerRegistry()
        breakers = registry.get_all()

        statuses: List[CircuitBreakerStatus] = []
        open_c = 0
        half_open_c = 0
        closed_c = 0

        now = time.time()
        for b in breakers:
            with b._lock:
                cooldown_rem = None
                if b.state == CircuitState.OPEN:
                    open_c += 1
                    elapsed = now - (b.last_failure_time or b.last_state_change)
                    cooldown_rem = max(0.0, b.recovery_timeout_seconds - elapsed)
                elif b.state == CircuitState.HALF_OPEN:
                    half_open_c += 1
                else:
                    closed_c += 1

                last_fail_iso = (
                    datetime.fromtimestamp(b.last_failure_time, tz=timezone.utc).isoformat()
                    if b.last_failure_time else None
                )
                last_change_iso = datetime.fromtimestamp(b.last_state_change, tz=timezone.utc).isoformat()

                statuses.append(
                    CircuitBreakerStatus(
                        host=b.host,
                        state=b.state,
                        failure_count=b.failure_count,
                        success_count=b.success_count,
                        consecutive_failures=b.consecutive_failures,
                        cooldown_remaining_seconds=round(cooldown_rem, 1) if cooldown_rem is not None else None,
                        last_failure_time=last_fail_iso,
                        last_state_change=last_change_iso,
                    )
                )

        return CircuitBreakerListResponse(
            total_breakers=len(breakers),
            open_count=open_c,
            half_open_count=half_open_c,
            closed_count=closed_c,
            breakers=statuses,
        )

    @classmethod
    def reset_circuit_breaker(cls, host: str) -> CircuitBreakerResetResponse:
        """Manually reset a specific host circuit breaker to CLOSED."""
        registry = CircuitBreakerRegistry()
        clean_host = registry.extract_host(host)
        b = registry.get_breaker(clean_host)
        b.reset()
        return CircuitBreakerResetResponse(
            success=True,
            host=clean_host,
            new_state=CircuitState.CLOSED,
            reset_at=datetime.now(timezone.utc).isoformat(),
        )

    @classmethod
    def reset_all_circuit_breakers(cls) -> int:
        """Reset all monitored host circuit breakers."""
        registry = CircuitBreakerRegistry()
        return registry.reset_all()

    @classmethod
    def get_error_summary(cls) -> PlatformErrorSummaryResponse:
        """Retrieve aggregated error categories and resilience telemetry."""
        registry = CircuitBreakerRegistry()
        open_count = sum(1 for b in registry.get_all() if b.state == CircuitState.OPEN)

        with cls._lock:
            categories: List[ErrorCategoryStat] = []
            total_errors = sum(cls._error_counts.values())

            for cat, cnt in sorted(cls._error_counts.items(), key=lambda x: x[1], reverse=True):
                categories.append(
                    ErrorCategoryStat(
                        category=cat,
                        count=cnt,
                        last_occurred_at=cls._last_error_times.get(cat),
                        latest_message=cls._latest_messages.get(cat),
                    )
                )

            return PlatformErrorSummaryResponse(
                total_errors_handled=total_errors,
                active_open_circuit_breakers=open_count,
                ai_fallback_invocations=cls._ai_fallback_count,
                categories=categories,
                generated_at=datetime.now(timezone.utc).isoformat(),
            )
