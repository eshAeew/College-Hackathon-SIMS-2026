# API Sentinel — Changelog

## [Stage 02 - Sub-Stage 02] - 2026-09-09
- **Completed**: Workspace Metadata & Summary Stats.
- Created `ProjectSummaryResponse` and `EnvironmentPreset` schemas in `app/models/schemas/project.py`.
- Implemented `get_project_summary()` calculation in `app/services/project_service.py`.
- Created `GET /api/v1/projects/{id}/summary` endpoint delivering real-time health score, auth headers detection, and environment presets.
- Added tests in `tests/test_projects.py`. Total test count: 23 passing.
- Marked Stage 02: Project / Workspace Management as 100% COMPLETE.

## [Stage 02 - Sub-Stage 01] - 2026-09-09
- **Completed**: Project & Workspace CRUD Operations.
- Created `app/core/database.py` with SQLAlchemy engine, `SessionLocal`, `Base`, and `get_db` dependency.
- Created `Project` entity model in `app/models/entities/project.py`.
- Created Pydantic request/response schemas in `app/models/schemas/project.py`.
- Implemented `ProjectService` business logic in `app/services/project_service.py`.
- Implemented `/api/v1/projects` REST endpoints (`POST`, `GET`, `GET /{id}`, `PUT /{id}`, `DELETE /{id}`).
- Added unit & database integration test suite in `tests/test_projects.py` (7 tests passing).
- Total test count increased to 21 with 100% pass rate.

## [Stage 01 - Sub-Stage 03] - 2026-09-09
- **Completed**: Structured Logging & Health Check Probe.
- Implemented `JSONLogFormatter` and `ConsoleLogFormatter` with context variable Request-ID support in `app/core/logging.py`.
- Implemented `RequestCorrelationMiddleware` attaching `X-Request-ID` and `X-Response-Time-Ms` in `app/core/middleware.py`.
- Enhanced `/api/v1/health` diagnostic probe returning uptime, database connection state, environment, and AI engine status.
- Added unit test suite in `tests/test_logging_and_health.py` (4 tests passing).
- All 13 unit tests across Stage 01 passing cleanly. Stage 01 is now 100% COMPLETE.

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
