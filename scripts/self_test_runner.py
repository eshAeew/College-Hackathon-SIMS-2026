import argparse
import json
import os
import sys
import time

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.models.schemas.self_test import SubsystemCategory
from app.services.self_test_service import SelfTestService


def main():
    parser = argparse.ArgumentParser(description="API Sentinel Platform Self-Testing CLI Runner")
    parser.add_argument(
        "--subsystem",
        choices=["core_foundation", "execution_engine", "validation_engine", "analysis_ai", "resilience_data_audit", "full_suite"],
        default="full_suite",
        help="Subsystem to target for self-testing",
    )
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    parser.add_argument("--failfast", action="store_true", help="Stop execution on first failure")
    args = parser.parse_args()

    sub_enum = SubsystemCategory(args.subsystem)
    report = SelfTestService.run_self_tests(
        subsystem=sub_enum,
        stop_on_first_error=args.failfast,
    )

    if args.json:
        print(json.dumps(report.model_dump(), indent=2))
        sys.exit(0 if report.verdict == "ALL_PASSED" else 1)

    # Pretty Console Output
    print("\n" + "=" * 70)
    print(f"  API SENTINEL --- PLATFORM SELF-TESTING SUITE [{report.run_id}]")
    print(f"  Target Subsystem: {report.subsystem.upper()}")
    print("=" * 70)
    print(f"  Verdict:       {report.verdict}")
    print(f"  Total Tests:   {report.total_tests}")
    print(f"  Passed:        {report.passed} ({report.pass_rate}%)")
    print(f"  Failed:        {report.failed}")
    print(f"  Errors:        {report.errors}")
    print(f"  Duration:      {report.total_duration_ms:.2f} ms")
    print("-" * 70)
    print("  SUBSYSTEM BREAKDOWN:")
    for sub in report.subsystems_breakdown:
        status_symbol = "[OK]" if sub.status == "HEALTHY" else "[WARN]"
        print(f"    * {sub.subsystem:<24} {status_symbol} {sub.passed}/{sub.total_tests} passed ({sub.pass_rate}%) in {sub.duration_ms:.1f}ms")
    print("=" * 70 + "\n")

    sys.exit(0 if report.verdict == "ALL_PASSED" else 1)


if __name__ == "__main__":
    main()
