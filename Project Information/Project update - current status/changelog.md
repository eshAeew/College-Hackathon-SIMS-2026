# API Sentinel — Changelog

## [Stage 01 - Sub-Stage 02] - 2026-09-09
- **Completed**: Configuration & Environment Management.
- Implemented `Settings` class using `pydantic-settings` in `app/core/config.py`.
- Added custom validation rules for `DATABASE_URL` (supporting SQLite and PostgreSQL) and `DEFAULT_TIMEOUT_SECONDS (>0)`.
- Implemented `@lru_cache` settings caching and `clear_settings_cache()` test helper.
- Added comprehensive `.env.example` template with complete field documentation.
- Added unit test suite in `tests/test_config.py` (6 tests passing).

## [Stage 01 - Sub-Stage 01] - 2026-09-09
- **Completed**: FastAPI Application Scaffolding.
- Created `app/` package architecture: `core/`, `api/v1/`, `models/schemas/`, `services/`, and `utils/`.
- Implemented `app/main.py` with CORS middleware, lifespan hooks, and validation error formatters.
- Implemented `StandardResponse[T]`, `ErrorResponse`, and `HealthStatus` Pydantic models.
- Added `/api/v1/health` and root identity `/` endpoints.
- Added `tests/test_main.py` verifying test suite passes with 100% success.
- Created `.env.example` and updated `requirements.txt`.

## [Initial Setup] - 2026-09-09
- Initialized comprehensive documentation repository in `Project Information/`.
- Created detailed Architecture Overview, Tech Stack Specification, Database Schema ERD, Demo API Specification, and AI Recommendation Architecture.
- Created real-time status tracker, stage progress matrix, and changelog.
- Established the modular 28-stage implementation framework under `stages/`.
