# Sub-Stage 01: LLM Prompt Synthesis & JSON Schema Enforcement — Implementation Plan

## 1. Objective
Format structured failure evidence into a strict system/user prompt demanding structured JSON remediation responses.

## 2. Technical Specification & Architecture
`app/utils/prompt_synthesizer.py` builds the system/user prompt pair and publishes the JSON schema the model must satisfy; exposed at `POST /api/v1/ai/synthesize-prompt`.

## 3. Step-by-Step Implementation Tasks
- [x] Create system prompt enforcing JSON output format with `likely_cause`, `severity`, `suggested_fix`, `code_snippet`.
- [x] Inject formatted failure evidence into prompt context.
- [x] Validate that prompts stay concise and cost-effective.

## 4. Edge Cases & Fault Tolerance
- [x] The system prompt forbids the model from restating pass/fail, caps evidence excerpts to keep prompts cost-effective, and returns a token estimate with every prompt.

## 5. Verification & Testing Checklist
- [x] Tests assert the JSON contract keys, the EVIDENCE block, a positive token estimate, and the explicit instruction never to state whether the test passed or failed.

## 6. Definition of Done (DoD)
> **COMPLETED**: Prompt synthesizer reliably builds structured prompts formatted for LLM completion.
