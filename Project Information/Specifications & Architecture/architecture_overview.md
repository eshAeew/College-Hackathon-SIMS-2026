# API Sentinel — Architecture Overview

## 1. Executive Summary
**API Sentinel (Case Study JP-009)** is an automated REST API testing, regression detection, and reliability platform designed for developers and QA teams. It unites a **high-throughput deterministic execution engine** (for repeatable HTTP verification) with an **evidence-driven AI recommendation layer** (for root-cause diagnosis and code fix suggestions).

## 2. Architectural Diagram
```text
                      +-------------------------+
                      |    Developer / User     |
                      +------------+------------+
                                   |
                                   v
                      +-------------------------+
                      |   Web UI / Dashboard    |
                      +------------+------------+
                                   | (REST API / JSON)
                                   v
                      +-------------------------+
                      |   FastAPI Application   |
                      +------------+------------+
                                   |
         +-------------------------+-------------------------+
         |                         |                         |
         v                         v                         v
+------------------+      +------------------+      +------------------+
| Project / Spec   |      | Test Suite       |      | Test Run         |
| Manager          |      | Orchestrator     |      | Manager          |
+--------+---------+      +--------+---------+      +--------+---------+
         |                         |                         |
         |                         v                         |
         |                +------------------+               |
         |                | Async HTTP Core  |               |
         |                | (httpx / asyncio)|               |
         |                +--------+---------+               |
         |                         |                         |
         |                         v                         |
         |                +------------------+               |
         |                | Validator Engine |               |
         |                | (Status, Schema) |               |
         |                +--------+---------+               |
         |                         |                         |
         |                         v                         |
         |                +------------------+               |
         |                | Performance &    |               |
         |                | Inconsistency    |               |
         |                +--------+---------+               |
         |                         |                         |
         |                         v                         |
         |                +------------------+               |
         |                | Failure Analyzer |               |
         |                | (Evidence DTO)   |               |
         |                +--------+---------+               |
         |                         |                         |
         |                         v                         |
         |                +------------------+               |
         |                | AI Recommender   |               |
         |                | (Gemini/Fallback)|               |
         |                +--------+---------+               |
         |                         |                         |
         +-------------------------+-------------------------+
                                   |
                                   v
                      +-------------------------+
                      | SQLite Persistence Store|
                      +-------------------------+
```

## 3. Core Design Principles
1. **Testing First, AI Second**: The deterministic engine validates status codes, headers, and schemas with 100% precision. AI never decides whether an API test passes or fails.
2. **Evidence-Driven AI**: When a failure occurs, the engine packages structured diagnostic evidence (payloads, status mismatches, tracebacks) and sends it to the AI for root-cause diagnosis.
3. **Zero-Flake Asynchronous Core**: Built with Python `asyncio` and `httpx` for high-concurrency non-blocking API probing.
4. **Full Offline Autonomy**: If the user lacks an LLM API key or runs in an isolated network, the built-in deterministic heuristic rule engine provides immediate remediation guidance.
