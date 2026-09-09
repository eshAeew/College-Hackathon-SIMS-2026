# Sub-Stage 02: Injected Bug Scenarios & Toggle Controls — Implementation Plan

## 1. Objective
Inject 6 realistic bugs (Missing Validation 500, Sluggish Latency, Flaky 503, Schema Mismatch, Malformed JSON, Regression) with fix toggles.

## 2. Technical Specification & Architecture
Configurable bug injection switches allowing instant demonstrations of 'Buggy API' vs 'Fixed API'.

## 3. Step-by-Step Implementation Tasks
- [ ] Bug 1: `POST /auth/login` raises KeyError -> 500 when password missing.
- [ ] Bug 2: `GET /products` sleeps 1.8s exceeding 500ms SLA threshold.
- [ ] Bug 3: `GET /products/{id}` returns price as string and omits stock field.
- [ ] Bug 4: `POST /orders` intermittently returns 503 Service Unavailable (40% rate).
- [ ] Bug 5: `GET /users/profile` returns malformed JSON for specific IDs.
- [ ] Bug 6: Provide `/demo/fix-bugs` toggle endpoint to demonstrate before/after regression verification.

## 4. Edge Cases & Fault Tolerance
- Validate all input parameters before execution.
- Ensure graceful handling of unexpected nulls or network disconnects.
- Return structured error responses adhering to the global error model.

## 5. Verification & Testing Checklist
- [ ] Unit tests written and passing with >90% coverage.
- [ ] FastAPI route documentation visible in Swagger UI (`/docs`).
- [ ] Integration verified with SQLite database.

## 6. Definition of Done (DoD)
> **Mock API reliably reproduces all 6 bug scenarios to demonstrate Sentinel's automated detection powers.**
