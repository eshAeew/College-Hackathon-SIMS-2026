# Sub-Stage 02: Visual Delta & Regression Inspector — Implementation Plan

## 1. Objective
Render intuitive visual diffs showing fixed bugs, newly introduced regressions, and latency shift charts.

## 2. Technical Specification & Architecture
`DeltaVisualization` view-model with a six-badge strip, regression and improvement lists, latency shift, and a pass-rate series; rendered at `/ui/projects/{id}/compare`.

## 3. Step-by-Step Implementation Tasks
- [x] Render green badges for fixed tests and red badges for new regressions.
- [x] Render side-by-side response payload and status comparisons.
- [x] Display latency distribution shift indicators.

## 4. Edge Cases & Fault Tolerance
- [x] A regression whose current status code is 5xx is upgraded to a CRITICAL CRASH badge.

## 5. Verification & Testing Checklist
- [x] Tests assert the badge count, regression list contents, the crash badge, and that the compare page renders.

## 6. Definition of Done (DoD)
> **COMPLETED**: Developers can instantly see the exact impact of their backend code changes between test runs.
