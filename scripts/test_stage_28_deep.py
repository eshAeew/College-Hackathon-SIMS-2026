"""Comprehensive in-depth test script for Stage 28: Final Demo Workflow & Pitch Playbook."""
import json
import requests

BASE_URL = "http://127.0.0.1:8000/api/v1/demo"

def run_deep_tests():
    print("=== Stage 28: Final Demo Workflow & Presentation Playbook Deep Verification ===")
    
    # 1. POST /bootstrap
    print("\n--- 1. Testing POST /api/v1/demo/bootstrap ---")
    r_boot = requests.post(f"{BASE_URL}/bootstrap")
    print(f"Status: {r_boot.status_code}")
    boot_data = r_boot.json()
    print(f"Project Name: {boot_data['project_name']} (ID: {boot_data['project_id']})")
    print(f"Endpoints Imported: {boot_data['endpoints_imported']}")
    print(f"Test Cases Created: {boot_data['test_cases_created']}")
    print(f"Status: {boot_data['status']}")
    assert r_boot.status_code == 200
    assert boot_data["status"] == "READY"
    assert boot_data["endpoints_imported"] >= 6
    assert boot_data["test_cases_created"] >= 9

    # 2. POST /execute-phase-1 (Flawed Target Baseline)
    print("\n--- 2. Testing POST /api/v1/demo/execute-phase-1 ---")
    r_p1 = requests.post(f"{BASE_URL}/execute-phase-1")
    print(f"Status: {r_p1.status_code}")
    p1_data = r_p1.json()
    print(f"Phase 1 Run ID: #{p1_data['run_id']}")
    print(f"Total Tests: {p1_data['total_tests']}, Passed: {p1_data['passed']}, Failed: {p1_data['failed']}")
    print(f"Pass Rate: {p1_data['pass_rate']}%")
    print(f"Detected Failures: {p1_data['detected_failures_count']}")
    for f in p1_data["detected_failures"]:
        print(f"  - [{f['failure_type']}] {f['test_name']} -> HTTP {f['actual_status_code']} ({f['latency_ms']:.1f}ms)")
    print(f"AI Recommendations Generated: {p1_data['ai_recommendations_count']}")
    assert r_p1.status_code == 200
    assert p1_data["failed"] >= 6
    assert p1_data["ai_recommendations_count"] >= 6

    # 3. POST /apply-fixes (Deploy Remediations)
    print("\n--- 3. Testing POST /api/v1/demo/apply-fixes ---")
    r_fixes = requests.post(f"{BASE_URL}/apply-fixes")
    print(f"Status: {r_fixes.status_code}, Body: {r_fixes.json()}")
    assert r_fixes.status_code == 200
    assert r_fixes.json()["status"] == "FIXES_APPLIED"

    # 4. POST /execute-phase-2 (Verification Run & Comparison Diff)
    print("\n--- 4. Testing POST /api/v1/demo/execute-phase-2 ---")
    r_p2 = requests.post(f"{BASE_URL}/execute-phase-2?baseline_run_id={p1_data['run_id']}")
    print(f"Status: {r_p2.status_code}")
    p2_data = r_p2.json()
    print(f"Verification Run ID: #{p2_data['verification_run_id']}")
    print(f"Total Tests: {p2_data['total_tests']}, Passed: {p2_data['passed']}, Failed: {p2_data['failed']}")
    print(f"Pass Rate: {p2_data['pass_rate']}%, Verdict: {p2_data['verdict']}")
    assert r_p2.status_code == 200
    assert p2_data["failed"] == 0
    assert p2_data["pass_rate"] == 100.0
    assert p2_data["verdict"] == "CLEAN_PASS"

    # 5. POST /run-complete-story (1-Click Autonomous Story)
    print("\n--- 5. Testing POST /api/v1/demo/run-complete-story ---")
    r_story = requests.post(f"{BASE_URL}/run-complete-story")
    print(f"Status: {r_story.status_code}")
    story_data = r_story.json()
    print(f"Story ID: {story_data['story_id']}")
    print(f"Total Steps: {story_data['total_steps']}, Completed: {story_data['completed_steps']}")
    print(f"Phase 1 Baseline Run ID: #{story_data['phase_1_baseline_run_id']} ({story_data['phase_1_failures_detected']} flaws detected)")
    print(f"Phase 2 Verification Run ID: #{story_data['phase_2_verification_run_id']} (Pass Rate: {story_data['phase_2_pass_rate']}%)")
    print(f"Regression Verdict: {story_data['regression_verdict']}")
    for s in story_data["steps"]:
        print(f"  [{s['step_number']}/{story_data['total_steps']}] {s['title']} -> {s['status']}")
        print(f"      Headline: {s['headline']}")
    assert r_story.status_code == 200
    assert story_data["regression_verdict"] == "ALL_BUGS_RESOLVED"
    assert story_data["phase_2_pass_rate"] == 100.0
    assert story_data["completed_steps"] == story_data["total_steps"]

    # 6. GET /playbook (3-Minute Live Hackathon Pitch Playbook)
    print("\n--- 6. Testing GET /api/v1/demo/playbook ---")
    r_pb = requests.get(f"{BASE_URL}/playbook")
    print(f"Status: {r_pb.status_code}")
    pb_data = r_pb.json()
    print(f"Title: {pb_data['title']}")
    print(f"Target Time Limit: {pb_data['target_time_limit']}")
    print(f"Pitch Timeline Sections ({len(pb_data['pitch_timeline'])}):")
    for sec in pb_data["pitch_timeline"]:
        print(f"  * [{sec['time_stamp']}] {sec['title']}")
        print(f"      UI Action: {sec['ui_action']}")
        print(f"      Takeaway:  {sec['key_takeaway']}")
    print(f"\nJudge Q&A Cheatsheet Items ({len(pb_data['judge_qa_cheatsheet'])}):")
    for qa in pb_data["judge_qa_cheatsheet"]:
        print(f"  * Q: {qa['question']}")
        print(f"    A: {qa['answer']}")
    assert r_pb.status_code == 200
    assert len(pb_data["pitch_timeline"]) == 5
    assert len(pb_data["judge_qa_cheatsheet"]) >= 4

    print("\n[SUCCESS] All Stage 28 demo workflow steps, 1-click execution, and pitch playbook validated successfully!")

if __name__ == "__main__":
    run_deep_tests()
