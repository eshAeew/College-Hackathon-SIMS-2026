# API Sentinel — Changelog

## [Stage 05 - Sub-Stage 01] - 2026-09-09
- **Completed**: Asynchronous HTTP Dispatcher & Connection Pooling.
- Created `app/core/http_client.py` managing a shared `httpx.AsyncClient` connection pool (`Limits(max_connections=50, max_keepalive_connections=20)`), default timeouts, and startup/shutdown lifecycle hooks.
- Integrated `init_async_client()` and `close_async_client()` into FastAPI `lifespan` in `app/main.py`.
- Created Pydantic DTO schemas in `app/models/schemas/execution.py`:
  - `ExecutionOptions`: Configurable request timeout, follow redirects toggle, max redirects, and SSL verification enforcement.
  - `DirectExecutionRequest`: Full specification for ad-hoc HTTP executions.
  - `EndpointExecutionRequest`: Specification for stored endpoint executions with runtime overrides.
  - `ExecutionResultResponse`: Telemetry-rich result schema capturing HTTP status code, status text, response headers, parsed/raw body, elapsed latency (ms), redirect counts, and network exception details.
  - `ClientInfoResponse`: Connection pool and diagnostic info schema.
- Implemented `HttpDispatcherService` in `app/services/http_dispatcher.py`:
  - `dispatch_httpx_request()`: Asynchronous dispatch with per-request timeout via `extensions["timeout"]`, redirect tracking, SSL controls, and non-crashing network exception handlers (`TimeoutException`, `ConnectError`, `SSLError`, `TooManyRedirects`).
  - `dispatch_direct()`: Pre-flight safety check, request compilation, and async dispatch for ad-hoc requests.
  - `dispatch_endpoint()`: Workspace and endpoint resolution from SQLite DB with runtime overrides, pre-flight safety check, and async dispatch.
- Implemented REST API endpoints in `app/api/v1/executions.py`:
  - `POST /api/v1/executions/dispatch`
  - `POST /api/v1/projects/{project_id}/endpoints/{endpoint_id}/execute`
  - `GET /api/v1/executions/client-info`
- Mounted `executions_router` in `app/api/v1/api.py`.
- Added comprehensive unit and integration test suite in `tests/test_async_http_dispatcher.py` (11 new tests passing).
- Total test suite count increased to 74 passing tests with 100% pass rate.

## [Stage 04 - Sub-Stage 02] - 2026-09-09
- **Completed**: Pre-flight Syntax & Configuration Validation (Stage 04 Complete).
- Created `app/utils/preflight_validator.py` with standalone and composite pre-flight validation utilities:
  - `validate_url_syntax()`: Scheme verification (`http`/`https`), host/domain format checking, and port range validation (`1-65535`).
  - `validate_path_parameters()`: Token parsing and unfulfilled path placeholder detection.
  - `validate_body_syntax()`: Content-Type alignment, JSON parse validation, and form-data format checking.
  - `validate_headers_syntax()`: ASCII/ISO-8859-1 enforcement, header name character checks, and forbidden header detection (e.g., `Host`).
  - `execute_preflight_check()`: Composite analyzer aggregating blocking `errors` and non-blocking `warnings`.
- Added `PreflightValidationRequest` and `PreflightValidationReport` DTO schemas in `app/models/schemas/request_config.py`.
- Extended `RequestBuilderService` in `app/services/request_builder_service.py` with `validate_preflight()` and `validate_endpoint_preflight()`.
- Implemented Pre-flight Validation REST endpoints in `app/api/v1/requests.py`:
  - `POST /api/v1/requests/preflight-check`
  - `POST /api/v1/projects/{project_id}/endpoints/{endpoint_id}/preflight-check`
- Added comprehensive unit and integration test suite in `tests/test_preflight_validation.py` (8 new tests passing).
- Total test suite count increased to 63 passing tests with 100% pass rate.
- Marked Stage 04: Dynamic Request Configuration Engine as 100% COMPLETE.

## [Stage 04 - Sub-Stage 01] - 2026-09-09
- **Completed**: Dynamic HTTP Request Builder & Payload Serializers.
- Created `app/models/schemas/request_config.py` with `BodyType`, `RequestCompileOverride`, `DirectRequestBuilderRequest`, and `CompiledRequestResponse` DTOs.
- Created `RequestBuilderService` in `app/services/request_builder_service.py` with:
  - Path variable interpolation and URL-encoding (`resolve_path()`).
  - Query parameter encoding with support for lists, booleans, and special characters (`encode_query_params()`).
  - Hierarchical, case-insensitive header merging with standard defaults (`merge_headers()`).
  - Multi-format body serializer for JSON, form-data, raw text/XML, and empty bodies (`serialize_body()`).
  - Automated cURL command generator (`generate_curl_command()`).
  - Concrete `httpx.Request` constructor (`build_httpx_request()`).
- Implemented Request Configuration REST APIs in `app/api/v1/requests.py`:
  - `POST /api/v1/projects/{project_id}/endpoints/{endpoint_id}/build-request`
  - `POST /api/v1/requests/build`
- Added comprehensive unit and integration test suite in `tests/test_request_builder.py` (10 new tests passing).
- Total test suite count increased to 55 passing tests with 100% pass rate.

## [Stage 03 - Sub-Stage 02] - 2026-09-09
- **Completed**: Parameter, Header & Body Contracts Specification (Stage 03 Complete).
- Created `app/utils/contract_parser.py` with `extract_path_variables()`, `validate_json_schema()`, and `validate_contract_specification()`.
- Added `response_schema_json` column and getter/setter to `Endpoint` entity model in `app/models/entities/endpoint.py`.
- Added `response_schema`, `ContractSpecification`, `ContractUpdateRequest`, `ContractValidationRequest`, and `ContractValidationResponse` DTOs in `app/models/schemas/endpoint.py`.
- Enhanced `EndpointService` in `app/services/endpoint_service.py` with `get_endpoint_contract()` and `update_endpoint_contract()`.
- Added contract inspection, updating, and ad-hoc validation endpoints to `app/api/v1/endpoints.py`:
  - `GET /api/v1/endpoints/{endpoint_id}/contract`
  - `PUT /api/v1/endpoints/{endpoint_id}/contract`
  - `POST /api/v1/endpoints/validate-contract`
- Added comprehensive unit and integration test suite in `tests/test_contract_spec.py` (8 new tests passing).
- Total test suite count increased to 45 passing tests with 100% pass rate.
- Marked Stage 03: API Endpoint Management as 100% COMPLETE.

## [Stage 03 - Sub-Stage 01] - 2026-09-09
- **Completed**: Endpoint Registration & CRUD Operations.
- Created `Endpoint` entity model in `app/models/entities/endpoint.py` with cascade foreign key to `Project` and JSON serializers for headers, query params, path params, and body schema.
- Added `endpoints` relationship to `Project` model in `app/models/entities/project.py`.
- Created Pydantic DTOs in `app/models/schemas/endpoint.py` (`HTTPMethod`, `EndpointBase`, `EndpointCreate`, `EndpointUpdate`, `EndpointDuplicate`, `EndpointResponse`) with `/` path validation and HTTP method validation.
- Implemented `EndpointService` in `app/services/endpoint_service.py` supporting creation, pagination, query filtering by `is_active`, updates, deletion, duplication/cloning, and active state toggle.
- Updated `ProjectService.get_project_summary` to dynamically calculate `total_endpoints` from the database.
- Implemented REST router in `app/api/v1/endpoints.py` with routes:
  - `POST /api/v1/projects/{project_id}/endpoints`
  - `GET /api/v1/projects/{project_id}/endpoints`
  - `GET /api/v1/endpoints/{endpoint_id}`
  - `PUT /api/v1/endpoints/{endpoint_id}`
  - `DELETE /api/v1/endpoints/{endpoint_id}`
  - `POST /api/v1/endpoints/{endpoint_id}/duplicate`
  - `PATCH /api/v1/endpoints/{endpoint_id}/toggle-active`
- Added comprehensive unit and integration test suite in `tests/test_endpoints.py` (14 new tests passing).
- Total test count increased to 37 with 100% pass rate.

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
