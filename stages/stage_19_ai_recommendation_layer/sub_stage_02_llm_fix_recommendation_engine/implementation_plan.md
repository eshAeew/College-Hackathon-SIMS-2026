# Sub-Stage 02: LLM Client Connector & Heuristic Fallback Engine — Implementation Plan

## 1. Objective
Call Google Gemini API (or OpenAI/custom endpoint) with graceful fallback to built-in rule-based recommendations when offline.

## 2. Technical Specification & Architecture
`AIRecommendationService` calls `gemini-2.5-flash` in JSON mode when a key and SDK are present and falls back to `app/utils/heuristic_recommender.py` otherwise; records persist to `ai_recommendations`.

## 3. Step-by-Step Implementation Tasks
- [x] Implement `GoogleGenAI` client calling `gemini-2.5-flash` with JSON response mode.
- [x] Implement rule-based fallback heuristics for offline or missing API key scenarios.
- [x] Store generated recommendations in `AIRecommendation` database table.

## 4. Edge Cases & Fault Tolerance
- [x] Missing SDK, missing key, network failure, rate limiting, and malformed model JSON all fall back to the deterministic engine instead of failing the request.

## 5. Verification & Testing Checklist
- [x] Tests confirm offline mode reports RULE_BASED_HEURISTIC, returns a CRITICAL card with a code snippet, and both persists and lists recommendations.

## 6. Definition of Done (DoD)
> **COMPLETED**: System produces high-quality, actionable developer recommendations in both online (AI) and offline (rule-based) modes.
