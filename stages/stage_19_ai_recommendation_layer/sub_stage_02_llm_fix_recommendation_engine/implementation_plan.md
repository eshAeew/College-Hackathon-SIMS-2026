# Sub-Stage 02: LLM Client Connector & Heuristic Fallback Engine — Implementation Plan

## 1. Objective
Call Google Gemini API (or OpenAI/custom endpoint) with graceful fallback to built-in rule-based recommendations when offline.

## 2. Technical Specification & Architecture
Dual-mode recommendation service: LLM client + local rule-based heuristic matcher.

## 3. Step-by-Step Implementation Tasks
- [ ] Implement `GoogleGenAI` client calling `gemini-2.5-flash` with JSON response mode.
- [ ] Implement rule-based fallback heuristics for offline or missing API key scenarios.
- [ ] Store generated recommendations in `AIRecommendation` database table.

## 4. Edge Cases & Fault Tolerance
- Validate all input parameters before execution.
- Ensure graceful handling of unexpected nulls or network disconnects.
- Return structured error responses adhering to the global error model.

## 5. Verification & Testing Checklist
- [ ] Unit tests written and passing with >90% coverage.
- [ ] FastAPI route documentation visible in Swagger UI (`/docs`).
- [ ] Integration verified with SQLite database.

## 6. Definition of Done (DoD)
> **System produces high-quality, actionable developer recommendations in both online (AI) and offline (rule-based) modes.**
