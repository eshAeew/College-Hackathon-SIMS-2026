# API Sentinel — Project Instructions

Automated REST API testing, regression detection & AI-diagnostic platform. Hackathon case study `JP-009`.
**All 28 stages complete + `/welcome` landing page. Production-ready / demo-ready.** ~118 routes, 322 passing tests, ~20.8k LOC.

## Prime Directive

**The deterministic engine decides 100% of pass/fail. AI is called only after evidence is collected, purely to explain failures and suggest fixes.** Never let an LLM determine whether a test passed. Every AI path must have a rule-based offline fallback (`app/utils/heuristic_recommender.py`) — the platform must stay fully functional with no `GEMINI_API_KEY`.

## Tech Stack

Python 3.13 · FastAPI · Pydantic 2 + pydantic-settings · httpx (async, pooled) · SQLAlchemy 2.0 (sync `Session`) + SQLite (WAL) · jsonschema · PyYAML · Jinja2 + vanilla JS (no React) · numpy · google-genai · pytest.

**Stay inside this boundary.** The case study constrains the stack; do not introduce new frameworks, ORMs, or task queues. Add to `requirements.txt` only when a stage plan calls for it.

## Build & Run

```bash
python -m venv .venv && .venv/Scripts/activate   # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000        # /, /welcome, /dashboard, /docs, /redoc, /health
python -m pytest tests/ -q                       # 322 passing in ~28s
python scripts/run_demo_api.py                   # flawed target standalone on :8001
python scripts/run_demo_story.py --auto          # 14-step demo story CLI
python scripts/self_test_runner.py               # platform self-test matrix
```

No linter, formatter, or CI configured. `.claude/launch.json` runs the app on port 8009.

## Layer Rules

- `app/api/v1/<area>.py` — thin routers. Parse, delegate, wrap. **A new router must be imported and `include_router`'d in `app/api/v1/api.py`** or it is silently unreachable.
- `app/services/<area>_service.py` — classes of `@staticmethod`/`@classmethod` taking `db: Session` first. Never instantiated.
- `app/utils/<engine>.py` — **pure functions, no DB, no I/O.** All real logic (mutation, assertion, classification, statistics, fingerprinting, regression, safety, OpenAPI parsing, prompt synthesis) lives here so it is unit-testable in isolation. Prefer growing utils over fattening services.
- `app/repositories/` — `BaseRepository(Generic[ModelType])` DAL added in Stage 23. Services may use repos or query directly; both patterns exist. Don't refactor one into the other opportunistically.
- `app/models/entities/` — SQLAlchemy ORM (`Project`, `Endpoint`, `TestCase`, `TestRun`, `TestResult`, `AIRecommendation`, `AuditEvent`). `app/models/schemas/` — Pydantic DTOs. Keep them separate.
- `app/core/` — config, database, logging, middleware, http_client, tracer, circuit_breaker, exceptions, exception_handlers.
- `app/web/` — Jinja2 dashboard (`web_router` serves `/`, `/welcome`, `/dashboard`; `dashboard_api_router` serves `/api/v1/dashboard/*`).
- `app/demo_target/` — the intentionally flawed "Alpha Commerce" API at `/demo-api/*` with 6 toggleable injected bugs. **Never fix its bugs** — they are the demo payload. Toggle via `/demo-api/control/*`.

## Code Conventions

- **JSON-in-TEXT columns.** Entities store structured data as `<name>_json` `Text` columns with a `@property`/setter pair that serializes on write and returns `{}`/`[]` on any parse failure. Follow this exactly; never add a JSON column type.
- **New entity → import it in `init_db()`** (`app/core/database.py`) or via `app/models/entities/__init__.py`, or `create_all` won't create the table.
- **Responses**: return `StandardResponse[T]`; errors become `ErrorResponse`/`ErrorDetail` with `SCREAMING_SNAKE` codes. Prefer raising the typed `SentinelBaseException` subclasses in `app/core/exceptions.py` — `register_exception_handlers()` maps them to the envelope. Some older routers still raise bare `HTTPException` for 404s.
- **Config**: only via `get_settings()` (`@lru_cache`d). Never `os.getenv`. New setting → `Settings` + `.env.example`. Use `clear_settings_cache()` in tests.
- **DB access**: `db: Session = Depends(get_db)`. Routers are sync `def` unless they await.
- Timestamps always `datetime.now(timezone.utc)`. One-line docstrings everywhere. Full type hints.
- **Tests**: `tests/test_<area>.py`, `unittest.TestCase` subclasses run by pytest, `TestClient` for HTTP, `test_NN_` prefixes to force ordering. Mirror the source module.
- CRLF endings; a few files carry a UTF-8 BOM. Match the file you're editing; don't normalize. `.gitattributes` pins landing-page assets against normalization.

## Workflow

All 28 stages under `stages/` are complete; their `implementation_plan.md` files are the historical record of what was built. New work is now feature/fix work rather than stage work — but keep the same discipline:

1. Implement narrowly; write tests; run the full suite.
2. Update `changelog.md` and `current_status.md` in `Project Information/Project update - current status/`.
3. Commit as `feat(area): <what>` / `fix(area): <what>` with a `-` bulleted body.

Current branch is **`Chandan`**, not `main` (`main` and `origin/main` also exist; stages 22–28 were merged in from origin). Confirm the intended branch before committing.

Reference docs: `Project Information/Specifications & Architecture/` (architecture, DB schema, demo API spec, AI system), `Project Information/Demo Playbook/` (3-minute pitch, judge Q&A, live demo steps), `Project Information/Prompt/project_stages.md` (§35 out-of-scope list still applies).

## Known Issues

- `requirements.txt` uses unbounded `>=`, so fresh installs drift (currently pulling Starlette with the `HTTP_422_UNPROCESSABLE_ENTITY` deprecation, source of ~109 test warnings). Consider pinning before judging day.
- `CLAUDE.md` and `.claude/` are untracked. Commit them if they should be shared.
- `api_sentinel.db` plus its `-wal`/`-shm` files sit in the repo root; the WAL has grown to ~3 MB. Checkpoint or reset before packaging.
- Mixed data-access styles (repositories vs. direct `db.query`) coexist post-Stage-23.

*Previously listed here and now fixed: SSRF guard is wired into `http_dispatcher.dispatch` via `enforce_target_authorization`; `/api/v1/health` opens a real `SELECT 1`; CORS drops `allow_credentials` when origins are `*`; `google-genai` is in `requirements.txt`; the frontend question is settled as Jinja2 + vanilla JS.*
