# Sub-Stage 02: Variance & Flakiness Analyzer — Implementation Plan

## 1. Objective
Compute status code entropy, response payload consistency, and latency variance across runs.

## 2. Technical Specification & Architecture
Statistical variance calculation and entropy-based flakiness score generator.

## 3. Step-by-Step Implementation Tasks
- [ ] Calculate pass/fail ratio across iterations.
- [ ] Detect status code switching (e.g., 200 -> 200 -> 503 -> 200).
- [ ] Flag endpoint as 'INCONSISTENT / FLAKY' if status variation > 0%.

## 4. Edge Cases & Fault Tolerance
- Validate all input parameters before execution.
- Ensure graceful handling of unexpected nulls or network disconnects.
- Return structured error responses adhering to the global error model.

## 5. Verification & Testing Checklist
- [ ] Unit tests written and passing with >90% coverage.
- [ ] FastAPI route documentation visible in Swagger UI (`/docs`).
- [ ] Integration verified with SQLite database.

## 6. Definition of Done (DoD)
> **Analyzer produces a flakiness score and warning tag for any endpoint displaying non-deterministic responses.**
