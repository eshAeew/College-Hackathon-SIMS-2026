"""Command-line presentation runner for API Sentinel's 14-Step Demo Story."""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import SessionLocal
from app.services.demo_workflow_service import DemoWorkflowService


def main():
    parser = argparse.ArgumentParser(description="API Sentinel 14-Step Demo Story CLI Player")
    parser.add_argument("--auto", action="store_true", help="Run without pausing between steps")
    parser.add_argument("--json", action="store_true", help="Output final story in JSON format")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.json:
            story = DemoWorkflowService.run_complete_story(db)
            print(json.dumps(story.model_dump(), indent=2))
            return

        print("\n" + "=" * 76)
        print("  API SENTINEL --- 14-STEP AUTONOMOUS DEMO WORKFLOW & PITCH")
        print("  Case Study JP-009 --- Autonomous API Quality & Telemetry Engine")
        print("=" * 76 + "\n")

        story = DemoWorkflowService.run_complete_story(db)

        for step in story.steps:
            print(f"[{step.step_number}/{story.total_steps}] >>> {step.title.upper()}")
            print(f"  * Action:   {step.action}")
            print(f"  * Status:   {step.status}")
            print(f"  * Headline: {step.headline}")
            if step.key_findings:
                print("  * Key Findings:")
                for kf in step.key_findings:
                    print(f"      - {kf}")
            print("-" * 76)
            if not args.auto:
                time.sleep(0.5)

        print("\n" + "=" * 76)
        print("  DEMO STORY COMPLETED SUCCESSFULLY!")
        print(f"  * Phase 1 Baseline Run ID: #{story.phase_1_baseline_run_id} ({story.phase_1_failures_detected} Failures Detected)")
        print(f"  * Phase 2 Verification Run ID: #{story.phase_2_verification_run_id} (Pass Rate: {story.phase_2_pass_rate}%)")
        print(f"  * Regression Verdict: {story.regression_verdict}")
        print("=" * 76 + "\n")
    finally:
        db.close()


if __name__ == "__main__":
    main()
