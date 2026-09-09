# API Sentinel — Demo Target API Specification

## 1. Overview
To demonstrate API Sentinel live during hackathon judging, we build an **Intentionally Flawed REST API** (Mock E-Commerce Service) that showcases the platform's diagnostic capabilities.

## 2. Injected Bugs & Flaws Catalog

| Endpoint | Method | Expected Behavior | Injected Deliberate Bug | Sentinel Detection Feature |
| :--- | :--- | :--- | :--- | :--- |
| `/api/auth/login` | POST | Validates payload, returns 400 on missing password | **Missing Input Validation**: Throws unhandled Python `KeyError` causing **HTTP 500** | Negative Testing & 500 Leak Detector |
| `/api/products` | GET | Returns product list within 200ms | **Simulated Sluggish Query**: Injected `asyncio.sleep(1.8)` latency spike | Performance SLA Threshold & Alerting |
| `/api/products/{id}` | GET | Returns product JSON with `id: int`, `price: float` | **Schema Inconsistency**: Returns `price` as string `"29.99 USD"` and missing `stock` field | Response Schema & Type Validator |
| `/api/orders` | POST | Creates order idempotently | **Intermittent Gateway Flakiness**: Randomly throws **HTTP 503** in 40% of calls | Inconsistent Behavior & Flakiness Analyzer |
| `/api/users/profile` | GET | Returns structured user JSON | **Malformed JSON Payload**: Returns invalid truncated JSON string on specific IDs | Format & Parser Validator |
| `/api/cart/checkout` | POST | Deducts cart and returns 200 | **Regression Bug**: Fails on 2nd consecutive run due to unhandled state leak | Regression Testing Engine |
