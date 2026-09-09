# Sub-Stage 02: Configuration & Environment Management — Implementation Plan

## 1. Objective
Centralize all environment variables and runtime settings using Pydantic Settings.

## 2. Technical Specification & Architecture
`pydantic-settings` BaseSettings class reading from `.env` and system environment with field validators and LRU cache.

## 3. Step-by-Step Implementation Tasks
- [x] Create `app/core/config.py` with `Settings` class.
- [x] Support `DATABASE_URL`, `PORT`, `HOST`, `GEMINI_API_KEY`, `LOG_LEVEL`, `DEFAULT_TIMEOUT`.
- [x] Create sample `.env.example` file with documented variables.
- [x] Implement settings caching via `@lru_cache` and cache clearing helper.

## 4. Edge Cases & Fault Tolerance
- [x] Validated DATABASE_URL schemes (SQLite/PostgreSQL) with custom field validator.
- [x] Validated positive timeout constraint (`DEFAULT_TIMEOUT_SECONDS > 0`).
- [x] Environment override tests verify dynamic variable injection.

## 5. Verification & Testing Checklist
- [x] Unit tests written in `tests/test_config.py` and passing with 100% success (6/6 config tests OK).
- [x] Overall test suite passing (9/9 tests OK across project).
- [x] Configuration documented in `.env.example`.

## 6. Definition of Done (DoD)
> **COMPLETED**: Application validates settings on startup, fails fast on invalid configs, and passes all unit tests.
