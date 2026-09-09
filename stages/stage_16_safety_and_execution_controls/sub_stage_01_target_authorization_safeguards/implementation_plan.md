# Sub-Stage 01: Target Authorization & Host Allowlisting — Implementation Plan

## 1. Objective
Prevent accidental testing against unauthorized external domains and enforce explicit target confirmations.

## 2. Technical Specification & Architecture
Host validation middleware ensuring tests only target authorized base URLs.

## 3. Step-by-Step Implementation Tasks
- [ ] Validate target base URLs against an allowlist of permitted domains/IPs.
- [ ] Provide explicit localhost and private network development modes.
- [ ] Display prominent 'Authorized Testing Only' advisory in UI.

## 4. Edge Cases & Fault Tolerance
- Validate all input parameters before execution.
- Ensure graceful handling of unexpected nulls or network disconnects.
- Return structured error responses adhering to the global error model.

## 5. Verification & Testing Checklist
- [ ] Unit tests written and passing with >90% coverage.
- [ ] FastAPI route documentation visible in Swagger UI (`/docs`).
- [ ] Integration verified with SQLite database.

## 6. Definition of Done (DoD)
> **Requests targeting non-whitelisted external hosts are blocked with a clear safety warning.**
