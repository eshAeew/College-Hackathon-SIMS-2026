"""Comprehensive in-depth test script for Stage 27: Intentionally Flawed Demo Target API."""
import json
import time
import requests

BASE_URL = "http://127.0.0.1:8000/demo-api"

def run_deep_tests():
    print("=== Stage 27: Intentionally Flawed Demo Target API Deep Verification ===")
    
    # 0. Reset to Flawed State
    print("\n--- 0. Resetting Demo API to Flawed Mode ---")
    r = requests.post(f"{BASE_URL}/control/reset")
    print(f"Reset Status: {r.status_code}, Body: {r.json()}")
    assert r.status_code == 200

    r_status = requests.get(f"{BASE_URL}/control/status")
    status_data = r_status.json()
    print(f"Initial State: {status_data['active_flaws_count']}/{status_data['total_bugs']} flaws active")
    assert status_data["active_flaws_count"] == 6

    # 1. Bug #1: Missing Input Validation -> 500 Server Crash vs 400 Fixed
    print("\n--- 1. Testing Bug #1: POST /demo-api/auth/login ---")
    # Flawed mode: Missing password triggers uncaught KeyError -> 500
    r_500 = requests.post(f"{BASE_URL}/auth/login", json={"username": "alice"})
    print(f"[Flawed] Missing Password -> Status: {r_500.status_code} (Expected 500)")
    assert r_500.status_code == 500

    # Toggle Bug #1 to Fixed
    r_tog1 = requests.post(f"{BASE_URL}/control/toggle/unhandled_500_login")
    print(f"Toggled Bug #1: {r_tog1.json()}")
    assert r_tog1.json()["is_active"] == False

    # Fixed mode: Missing password -> 400 Bad Request
    r_400 = requests.post(f"{BASE_URL}/auth/login", json={"username": "alice"})
    print(f"[Fixed] Missing Password -> Status: {r_400.status_code}, Body: {r_400.json()} (Expected 400)")
    assert r_400.status_code == 400
    assert r_400.json()["error"] == "MissingRequiredField"

    # Fixed mode: Valid credentials -> 200 OK
    r_login_ok = requests.post(f"{BASE_URL}/auth/login", json={"username": "alice", "password": "secret123"})
    print(f"[Fixed] Valid Login -> Status: {r_login_ok.status_code}, Token: {r_login_ok.json()['token']}")
    assert r_login_ok.status_code == 200

    # 2. Bug #2: Sluggish Performance / Latency Spike (>1.2s) vs <5ms Fast
    print("\n--- 2. Testing Bug #2: GET /demo-api/products ---")
    # Flawed mode (default delay active)
    t0 = time.perf_counter()
    r_slow = requests.get(f"{BASE_URL}/products?latency_spike=true")
    slow_dur = (time.perf_counter() - t0) * 1000
    print(f"[Flawed] Injected SLA Breach -> Status: {r_slow.status_code}, Duration: {slow_dur:.1f}ms (Expected >= 1200ms)")
    assert r_slow.status_code == 200
    assert slow_dur >= 1100

    # Fixed mode (instant)
    t0 = time.perf_counter()
    r_fast = requests.get(f"{BASE_URL}/products?latency_spike=false")
    fast_dur = (time.perf_counter() - t0) * 1000
    print(f"[Fixed] Optimized Query -> Status: {r_fast.status_code}, Duration: {fast_dur:.1f}ms (Expected < 50ms)")
    assert r_fast.status_code == 200
    assert fast_dur < 100

    # 3. Bug #3: Schema Drift / Inversion (price as string, missing stock)
    print("\n--- 3. Testing Bug #3: GET /demo-api/products/1 ---")
    # Flawed mode:
    r_drift = requests.get(f"{BASE_URL}/products/1")
    print(f"[Flawed] Schema Drift -> Status: {r_drift.status_code}, Payload: {r_drift.json()}")
    assert r_drift.status_code == 200
    flawed_prod = r_drift.json()
    assert isinstance(flawed_prod["price"], str)
    assert "stock" not in flawed_prod

    # Toggle Bug #3 to Fixed
    requests.post(f"{BASE_URL}/control/toggle/schema_drift_product_detail")
    r_fixed_prod = requests.get(f"{BASE_URL}/products/1")
    print(f"[Fixed] Strict Schema -> Status: {r_fixed_prod.status_code}, Payload: {r_fixed_prod.json()}")
    assert r_fixed_prod.status_code == 200
    fixed_prod = r_fixed_prod.json()
    assert isinstance(fixed_prod["price"], (int, float))
    assert isinstance(fixed_prod["available"], bool)
    assert isinstance(fixed_prod["stock"], int)

    # 4. Bug #4: Flaky 503 Gateway Timeout vs Deterministic 201 Created
    print("\n--- 4. Testing Bug #4: POST /demo-api/orders ---")
    # Flawed mode with force_fail=true -> 503
    r_503 = requests.post(f"{BASE_URL}/orders?force_fail=true", json={"product_id": 1, "quantity": 1})
    print(f"[Flawed] Flaky Gateway Timeout -> Status: {r_503.status_code}, Content: {r_503.text.strip()}")
    assert r_503.status_code == 503

    # Toggle Bug #4 to Fixed
    requests.post(f"{BASE_URL}/control/toggle/flaky_503_orders")
    r_201 = requests.post(f"{BASE_URL}/orders", json={"product_id": 1, "quantity": 2})
    print(f"[Fixed] Deterministic Order Creation -> Status: {r_201.status_code}, Body: {r_201.json()}")
    assert r_201.status_code == 201
    assert r_201.json()["status"] == "CONFIRMED"

    # 5. Bug #5: Malformed Corrupted JSON vs Clean User Profile
    print("\n--- 5. Testing Bug #5: GET /demo-api/users/profile ---")
    # Flawed mode with corrupt=true
    r_corrupt = requests.get(f"{BASE_URL}/users/profile?corrupt=true")
    print(f"[Flawed] Raw Content: {r_corrupt.text}")
    print(f"[Flawed] Content-Type: {r_corrupt.headers.get('content-type')}")
    is_malformed = False
    try:
        r_corrupt.json()
    except Exception as e:
        is_malformed = True
        print(f"[Flawed] JSON parse failed as expected: {e}")
    assert is_malformed == True

    # Fixed mode
    r_clean_prof = requests.get(f"{BASE_URL}/users/profile?corrupt=false")
    print(f"[Fixed] Profile JSON: {r_clean_prof.json()}")
    assert r_clean_prof.status_code == 200
    assert r_clean_prof.json()["username"] == "sentinel_tester"

    # 6. Bug #6: State Leak & Regression Bug on Cart Checkout
    print("\n--- 6. Testing Bug #6: POST /demo-api/cart/checkout ---")
    requests.post(f"{BASE_URL}/control/reset")
    # 1st execution -> Success 200
    r_chk1 = requests.post(f"{BASE_URL}/cart/checkout")
    print(f"[Flawed - Run #1] First Checkout -> Status: {r_chk1.status_code}, Body: {r_chk1.json()}")
    assert r_chk1.status_code == 200

    # 2nd execution -> Regression Conflict 409
    r_chk2 = requests.post(f"{BASE_URL}/cart/checkout")
    print(f"[Flawed - Run #2] Subsequent Checkout -> Status: {r_chk2.status_code}, Body: {r_chk2.json()}")
    assert r_chk2.status_code == 409
    assert r_chk2.json()["error"] == "InventoryLockConflict"

    # Fix all and verify state is cleared
    requests.post(f"{BASE_URL}/control/fix-all")
    r_chk3 = requests.post(f"{BASE_URL}/cart/checkout")
    r_chk4 = requests.post(f"{BASE_URL}/cart/checkout")
    print(f"[Fixed - Run #1] Checkout -> Status: {r_chk3.status_code}")
    print(f"[Fixed - Run #2] Checkout -> Status: {r_chk4.status_code}")
    assert r_chk3.status_code == 200
    assert r_chk4.status_code == 200

    # 7. Control Endpoints & Telemetry
    print("\n--- 7. Testing Control & Telemetry APIs ---")
    r_final_status = requests.get(f"{BASE_URL}/control/status")
    print(f"Final Status: {json.dumps(r_final_status.json(), indent=2)}")
    assert r_final_status.json()["active_flaws_count"] == 0

    # Test toggling non-existent bug flag -> 400 Bad Request
    r_bad_toggle = requests.post(f"{BASE_URL}/control/toggle/non_existent_bug_flag")
    print(f"Invalid Toggle Status: {r_bad_toggle.status_code} (Expected 400)")
    assert r_bad_toggle.status_code == 400

    # 8. OpenAPI Specification Endpoint
    print("\n--- 8. Testing GET /demo-api/openapi.json ---")
    r_spec = requests.get(f"{BASE_URL}/openapi.json")
    print(f"OpenAPI Spec Status: {r_spec.status_code}")
    spec = r_spec.json()
    print(f"OpenAPI Version: {spec.get('openapi')}")
    print(f"Paths Documented: {list(spec.get('paths', {}).keys())}")
    assert r_spec.status_code == 200
    assert len(spec.get("paths", {})) >= 6

    print("\n[SUCCESS] All Stage 27 demo target API endpoints, bug injection flows, toggles, and edge cases passed 100%!")

if __name__ == "__main__":
    run_deep_tests()
