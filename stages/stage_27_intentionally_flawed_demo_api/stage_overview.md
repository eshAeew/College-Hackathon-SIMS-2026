# Stage 27: Intentionally Flawed Demo Target API

## 1. Stage Overview
Build an independent mock REST API (Mock E-Commerce Service) with 6 deliberate, realistic bugs for live hackathon demonstrations.

## 2. Key Objectives
- Establish robust architectural foundations for this component.
- Ensure strict adherence to the project technology boundary (FastAPI, SQLite, httpx, Pydantic).
- Deliver modular, testable, and maintainable services.

## 3. Sub-Stages Breakdown
- **[Sub-Stage 01: Mock E-Commerce Service Endpoints](./sub_stage_01_mock_ecommerce_endpoints/implementation_plan.md)**: Create realistic REST endpoints for Authentication (`/auth/login`), Catalog (`/products`), Orders (`/orders`), and Profile (`/users/profile`).
- **[Sub-Stage 02: Injected Bug Scenarios & Toggle Controls](./sub_stage_02_injected_deliberate_bugs/implementation_plan.md)**: Inject 6 realistic bugs (Missing Validation 500, Sluggish Latency, Flaky 503, Schema Mismatch, Malformed JSON, Regression) with fix toggles.
