# <div align="center">🛡️ API SENTINEL</div>
### <div align="center">Autonomous REST API Testing, Regression Detection & AI-Assisted Reliability Platform</div>

<div align="center">

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![SQLite](https://img.shields.io/badge/SQLite-3-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![Pydantic](https://img.shields.io/badge/Pydantic-v2-E92063?style=for-the-badge&logo=pydantic&logoColor=white)](https://docs.pydantic.dev/)
[![Google Gemini](https://img.shields.io/badge/Google%20Gemini-AI%20Diagnostic-8E75C2?style=for-the-badge&logo=googlegemini&logoColor=white)](https://ai.google.dev/)
[![Pytest](https://img.shields.io/badge/Pytest-Testing%20Suite-0A9EDC?style=for-the-badge&logo=pytest&logoColor=white)](https://docs.pytest.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)

<br/>

<p align="center">
  <a href="https://skillicons.dev">
    <img src="https://skillicons.dev/icons?i=py,fastapi,sqlite,docker,git,github,vscode,postman" />
  </a>
</p>

**Case Study:** `JP-009` &bull; **Category:** Developer Infrastructure & Automated QA &bull; **Event:** College Hackathon SIMS 2026

</div>

---

## 📌 Table of Contents
- [Executive Overview](#-executive-overview)
- [The Problem vs Our Solution](#-the-problem-vs-our-solution)
- [System Architecture](#-system-architecture)
- [Core Capabilities & Features](#-core-capabilities--features)
- [How AI Is Implemented (Testing-First Principle)](#-how-ai-is-implemented-testing-first-principle)
- [Intentionally Flawed Demo Target API](#-intentionally-flawed-demo-target-api)
- [28-Stage Implementation Roadmap](#-28-stage-implementation-roadmap)
- [Technology Stack Matrix](#-technology-stack-matrix)
- [Directory Structure](#-directory-structure)
- [Quick Start Guide](#-quick-start-guide)
- [3-Minute Live Hackathon Demo Script](#-3-minute-live-hackathon-demo-script)
- [Contributing & Team](#-contributing--team)
- [License](#-license)

---

## 🌟 Executive Overview

**API Sentinel** is a lightweight, continuous API reliability platform. Unlike passive API clients (such as Postman or Insomnia), API Sentinel functions as an **automated QA engineer**. 

A developer points API Sentinel to their REST API (or imports an OpenAPI 3.0 specification), and Sentinel systematically:
1. Executes configurable functional, adversarial, and boundary test scenarios.
2. Validates status codes, headers, response schemas, and strict data types.
3. Detects non-deterministic intermittent behavior (flakiness) and latency regressions.
4. Identifies recurring failure patterns across historical test runs.
5. Synthesizes structured failure evidence and delivers **actionable AI-assisted root-cause explanations and code fixes**.

---

## ⚡ The Problem vs Our Solution

| The Manual Status Quo (Postman/Curl) | The API Sentinel Solution |
| :--- | :--- |
| ❌ Manually craft requests, send, and inspect JSON by eye | ✅ **1-Click OpenAPI Import & Automatic Test Generation** |
| ❌ Only tests the "happy path" (valid inputs $\rightarrow$ 200 OK) | ✅ **Automated Adversarial Fuzzing** (detects unhandled 500 crashes on bad input) |
| ❌ Misses intermittent 503s or non-deterministic behavior | ✅ **Multi-Execution Entropy & Flakiness Analyzer** |
| ❌ Developers don't notice latency regressions until production | ✅ **P50 / P95 / P99 Latency Benchmarking with SLA Alerting** |
| ❌ Raw error stack traces confuse junior developers | ✅ **Evidence-Driven AI Root-Cause Diagnosis & Code Fixes** |

---

## 🏗️ System Architecture

```text
                      ┌─────────────────────────────────────────┐
                      │            Developer / User             │
                      └────────────────────┬────────────────────┘
                                           │
                                           ▼
                      ┌─────────────────────────────────────────┐
                      │       Web Interface / Dashboard         │
                      └────────────────────┬────────────────────┘
                                           │ (REST API / JSON)
                                           ▼
                      ┌─────────────────────────────────────────┐
                      │           FastAPI Backend Core          │
                      └────────────────────┬────────────────────┘
                                           │
         ┌─────────────────────────────────┼─────────────────────────────────┐
         ▼                                 ▼                                 ▼
┌──────────────────┐              ┌──────────────────┐              ┌──────────────────┐
│ Project & Spec   │              │ Test Suite       │              │ Test Run         │
│ Manager          │              │ Orchestrator     │              │ Manager          │
└────────┬─────────┘              └────────┬─────────┘              └────────┬─────────┘
         │                                 │                                 │
         │                                 ▼                                 │
         │                        ┌──────────────────┐                       │
         │                        │ Async HTTP Core  │                       │
         │                        │ (httpx / asyncio)│                       │
         │                        └────────┬─────────┘                       │
         │                                 │                                 │
         │                                 ▼                                 │
         │                        ┌──────────────────┐                       │
         │                        │ Validator Engine │                       │
         │                        │ (Status, Schema) │                       │
         │                        └────────┬─────────┘                       │
         │                                 │                                 │
         │                                 ▼                                 │
         │                        ┌──────────────────┐                       │
         │                        │ Performance &    │                       │
         │                        │ Flakiness Stats  │                       │
         │                        └────────┬─────────┘                       │
         │                                 │                                 │
         │                                 ▼                                 │
         │                        ┌──────────────────┐                       │
         │                        │ Failure Analyzer │                       │
         │                        │ (Structured DTO) │                       │
         │                        └────────┬─────────┘                       │
         │                                 │                                 │
         │                                 ▼                                 │
         │                        ┌──────────────────┐                       │
         │                        │ AI Recommender   │                       │
         │                        │ (Gemini/Fallback)│                       │
         │                        └────────┬─────────┘                       │
         │                                 │                                 │
         └─────────────────────────────────┼─────────────────────────────────┘
                                           ▼
                              ┌─────────────────────────┐
                              │  SQLite Database Store  │
                              └─────────────────────────┘
```

---

## 🚀 Core Capabilities & Features

### 1. 🔍 Multi-Layer Deterministic Validation
* **HTTP Status Code Assertion:** Exact matching or range assertions (e.g. `[200, 201]`).
* **Content-Type & Header Verification:** Ensures strict compliance (`application/json`, `application/xml`).
* **JSON Schema & Data-Type Validator:** Detects missing required fields, extraneous keys, and type discrepancies (`expected int, received str`).

### 2. 💣 Adversarial & Negative Fuzzing
* Programmatically mutates valid schemas: null injections, empty strings, missing mandatory keys, and type inversions.
* **500 Server Crash Leak Detection:** Automatically flags backend vulnerabilities where bad inputs cause unhandled `500 Internal Server Error` instead of proper `400 Bad Request` or `422 Unprocessable Entity`.

### 3. ⏱️ Performance & Latency Analytics
* Records sub-millisecond network timings across every execution.
* Calculates statistical percentiles: **Min, Max, Mean, Median (P50), P95, and P99**.
* Configurable SLA thresholds: **Fast (<200ms)**, **Acceptable (200-500ms)**, **Slow (500-1000ms)**, and **Critical SLA Breach (>1000ms)**.

### 4. 📉 Regression & Inconsistent Behavior Tracking
* **Historical Delta Comparator:** Compares current run results against baseline runs to catch newly introduced regressions.
* **Flakiness & Jitter Engine:** Executes repeated requests under identical payloads to detect status-code variance and intermittent 503 errors.

### 5. 📑 OpenAPI 3.0 / Swagger Ingestion
* Ingests JSON/YAML OpenAPI specifications, extracting paths, parameters, request bodies, and response contracts in seconds.
* Automatically synthesizes complete test suites ready for immediate execution.

---

## 🤖 How AI Is Implemented (Testing-First Principle)

> **Golden Rule:** AI never decides if an API test passed or failed. The deterministic Python engine handles 100% of the testing logic. AI is an expert assistant called **only after evidence is gathered**.

```text
[Deterministic Test Engine]
         │
         ▼ (Catches Failure: POST /login -> 500 Internal Server Error)
[Evidence Packager Aggregates Diagnostic DTO]
         │ (Payload, Status, Traceback, Headers, Latency)
         ▼
[LLM Prompt Synthesizer Formats Context]
         │
         ├──────────────────────────────┬──────────────────────────────┐
         ▼ (Online: Gemini API)         ▼ (Offline / No API Key)       ▼
[Google Gemini 2.5 Flash]     [Rule-Based Heuristic Matcher]           │
         │                              │                              │
         └──────────────────────────────┴──────────────────────────────┘
                                        │
                                        ▼
                         [Structured Remediation Card]
                         {
                           "likely_cause": "Unhandled KeyError on 'password'",
                           "severity": "HIGH",
                           "suggested_fix": "Add Pydantic schema validation",
                           "code_snippet": "class LoginRequest(BaseModel): ..."
                         }
```

---

## 🎯 Intentionally Flawed Demo Target API

To showcase API Sentinel live during hackathon judging, we include an **Intentionally Flawed REST API** (Mock E-Commerce Service) with 6 deliberate, real-world bugs:

| Endpoint | Method | Injected Deliberate Bug | Sentinel Detection Feature |
| :--- | :--- | :--- | :--- |
| `/api/auth/login` | `POST` | **Missing Validation**: Unhandled `KeyError` throws **HTTP 500** | Negative Testing & 500 Leak Detector |
| `/api/products` | `GET` | **Sluggish Query**: Injected `1.8s` latency spike | Performance SLA Threshold Violation |
| `/api/products/{id}` | `GET` | **Schema Inconsistency**: Price returned as string `"29.99 USD"`, missing `stock` | JSON Schema & Type Validator |
| `/api/orders` | `POST` | **Flakiness / Gateway Jitter**: Intermittent **HTTP 503** (40% rate) | Inconsistent Behavior & Entropy Analyzer |
| `/api/users/profile` | `GET` | **Malformed Payload**: Truncated/corrupted JSON string | Response Parser & Format Validator |
| `/api/cart/checkout` | `POST` | **State Leak Regression**: Fails on 2nd consecutive run | Regression Testing Engine |

---

## 🗺️ 28-Stage Implementation Roadmap

The project is structured into **28 modular stages** spanning 7 phases:

```text
PHASE A: FOUNDATION & WORKSPACE
├── [Stage 01] Project Foundation (FastAPI, Env, Logging, Healthchecks)
├── [Stage 02] Project & Workspace Management (Project CRUD, Multi-environment)
├── [Stage 03] API Endpoint Management (Endpoint Registration, Path/Method Specs)
└── [Stage 04] Request Configuration Engine (HTTP Builder, Parameter Interpolation)

PHASE B: CORE EXECUTION & DATA LAYER
├── [Stage 05] Core API Execution Engine (httpx Async Dispatcher, Telemetry)
├── [Stage 06] Test Case Management (Test Scenarios, Assertions)
├── [Stage 07] Functional Validation Engine (Status, JSON Schema, Types)
└── [Stage 23] Persistence & Database Layer (SQLAlchemy Models, SQLite Repos)

PHASE C: INTELLIGENCE & BEHAVIORAL ANALYSIS
├── [Stage 08] Negative & Adversarial Testing (Payload Fuzzing, 500 Leak Detector)
├── [Stage 09] Inconsistent Behavior Detection (Multi-run Flakiness Analyzer)
├── [Stage 10] Performance Analysis (Latency P50/P95/P99, SLA Rules)
├── [Stage 11] Recurring Failure Detection (Historical Clustering)
└── [Stage 13] Regression Testing Engine (Historical Delta Comparator)

PHASE D: AUTOMATION & SPECIFICATION SUPPORT
├── [Stage 14] OpenAPI Specification Support (OpenAPI 3.0/Swagger JSON & YAML Parser)
└── [Stage 15] Automatic Test Generation (Happy Path & Negative Suite Generator)

PHASE E: SAFETY, CLASSIFICATION & AI DIAGNOSIS
├── [Stage 16] Safety & Execution Controls (Target Whitelisting, Method Safeguards)
├── [Stage 17] Result Classification Engine (PASS/FAIL/WARN/ERROR Matrix, Severity)
├── [Stage 18] Failure Analysis Engine (Evidence DTO Packager, Root-Cause Categorizer)
└── [Stage 19] AI Recommendation Layer (Gemini API Integration + Heuristic Fallback)

PHASE F: RUN MANAGEMENT & UI/UX
├── [Stage 12] Test Run Management (Suite Orchestrator, Lifecycle State Machine)
├── [Stage 20] Dashboard & Web Interface (Global KPI Cards, Endpoint Inspector)
├── [Stage 21] Run Comparison & Diff Tool (Side-by-Side Comparator, Visual Diff)
└── [Stage 22] Reporting & Export (Executive Summary, Standalone HTML/PDF Export)

PHASE G: HARDENING, SELF-TESTING & DEMO SHOWCASE
├── [Stage 24] Error Handling & Resilience (Global Exception Filters, Circuit Breakers)
├── [Stage 25] Logging, Tracing & Auditability (Structured JSON Logs, cURL Replay)
├── [Stage 26] Platform Self-Testing Suite (Pytest Unit & E2E Pipeline Tests)
├── [Stage 27] Intentionally Flawed Demo API (Mock E-Commerce Service + 6 Bugs)
└── [Stage 28] Final Demo Workflow & Presentation (3-Minute Live Pitch Playbook)
```

---

## 🛠️ Technology Stack Matrix

| Component | Technology | Role |
| :--- | :--- | :--- |
| **Backend Core** | `Python 3.11+` & `FastAPI` | Asynchronous REST backend framework |
| **HTTP Engine** | `httpx` & `asyncio` | High-concurrency non-blocking HTTP client |
| **Validation** | `Pydantic v2` & `jsonschema` | Strict schema validation and contract matching |
| **Database** | `SQLite 3` with `SQLAlchemy 2.0` | Portable relational storage with zero external setup |
| **AI Diagnostics** | `Google Gemini API` (`google-genai`) | Root-cause analysis & code remediation engine |
| **Fallback Engine** | `Rule-Based Heuristic Matcher` | 100% offline diagnostic fallback |
| **Testing** | `pytest`, `pytest-asyncio`, `coverage`| Comprehensive self-testing framework |
| **Documentation** | `Jinja2` & `PyYAML` | Exportable HTML/PDF reports & OpenAPI spec parser |

---

## 📂 Directory Structure

```text
.
├── Project Information/
│   ├── Prompt/
│   │   ├── about_project.md                     # Case study prompt & vision
│   │   └── project_stages.md                    # Comprehensive 28-stage breakdown
│   ├── Specifications & Architecture/
│   │   ├── architecture_overview.md             # High-level architecture & diagram
│   │   ├── tech_stack_specification.md          # Approved case-study tech stack
│   │   ├── database_schema_design.md            # SQLite ERD & data models
│   │   ├── demo_api_specification.md            # 6 Injected bugs specification
│   │   └── ai_recommendation_system.md          # AI evidence packaging & fallback
│   └── Project update - current status/
│       ├── current_status.md                    # Real-time milestone tracker
│       ├── stage_progress_tracker.md            # Matrix of all 28 stages
│       └── changelog.md                         # Chronological update logs
│
├── stages/                                      # 28 Modular Stage Directories
│   ├── stage_01_project_foundation/
│   ├── stage_02_project_workspace_management/
│   ├── ...
│   └── stage_28_final_demo_workflow_and_presentation/
│
├── .gitignore
└── README.md
```

---

## ⚡ Quick Start Guide

### Prerequisites
* Python 3.11 or higher
* Git

### 1. Clone the Repository
```bash
git clone https://github.com/eshAeew/College-Hackathon-SIMS-2026.git
cd College-Hackathon-SIMS-2026
```

### 2. Create and Activate Virtual Environment
```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment
```bash
cp .env.example .env
# Edit .env with your optional GEMINI_API_KEY (System works offline if omitted)
```

### 5. Launch API Sentinel
```bash
uvicorn app.main:app --reload --port 8000
```
Open **`http://localhost:8000/docs`** to explore the interactive API.

---

## 🎬 3-Minute Live Hackathon Demo Script

```text
[00:00 - 00:30] THE PROBLEM
"Every team has dozens of endpoints. Manually testing them with Postman after each commit is slow, 
misses edge cases, and lets regressions slip through to production."

[00:30 - 01:00] 1-CLICK IMPORT & TEST GENERATION
Upload openapi.json -> Sentinel automatically creates 30+ happy-path and adversarial test cases.

[01:00 - 01:45] RUN SUITE & PROVE BUGS (DETERMINISTIC FACTS)
Click 'Run Test Suite' -> Sentinel flags:
- POST /auth/login -> HTTP 500 (Missing input validation crash)
- GET /products    -> 1.8s latency (SLA threshold warning)
- POST /orders     -> 503 error (Intermittent flakiness detected)

[01:45 - 02:30] AI DIAGNOSIS & REMEDIATION
Click 'Explain Failure' -> AI analyzes evidence and provides exact Pydantic validation code to fix the 500 crash.

[02:30 - 03:00] VERIFY & REGRESSION COMPARISON
Fix the demo API -> Re-run -> Showcase green test report with clear Before vs After regression comparison!
```

---

## 👥 Contributing & Team
* **Project Name:** API Sentinel
* **Hackathon:** College Hackathon SIMS 2026
* **Repository:** [https://github.com/eshAeew/College-Hackathon-SIMS-2026](https://github.com/eshAeew/College-Hackathon-SIMS-2026)

---

## 📜 License
Distributed under the **MIT License**. See `LICENSE` for more information.
