"""Host-level Circuit Breaker state machine and registry for network resilience."""
import logging
import threading
import time
from enum import Enum
from typing import Dict, List, Optional
from urllib.parse import urlparse

from app.core.exceptions import CircuitBreakerOpenException

logger = logging.getLogger("app.resilience.circuit_breaker")


class CircuitState(str, Enum):
    """Circuit breaker operational states."""
    CLOSED = "CLOSED"        # Normal operation, requests allowed
    OPEN = "OPEN"            # Faulted, requests immediately rejected
    HALF_OPEN = "HALF_OPEN"  # Trial period, limited probe requests allowed


class CircuitBreaker:
    """State machine protecting target hosts against cascading network and timeout failures."""

    def __init__(
        self,
        host: str,
        failure_threshold: int = 5,
        recovery_timeout_seconds: float = 30.0,
        half_open_max_trials: int = 2,
    ):
        self.host = host
        self.failure_threshold = failure_threshold
        self.recovery_timeout_seconds = recovery_timeout_seconds
        self.half_open_max_trials = half_open_max_trials

        self.state: CircuitState = CircuitState.CLOSED
        self.failure_count: int = 0
        self.success_count: int = 0
        self.consecutive_failures: int = 0
        self.last_failure_time: Optional[float] = None
        self.last_state_change: float = time.time()
        self.half_open_trials: int = 0
        self._lock = threading.RLock()

    def can_execute(self) -> bool:
        """Check if request to this host can proceed based on current circuit state."""
        with self._lock:
            now = time.time()
            if self.state == CircuitState.CLOSED:
                return True

            if self.state == CircuitState.OPEN:
                # Check if recovery timeout has elapsed
                elapsed = now - (self.last_failure_time or self.last_state_change)
                if elapsed >= self.recovery_timeout_seconds:
                    logger.info(f"Circuit breaker for host '{self.host}' transitioning from OPEN -> HALF_OPEN (Cooldown {elapsed:.1f}s expired)")
                    self.state = CircuitState.HALF_OPEN
                    self.last_state_change = now
                    self.half_open_trials = 0
                    return True
                return False

            if self.state == CircuitState.HALF_OPEN:
                if self.half_open_trials < self.half_open_max_trials:
                    self.half_open_trials += 1
                    return True
                return False

            return True

    def check_and_raise(self) -> None:
        """Raise CircuitBreakerOpenException if requests to host are currently blocked."""
        with self._lock:
            if not self.can_execute():
                now = time.time()
                elapsed = now - (self.last_failure_time or self.last_state_change)
                remaining = max(0.0, self.recovery_timeout_seconds - elapsed)
                raise CircuitBreakerOpenException(
                    host=self.host,
                    cooldown_remaining=remaining,
                    consecutive_failures=self.consecutive_failures
                )

    def record_success(self) -> None:
        """Record a successful execution, recovering half-open circuits."""
        with self._lock:
            self.success_count += 1
            if self.state == CircuitState.HALF_OPEN:
                logger.info(f"Circuit breaker for host '{self.host}' transitioning from HALF_OPEN -> CLOSED (Trial probe passed)")
                self.state = CircuitState.CLOSED
                self.consecutive_failures = 0
                self.failure_count = 0
                self.last_state_change = time.time()
            elif self.state == CircuitState.CLOSED:
                self.consecutive_failures = 0

    def record_failure(self, exc: Optional[Exception] = None) -> None:
        """Record an execution failure, potentially tripping the circuit to OPEN."""
        with self._lock:
            now = time.time()
            self.failure_count += 1
            self.consecutive_failures += 1
            self.last_failure_time = now

            if self.state == CircuitState.HALF_OPEN:
                logger.warning(f"Circuit breaker for host '{self.host}' transitioning from HALF_OPEN -> OPEN (Trial probe failed: {exc})")
                self.state = CircuitState.OPEN
                self.last_state_change = now
            elif self.state == CircuitState.CLOSED:
                if self.consecutive_failures >= self.failure_threshold:
                    logger.warning(f"Circuit breaker for host '{self.host}' TRIPPED from CLOSED -> OPEN ({self.consecutive_failures} failures exceeded threshold of {self.failure_threshold})")
                    self.state = CircuitState.OPEN
                    self.last_state_change = now

    def reset(self) -> None:
        """Manually reset the circuit breaker to CLOSED state."""
        with self._lock:
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.consecutive_failures = 0
            self.half_open_trials = 0
            self.last_state_change = time.time()
            logger.info(f"Circuit breaker for host '{self.host}' manually RESET to CLOSED")


class CircuitBreakerRegistry:
    """Registry maintaining host-level circuit breakers."""
    _instance = None
    _lock = threading.RLock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(CircuitBreakerRegistry, cls).__new__(cls)
                cls._instance._breakers: Dict[str, CircuitBreaker] = {}
            return cls._instance

    @classmethod
    def extract_host(cls, target_url: str) -> str:
        """Extract clean hostname/netloc from target URL or host string."""
        if not target_url:
            return "unknown-host"
        url = target_url.strip()
        if not url.startswith(("http://", "https://")):
            url = f"http://{url}"
        parsed = urlparse(url)
        return parsed.netloc or parsed.path.split("/")[0] or "unknown-host"

    def get_breaker(self, host_or_url: str) -> CircuitBreaker:
        """Retrieve or create CircuitBreaker for a host."""
        host = self.extract_host(host_or_url)
        with self._lock:
            if host not in self._breakers:
                self._breakers[host] = CircuitBreaker(host=host)
            return self._breakers[host]

    def get_all(self) -> List[CircuitBreaker]:
        """Return list of all registered circuit breakers."""
        with self._lock:
            return list(self._breakers.values())

    def reset_breaker(self, host: str) -> bool:
        """Reset a specific circuit breaker."""
        clean_host = self.extract_host(host)
        with self._lock:
            if clean_host in self._breakers:
                self._breakers[clean_host].reset()
                return True
            return False

    def reset_all(self) -> int:
        """Reset all circuit breakers in registry."""
        with self._lock:
            count = len(self._breakers)
            for b in self._breakers.values():
                b.reset()
            return count

    def clear(self) -> None:
        """Clear all registry entries (used in tests)."""
        with self._lock:
            self._breakers.clear()
