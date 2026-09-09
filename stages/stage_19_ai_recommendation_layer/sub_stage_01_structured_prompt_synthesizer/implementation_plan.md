# Sub-Stage 01: LLM Prompt Synthesis & JSON Schema Enforcement — Implementation Plan

## 1. Objective
Format structured failure evidence into a strict system/user prompt demanding structured JSON remediation responses.

## 2. Technical Specification & Architecture
Prompt template synthesizer with strict Pydantic response schema constraints.

## 3. Step-by-Step Implementation Tasks
- [ ] Create system prompt enforcing JSON output format with `likely_cause`, `severity`, `suggested_fix`, `code_snippet`.
- [ ] Inject formatted failure evidence into prompt context.
- [ ] Validate that prompts stay concise and cost-effective.

## 4. Edge Cases & Fault Tolerance
- Validate all input parameters before execution.
- Ensure graceful handling of unexpected nulls or network disconnects.
- Return structured error responses adhering to the global error model.

## 5. Verification & Testing Checklist
- [ ] Unit tests written and passing with >90% coverage.
- [ ] FastAPI route documentation visible in Swagger UI (`/docs`).
- [ ] Integration verified with SQLite database.

## 6. Definition of Done (DoD)
> **Prompt synthesizer reliably builds structured prompts formatted for LLM completion.**
