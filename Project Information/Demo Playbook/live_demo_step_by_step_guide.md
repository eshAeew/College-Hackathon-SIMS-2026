# API Sentinel — Live Demo Step-by-Step Presenter Guide
**14-Step Presentation Walkthrough for Live Demos & Evaluations**

---

## 🚀 Pre-Demo Checklist
1. **Start Backend Server**: `uvicorn app.main:app --reload --port 8000`
2. **Open Browser Tab**: `http://127.0.0.1:8000/` (Dark Cyber Dashboard)
3. **Open Secondary Browser Tab**: `http://127.0.0.1:8000/docs` (Interactive Swagger UI)
4. **Terminal Window Ready**: Open PowerShell in project root for CLI demonstration (`scripts/run_demo_story.py`).

---

## 📋 The 14-Step Live Demo Execution Flow

| Step | Phase | Action / Endpoint | Visual Expectation | Presenter Narration Point |
|---|---|---|---|---|
| **01** | Initialization | Load Dashboard (`GET /`) | Dark Cyber UI with 4 KPI cards and neon accents | *"Welcome to API Sentinel — here is the unified telemetry cockpit."* |
| **02** | Ingestion | Open OpenAPI Ingestion Modal | JSON/YAML spec editor appears | *"We import our OpenAPI 3.1 contract for Alpha Commerce."* |
| **03** | Discovery | Submit Spec (`POST /api/v1/projects/1/openapi/import`) | 6 endpoints extracted with method badges | *"Sentinel maps every route and parameters automatically."* |
| **04** | Synthesis | Auto-generate Test Cases | 9 scenarios created (happy, negative, security) | *"Combinatorial mutation generates full test suites in seconds."* |
| **05** | Config | View Assertions Configuration | Status code, latency SLA (1000ms), schema checks | *"Assertions verify status codes, JSON schema, and SLA limits."* |
| **06** | Review | Inspect Test Catalog | Grouped by endpoint with tags | *"Tests ready for concurrent execution."* |
| **07** | Phase 1 Exec | Click 'Run Test Suite' (`POST /api/v1/demo/execute-phase-1`) | Progress bar fills -> Run summary displays 6 failures | *"Executing against live target with active runtime defects."* |
| **08** | Defect Discovery | View Failure Badges & SLA Breaches | Red badges on Login, Catalog, Detail, Orders, Profile, Cart | *"6 multi-vector defects detected across 6 distinct categories."* |
| **09** | Telemetry | Inspect Failure Evidence Package | Headers, sanitized payload, latency graph | *"Deterministic telemetry captures exact failure context."* |
| **10** | AI Analysis | Click 'AI Root Cause Analysis' | Gemini analysis card slides out | *"AI explains root cause and generates reproducible cURL."* |
| **11** | Remediation | Inspect Code Snippet | Python/FastAPI validation patch displayed | *"Actionable copy-paste fix provided directly to developer."* |
| **12** | Fix Target | Apply Fixes (`POST /api/v1/demo/apply-fixes`) | Toast: 'All 6 Target API Flaws Resolved' | *"Applying backend patches to demo store."* |
| **13** | Phase 2 Exec | Click 'Re-run Verification' (`POST /api/v1/demo/execute-phase-2`) | 100% Pass Rate (9/9) in green | *"Verification run completes with zero failures."* |
| **14** | Diff & Export | Click 'Compare Runs' -> Export HTML | Side-by-side green diff + Dark Cyber HTML Report | *"Closed-loop proof of fix and standalone executive audit report."* |

---

## 💡 CLI Alternative (1-Command Presentation)
If presenting via terminal or CI/CD stage:
```bash
py -3.13 scripts/run_demo_story.py
```
This runs the entire 14-step presentation story in 2 seconds with formatted terminal tables and colored status highlights!
