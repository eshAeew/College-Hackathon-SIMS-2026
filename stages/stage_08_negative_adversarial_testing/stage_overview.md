# Stage 08: Negative & Adversarial Testing

## 1. Stage Overview
Automatically generate boundary-breaking test cases (empty bodies, invalid types, missing required keys) to expose backend validation flaws.

## 2. Key Objectives
- Establish robust architectural foundations for this component.
- Ensure strict adherence to the project technology boundary (FastAPI, SQLite, httpx, Pydantic).
- Deliver modular, testable, and maintainable services.

## 3. Sub-Stages Breakdown
- **[Sub-Stage 01: Payload Mutation & Fuzzing Generators](./sub_stage_01_mutation_generators/implementation_plan.md)**: Generate adversarial test payloads from valid baseline schemas (null values, empty strings, missing fields, type inversions).
- **[Sub-Stage 02: 4xx vs 500 Unhandled Exception Detector](./sub_stage_02_4xx_vs_500_leak_detection/implementation_plan.md)**: Flag API vulnerabilities where bad input causes HTTP 500 (Internal Server Error) instead of proper HTTP 400/422.
