# etl AGENTS

This file overrides the repository root `AGENTS.md` for everything under `etl/`.

## Project Scope

- Python ETL project that shapes data for `ai-alert-scorer` tooling
- Keep data shaping steps reproducible and easy to validate

## Project Rules

- Prefer modular code under `src/etl/`.
- Keep tests in `tests/`.
- Use `data/raw`, `data/interim`, and `data/processed` for staging boundaries.
