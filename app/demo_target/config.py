import threading
from typing import Any, Dict


class DemoApiConfig:
    """State manager controlling injected bugs and simulation counters."""
    _instance = None
    _lock = threading.RLock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(DemoApiConfig, cls).__new__(cls)
                cls._instance.reset()
            return cls._instance

    def reset(self) -> None:
        """Reset all bugs to default FLAWED states."""
        with self._lock:
            self.unhandled_500_login: bool = True
            self.slow_latency_products: bool = True
            self.schema_drift_product_detail: bool = True
            self.flaky_503_orders: bool = True
            self.malformed_json_profile: bool = True
            self.state_leak_checkout: bool = True
            self.checkout_invocations: int = 0
            self.endpoint_hits: Dict[str, int] = {
                "login": 0,
                "products": 0,
                "product_detail": 0,
                "orders": 0,
                "profile": 0,
                "checkout": 0,
            }

    def fix_all(self) -> None:
        """Fix all bugs (used for demonstration of resolution & regression verification)."""
        with self._lock:
            self.unhandled_500_login = False
            self.slow_latency_products = False
            self.schema_drift_product_detail = False
            self.flaky_503_orders = False
            self.malformed_json_profile = False
            self.state_leak_checkout = False
            self.checkout_invocations = 0

    def toggle(self, bug_name: str) -> bool:
        """Toggle an individual bug between flawed and fixed."""
        with self._lock:
            attr_name = bug_name.lower().replace("-", "_")
            if hasattr(self, attr_name):
                current = getattr(self, attr_name)
                setattr(self, attr_name, not current)
                return getattr(self, attr_name)
            raise KeyError(f"Unknown bug flag: '{bug_name}'")

    def increment_hit(self, endpoint: str) -> int:
        """Increment endpoint call counter."""
        with self._lock:
            self.endpoint_hits[endpoint] = self.endpoint_hits.get(endpoint, 0) + 1
            return self.endpoint_hits[endpoint]

    def get_status(self) -> Dict[str, Any]:
        """Return snapshot of bug switches and hit telemetry."""
        with self._lock:
            active_bugs = [
                k for k in [
                    "unhandled_500_login",
                    "slow_latency_products",
                    "schema_drift_product_detail",
                    "flaky_503_orders",
                    "malformed_json_profile",
                    "state_leak_checkout",
                ]
                if getattr(self, k)
            ]
            return {
                "total_bugs": 6,
                "active_flaws_count": len(active_bugs),
                "is_flawed_mode": len(active_bugs) > 0,
                "bugs": {
                    "unhandled_500_login": self.unhandled_500_login,
                    "slow_latency_products": self.slow_latency_products,
                    "schema_drift_product_detail": self.schema_drift_product_detail,
                    "flaky_503_orders": self.flaky_503_orders,
                    "malformed_json_profile": self.malformed_json_profile,
                    "state_leak_checkout": self.state_leak_checkout,
                },
                "checkout_invocations": self.checkout_invocations,
                "endpoint_hits": dict(self.endpoint_hits),
            }


def get_demo_config() -> DemoApiConfig:
    """Singleton getter for DemoApiConfig."""
    return DemoApiConfig()
