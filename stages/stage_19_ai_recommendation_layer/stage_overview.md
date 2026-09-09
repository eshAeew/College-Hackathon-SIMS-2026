# Stage 19: AI Recommendation Layer

## 1. Stage Overview
Synthesize structured diagnostic evidence into prompt templates, invoke the LLM (Google Gemini API), and provide deterministic heuristic fallback.

## 2. Key Objectives
- Establish robust architectural foundations for this component.
- Ensure strict adherence to the project technology boundary (FastAPI, SQLite, httpx, Pydantic).
- Deliver modular, testable, and maintainable services.

## 3. Sub-Stages Breakdown
- **[Sub-Stage 01: LLM Prompt Synthesis & JSON Schema Enforcement](./sub_stage_01_structured_prompt_synthesizer/implementation_plan.md)**: Format structured failure evidence into a strict system/user prompt demanding structured JSON remediation responses.
- **[Sub-Stage 02: LLM Client Connector & Heuristic Fallback Engine](./sub_stage_02_llm_fix_recommendation_engine/implementation_plan.md)**: Call Google Gemini API (or OpenAI/custom endpoint) with graceful fallback to built-in rule-based recommendations when offline.
