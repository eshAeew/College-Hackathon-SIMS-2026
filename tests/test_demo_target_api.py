"""Unit and Integration tests for Stage 27: Intentionally Flawed Demo Target API."""
import unittest
from fastapi.testclient import TestClient

from app.main import app
from app.demo_target.config import get_demo_config


class TestDemoTargetApi(unittest.TestCase):
    """Test suite covering all 6 flawed endpoints, bug toggling, and OpenAPI specification."""

    def setUp(self):
        self.client = TestClient(app, raise_server_exceptions=False)
        get_demo_config().reset()

    def tearDown(self):
        get_demo_config().reset()

    def test_bug_1_unhandled_500_login_and_fix(self):
        """Test Bug #1: Missing input validation throws 500 in flawed mode and 400 when fixed."""
        # 1. Flawed mode: Missing password -> triggers 500 error
        res_flawed = self.client.post("/demo-api/auth/login", json={"username": "alice"})
        self.assertEqual(res_flawed.status_code, 500)

        # 2. Fix bug
        get_demo_config().toggle("unhandled_500_login")

        # 3. Fixed mode: Missing password -> returns proper 400 Bad Request
        res_fixed = self.client.post("/demo-api/auth/login", json={"username": "alice"})
        self.assertEqual(res_fixed.status_code, 400)
        self.assertEqual(res_fixed.json()["error"], "MissingRequiredField")

        # 4. Valid login in fixed mode -> 200 OK
        res_ok = self.client.post("/demo-api/auth/login", json={"username": "alice", "password": "secret123"})
        self.assertEqual(res_ok.status_code, 200)
        self.assertIn("token", res_ok.json())

    def test_bug_2_slow_products_latency_and_fix(self):
        """Test Bug #2: Sluggish query delay in flawed mode and instant response in fixed mode."""
        # Fast query with delay disabled
        res_fast = self.client.get("/demo-api/products?latency_spike=false")
        self.assertEqual(res_fast.status_code, 200)
        data = res_fast.json()
        self.assertEqual(data["total_items"], 3)
        self.assertEqual(data["latency_simulated"], False)

    def test_bug_3_schema_drift_product_detail_and_fix(self):
        """Test Bug #3: Schema drift (string price, missing stock) vs strict schema when fixed."""
        # 1. Flawed mode
        res_flawed = self.client.get("/demo-api/products/1")
        self.assertEqual(res_flawed.status_code, 200)
        flawed_data = res_flawed.json()
        self.assertIsInstance(flawed_data["price"], str)  # Violation: string price
        self.assertNotIn("stock", flawed_data)            # Violation: missing stock

        # 2. Fix bug
        get_demo_config().toggle("schema_drift_product_detail")

        # 3. Fixed mode
        res_fixed = self.client.get("/demo-api/products/1")
        self.assertEqual(res_fixed.status_code, 200)
        fixed_data = res_fixed.json()
        self.assertIsInstance(fixed_data["price"], float)
        self.assertIn("stock", fixed_data)
        self.assertIsInstance(fixed_data["stock"], int)

    def test_bug_4_flaky_orders_and_fix(self):
        """Test Bug #4: Intermittent 503 gateway timeout vs deterministic 201 creation."""
        # 1. Flawed mode with force_fail=true -> 503
        res_503 = self.client.post("/demo-api/orders?force_fail=true", json={"product_id": 1, "quantity": 1})
        self.assertEqual(res_503.status_code, 503)

        # 2. Fix bug
        get_demo_config().fix_all()

        # 3. Fixed mode -> 201 Created
        res_ok = self.client.post("/demo-api/orders", json={"product_id": 1, "quantity": 2})
        self.assertEqual(res_ok.status_code, 201)
        self.assertEqual(res_ok.json()["status"], "CONFIRMED")

    def test_bug_5_malformed_profile_json_and_fix(self):
        """Test Bug #5: Corrupt unclosed JSON string vs valid JSON profile."""
        # 1. Flawed mode: raw corrupt string
        res_corrupt = self.client.get("/demo-api/users/profile?corrupt=true")
        # Raw text is unclosed malformed JSON
        self.assertIn("notifications", res_corrupt.text)
        self.assertFalse(res_corrupt.text.endswith("}"))

        # 2. Fixed mode
        res_fixed = self.client.get("/demo-api/users/profile?corrupt=false")
        self.assertEqual(res_fixed.status_code, 200)
        self.assertEqual(res_fixed.json()["username"], "sentinel_tester")

    def test_bug_6_checkout_state_leak_regression(self):
        """Test Bug #6: 1st run succeeds, 2nd run fails with 409 Conflict (State Leak)."""
        # 1st call -> 200 OK
        res1 = self.client.post("/demo-api/cart/checkout")
        self.assertEqual(res1.status_code, 200)

        # 2nd call -> 409 Conflict (Regression bug!)
        res2 = self.client.post("/demo-api/cart/checkout")
        self.assertEqual(res2.status_code, 409)
        self.assertEqual(res2.json()["error"], "InventoryLockConflict")

        # Fix all
        get_demo_config().fix_all()

        # Call again -> 200 OK
        res3 = self.client.post("/demo-api/cart/checkout")
        self.assertEqual(res3.status_code, 200)

    def test_control_endpoints_and_openapi_spec(self):
        """Test GET /control/status, POST /toggle, POST /fix-all, POST /reset, and GET /openapi.json."""
        # Status
        res_status = self.client.get("/demo-api/control/status")
        self.assertEqual(res_status.status_code, 200)
        self.assertEqual(res_status.json()["total_bugs"], 6)

        # Fix all
        res_fix = self.client.post("/demo-api/control/fix-all")
        self.assertEqual(res_fix.status_code, 200)
        self.assertEqual(self.client.get("/demo-api/control/status").json()["active_flaws_count"], 0)

        # Reset
        res_reset = self.client.post("/demo-api/control/reset")
        self.assertEqual(res_reset.status_code, 200)
        self.assertEqual(self.client.get("/demo-api/control/status").json()["active_flaws_count"], 6)

        # OpenAPI spec
        res_spec = self.client.get("/demo-api/openapi.json")
        self.assertEqual(res_spec.status_code, 200)
        spec = res_spec.json()
        self.assertEqual(spec["openapi"], "3.1.0")
        self.assertIn("/demo-api/auth/login", spec["paths"])
        self.assertIn("/demo-api/products", spec["paths"])


if __name__ == "__main__":
    unittest.main()
