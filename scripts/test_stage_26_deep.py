"""Comprehensive manual and edge-case testing for Stage 26: Platform Self-Testing."""
import json
import requests
import sys

BASE_URL = "http://127.0.0.1:8000/api/v1/self-test"

def run_tests():
    print("=== Testing Stage 26: Platform Self-Testing Suite ===")
    
    # 1. GET /suites
    print("\n--- 1. Testing GET /api/v1/self-test/suites ---")
    r = requests.get(f"{BASE_URL}/suites")
    print(f"Status Code: {r.status_code}")
    suites = r.json()
    print(f"Suites Count: {len(suites)}")
    for s in suites:
        print(f"  Suite: {s['id']} -> {s['name']} ({s['test_files_count']} files, ~{s['estimated_tests']} tests)")
    assert r.status_code == 200
    assert len(suites) >= 5

    # 2. POST /run - Core Foundation Subsystem
    print("\n--- 2. Testing POST /api/v1/self-test/run (Subsystem: core_foundation) ---")
    payload = {
        "subsystem": "core_foundation",
        "stop_on_first_error": False,
        "include_tracebacks": True
    }
    r = requests.post(f"{BASE_URL}/run", json=payload)
    print(f"Status Code: {r.status_code}")
    res = r.json()
    print(f"Run ID: {res['run_id']}, Verdict: {res['verdict']}, Pass Rate: {res['pass_rate']}%")
    print(f"Total: {res['total_tests']}, Passed: {res['passed']}, Failed: {res['failed']}, Errors: {res['errors']}")
    print(f"Duration: {res['total_duration_ms']:.2f}ms")
    assert r.status_code == 200
    assert res['verdict'] == "ALL_PASSED"
    assert res['total_tests'] > 0
    assert res['failed'] == 0

    # 3. POST /run - Validation Engine Subsystem
    print("\n--- 3. Testing POST /api/v1/self-test/run (Subsystem: validation_engine) ---")
    payload = {
        "subsystem": "validation_engine",
        "stop_on_first_error": False,
        "include_tracebacks": False
    }
    r = requests.post(f"{BASE_URL}/run", json=payload)
    print(f"Status Code: {r.status_code}")
    res = r.json()
    print(f"Run ID: {res['run_id']}, Verdict: {res['verdict']}, Pass Rate: {res['pass_rate']}%")
    print(f"Total: {res['total_tests']}, Passed: {res['passed']}")
    assert r.status_code == 200
    assert res['verdict'] == "ALL_PASSED"

    # 4. POST /run - Execution Engine Subsystem
    print("\n--- 4. Testing POST /api/v1/self-test/run (Subsystem: execution_engine) ---")
    payload = {
        "subsystem": "execution_engine",
        "stop_on_first_error": True,
        "include_tracebacks": True
    }
    r = requests.post(f"{BASE_URL}/run", json=payload)
    print(f"Status Code: {r.status_code}")
    res = r.json()
    print(f"Run ID: {res['run_id']}, Verdict: {res['verdict']}, Pass Rate: {res['pass_rate']}%")
    assert r.status_code == 200
    assert res['verdict'] == "ALL_PASSED"

    # 5. POST /run - Analysis & AI Subsystem
    print("\n--- 5. Testing POST /api/v1/self-test/run (Subsystem: analysis_ai) ---")
    payload = {
        "subsystem": "analysis_ai",
        "stop_on_first_error": False,
        "include_tracebacks": True
    }
    r = requests.post(f"{BASE_URL}/run", json=payload)
    print(f"Status Code: {r.status_code}")
    res = r.json()
    print(f"Run ID: {res['run_id']}, Verdict: {res['verdict']}, Pass Rate: {res['pass_rate']}%")
    assert r.status_code == 200
    assert res['verdict'] == "ALL_PASSED"

    # 6. POST /run - Resilience, Data & Audit Subsystem
    print("\n--- 6. Testing POST /api/v1/self-test/run (Subsystem: resilience_data_audit) ---")
    payload = {
        "subsystem": "resilience_data_audit",
        "stop_on_first_error": False,
        "include_tracebacks": True
    }
    r = requests.post(f"{BASE_URL}/run", json=payload)
    print(f"Status Code: {r.status_code}")
    res = r.json()
    print(f"Run ID: {res['run_id']}, Verdict: {res['verdict']}, Pass Rate: {res['pass_rate']}%")
    assert r.status_code == 200
    assert res['verdict'] == "ALL_PASSED"

    # 7. POST /run - Full Suite
    print("\n--- 7. Testing POST /api/v1/self-test/run (Subsystem: full_suite) ---")
    payload = {
        "subsystem": "full_suite",
        "stop_on_first_error": False,
        "include_tracebacks": True
    }
    r = requests.post(f"{BASE_URL}/run", json=payload)
    print(f"Status Code: {r.status_code}")
    res = r.json()
    print(f"Run ID: {res['run_id']}, Verdict: {res['verdict']}, Pass Rate: {res['pass_rate']}%")
    print(f"Subsystems Breakdown:")
    for sub in res['subsystems_breakdown']:
        print(f"  - {sub['subsystem']:<24}: {sub['status']} ({sub['passed']}/{sub['total_tests']} passed, {sub['pass_rate']}%) in {sub['duration_ms']:.1f}ms")
    assert r.status_code == 200
    assert res['verdict'] == "ALL_PASSED"
    assert len(res['subsystems_breakdown']) == 5

    # 8. GET /latest
    print("\n--- 8. Testing GET /api/v1/self-test/latest ---")
    r = requests.get(f"{BASE_URL}/latest")
    print(f"Status Code: {r.status_code}")
    latest = r.json()
    print(f"Latest Run ID: {latest['run_id']}, Verdict: {latest['verdict']}, Executed At: {latest['executed_at']}")
    assert r.status_code == 200
    assert latest['run_id'] == res['run_id']

    # 9. GET /matrix
    print("\n--- 9. Testing GET /api/v1/self-test/matrix ---")
    r = requests.get(f"{BASE_URL}/matrix")
    print(f"Status Code: {r.status_code}")
    matrix = r.json()
    print(f"Overall System Status: {matrix['overall_system_status']}")
    print(f"Total Subsystems: {matrix['total_subsystems']}, Healthy: {matrix['healthy_subsystems']}")
    for s in matrix['subsystems']:
        print(f"  - {s['subsystem']:<24}: Status={s['status']}, Pass Rate={s['pass_rate']}%")
    assert r.status_code == 200
    assert matrix['overall_system_status'] == "HEALTHY"
    assert matrix['healthy_subsystems'] == 5

    # 10. Edge Cases & Validation Errors
    print("\n--- 10. Testing Edge Cases & Invalid Inputs ---")
    # Invalid subsystem enum
    r_bad_sub = requests.post(f"{BASE_URL}/run", json={"subsystem": "invalid_subsystem_name"})
    print(f"Invalid Subsystem Status Code: {r_bad_sub.status_code} (Expected 422)")
    assert r_bad_sub.status_code == 422

    # Empty payload (defaults to full_suite)
    r_empty = requests.post(f"{BASE_URL}/run", json={})
    print(f"Empty Payload Status Code: {r_empty.status_code} (Expected 200 default full_suite)")
    assert r_empty.status_code == 200

    print("\n[SUCCESS] All Stage 26 platform self-testing tests and edge cases passed successfully!")

if __name__ == "__main__":
    run_tests()
