# API Sentinel — Technology Stack Specification

## 1. Approved Technology Matrix (Case Study Compliant)
In strict compliance with the JP-009 case study guidelines, the following stack is specified:

| Layer | Technology | Rationale & Responsibility |
| :--- | :--- | :--- |
| **Backend Core** | **Python 3.11+ / FastAPI** | High-performance async REST API framework with native OpenAPI schema generation and Pydantic validation. |
| **HTTP Client** | **`httpx` & `asyncio`** | Non-blocking HTTP/1.1 & HTTP/2 client supporting connection pooling, timeouts, and custom certificate handling. |
| **Data Validation** | **Pydantic v2 & `jsonschema`** | Strict type enforcement, request/response validation, and JSON Schema specification matching. |
| **Persistence / DB** | **SQLite with SQLAlchemy / SQLModel** | Zero-configuration, file-based relational database ideal for fast local execution and artifact portability. |
| **AI Recommendation** | **Google Gemini API (`google-genai`) / LLM REST Client** | Contextual failure analysis and code remediation generation. |
| **AI Fallback** | **Rule-Based Heuristics Engine** | Deterministic keyword/pattern matching for 100% offline reliability. |
| **Frontend / UI** | **Modern Responsive Web UI (HTML5, TailwindCSS / React)** | Interactive test suite manager, latency charts, real-time run logs, and diff inspectors. |
| **Testing Engine** | **`pytest`, `pytest-asyncio`, `coverage`** | Comprehensive self-testing framework verifying all validation and execution engines. |

## 2. Dependency Manifest (`requirements.txt`)
```text
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
pydantic>=2.8.0
pydantic-settings>=2.4.0
httpx>=0.27.0
sqlalchemy>=2.0.30
jsonschema>=4.23.0
pyyaml>=6.0.2
google-genai>=0.1.1
pytest>=8.3.0
pytest-asyncio>=0.24.0
python-multipart>=0.0.9
jinja2>=3.1.4
```
