# Sub-Stage 02: 4xx vs 500 Unhandled Exception Detector — Implementation Plan

## 1. Objective
Flag API vulnerabilities where bad input causes HTTP 500 (Internal Server Error) instead of proper HTTP 400/422.

## 2. Technical Specification & Architecture
Classification heuristic distinguishing proper client rejection from unhandled server crashes.

## 3. Step-by-Step Implementation Tasks
- [x] Identify tests marked as `is_negative_test`.
- [x] Assert that server returns 4xx (400, 422, 401, 403, 404).
- [x] Tag any 500/502/503 response as 'CRITICAL: Unhandled Server Exception / Missing Validation'.

## 4. Edge Cases & Fault Tolerance
- Validate all input parameters before execution.
- Ensure graceful handling of unexpected nulls or network disconnects.
- Return structured error responses adhering to the global error model.

## 5. Verification & Testing Checklist
- [x] Unit tests written and passing with >90% coverage.
- [x] FastAPI route documentation visible in Swagger UI (`/docs`).
- [x] Integration verified with SQLite database.

## 6. Definition of Done (DoD)
> **Engine accurately catches and highlights whenever invalid user input crashes the target backend.**
