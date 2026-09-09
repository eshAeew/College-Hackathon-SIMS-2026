# Sub-Stage 01: Structured Diagnostic Evidence Packager — Implementation Plan

## 1. Objective
Collect and package request payload, response status, headers, body, latency, and assertion failure details into a structured JSON DTO.

## 2. Technical Specification & Architecture
Built `app/utils/evidence_packager.py` and `FailureAnalysisService`; evidence is exposed at `POST /api/v1/failure-analysis/package` and `GET /api/v1/results/{id}/evidence`.

## 3. Step-by-Step Implementation Tasks
- [x] Extract failed assertion criteria (e.g. Expected 400, Got 500).
- [x] Format request parameters and request body neatly.
- [x] Capture server response body and response headers.
- [x] Include failure history context (e.g., failed 3 times previously).

## 4. Edge Cases & Fault Tolerance
- [x] Credential-bearing headers are redacted, bodies truncate at 2000 chars, and malformed stored evidence JSON degrades to an empty dict rather than raising.

## 5. Verification & Testing Checklist
- [x] Tests in `tests/test_stages_18_to_21.py` cover masking, truncation, cURL generation, history ratings, and the full API surface.

## 6. Definition of Done (DoD)
> **COMPLETED**: Every test failure is transformed into a standardized, self-contained diagnostic evidence package.
