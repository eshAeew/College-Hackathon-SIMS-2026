# Sub-Stage 02: Project & Endpoint Drill-Down Views — Implementation Plan

## 1. Objective
Provide deep-dive views for individual projects, endpoints, test cases, and diagnostic detail pages with AI recommendations.

## 2. Technical Specification & Architecture
Project dashboard, endpoint inspector, and result detail views, each with a server-rendered template under `app/web/templates/`.

## 3. Step-by-Step Implementation Tasks
- [x] Build Project Detail view with endpoint list, OpenAPI importer, and 'Run All' button.
- [x] Build Endpoint Inspector view showing request config, assertion rules, and historical results.
- [x] Build Test Result Detail view displaying status, diffs, timing charts, and AI Recommendation card.

## 4. Edge Cases & Fault Tolerance
- [x] Missing projects, endpoints, and results return 404 rather than rendering a broken page.

## 5. Verification & Testing Checklist
- [x] Tests cover all three API views plus the four rendered `/ui` pages.

## 6. Definition of Done (DoD)
> **COMPLETED**: Developers can navigate from high-level project summaries down to individual test assertion diffs and AI fixes.
