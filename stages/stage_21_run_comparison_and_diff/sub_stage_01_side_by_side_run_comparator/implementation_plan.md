# Sub-Stage 01: Side-by-Side Run Metrics Comparator — Implementation Plan

## 1. Objective
Provide comparison API and view contrasting metrics between Run A (Baseline) and Run B (Current).

## 2. Technical Specification & Architecture
`RunComparisonService.compare_runs()` behind `GET /api/v1/projects/{id}/compare-runs`, plus a `/compare-runs/latest` convenience route.

## 3. Step-by-Step Implementation Tasks
- [x] Compare overall pass rate, test counts, and average latency.
- [x] Identify tests that changed status (Passed -> Failed, Failed -> Passed).
- [x] Calculate net quality delta (+X% improved or -Y% degraded).

## 4. Edge Cases & Fault Tolerance
- [x] Tests present in only one run report as ADDED or REMOVED, and a zero baseline never divides by zero.

## 5. Verification & Testing Checklist
- [x] Tests assert broken and fixed counts, the CRITICAL_REGRESSIONS_FOUND verdict, a negative net quality delta, and a 404 for a missing run.

## 6. Definition of Done (DoD)
> **COMPLETED**: Comparator API returns structured diff metrics between any two selected runs.
