# Stage 21: Run Comparison & Diff Tool

## 1. Stage Overview
Compare two historical test runs side-by-side to visualize performance changes, newly failed tests, and fixed issues.

## 2. Key Objectives
- Establish robust architectural foundations for this component.
- Ensure strict adherence to the project technology boundary (FastAPI, SQLite, httpx, Pydantic).
- Deliver modular, testable, and maintainable services.

## 3. Sub-Stages Breakdown
- **[Sub-Stage 01: Side-by-Side Run Metrics Comparator](./sub_stage_01_side_by_side_run_comparator/implementation_plan.md)**: Provide comparison API and view contrasting metrics between Run A (Baseline) and Run B (Current).
- **[Sub-Stage 02: Visual Delta & Regression Inspector](./sub_stage_02_delta_visualizer/implementation_plan.md)**: Render intuitive visual diffs showing fixed bugs, newly introduced regressions, and latency shift charts.
