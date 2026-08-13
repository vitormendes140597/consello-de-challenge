# Repository AGENTS

This file applies to the whole monorepo unless a more specific `AGENTS.md` exists in a subdirectory.

## Scope

- Shared conventions, safety, and coordination rules for the repo
- Project-specific `AGENTS.md` files in subdirectories override this file for their subtree

## General Rules

- Prefer small, focused changes that match the existing structure.
- Keep files ASCII unless the file already uses non-ASCII characters or there is a clear reason to introduce them.
- Use `apply_patch` for manual file edits.
- Do not overwrite user changes unless explicitly requested.

## Development Guide

- Read the surrounding code before editing. Match the local module layout, naming, imports, and test style.
- Keep changes as small, simple, and clear as possible. Do not add boilerplate, broad abstractions, or unrelated refactors unless they are needed for the requested behavior.
- Prefer explicit, readable code over clever shortcuts. Choose names that describe intent, not implementation details.
- Use established coding patterns and best practices when they clarify the implementation or reduce real complexity.
- For python code always use python-code-writer agent

## Repo-Local Codex Agents

The repository defines local Codex agent roles under `.codex/agents/`. These
agents are workflow helpers, not product code. Use them as lenses for the
appropriate phase of work and keep their output grounded in the applicable
`AGENTS.md`, nearby code, tests, and OpenSpec artifacts.

| Agent | Definition | Use for |
| --- | --- | --- |
| Python Expert | `.codex/agents/python_expert.toml` | Python implementation, refactoring, test design, type hints, docstrings, and pragmatic module design. |
| Code Reviewer | `.codex/agents/code_reviewer.toml` | Review findings focused on correctness, regressions, missing tests, maintainability, public contracts, and delivery risk. |
| Security Auditor | `.codex/agents/security_auditor.toml` | Security, privacy, configuration, secrets, logging, prompt/model data, file IO, path handling, and integration-risk review. |

Typical flow:

1. Use Python Expert for focused Python code changes.
2. Use Code Reviewer before accepting non-trivial changes.
3. Use Security Auditor when changes touch secrets, `.env`, external services,
   prompts, model responses, file paths, generated artifacts, or user/client
   data.

Codex local settings live in `.codex/config.toml`; current agent settings allow
up to 6 threads with depth 1. For more detail, see
`docs/project-agents-overview.md`.

## Python Coding Standards

- Follow PEP 8 and the formatter/linter configuration already present in the project.
- Use 4-space indentation, `snake_case` for functions and variables, `PascalCase` for classes, and `UPPER_CASE` for constants.
- Add type hints to all new or changed function signatures. Avoid `Any` unless a precise practical type is not available.
- Add docstrings to all public modules, classes, and functions. Keep internal comments sparse and useful.
- Keep functions focused on one responsibility. Prefer early returns over deeply nested conditionals.
- Do not use mutable default arguments. Use `None` plus an explicit initialization inside the function.
- Prefer dataclasses or typed structures for simple data containers instead of loosely shaped dictionaries.
- Organize imports as standard library, third-party packages, then local modules. Avoid wildcard imports.
- Remove commented-out code, debug prints, breakpoints, and unused variables before handing off.

## Python Docstrings

- Use Google-style docstrings for public modules, classes, dataclasses, protocols, functions, and methods.
- Function and method docstrings must include a concise summary plus `Args` and `Returns` sections with parameter and return data types.
- Add a `Raises` section for expected exceptions and note side effects such as reading environment variables, loading `.env`, file IO, network calls, or model/API calls.
- For dataclasses and Pydantic models, document fields in an `Attributes` section with field names, data types, and meaning.
- Keep private helper docstrings concise when the behavior is obvious; use the same `Args` and `Returns` structure when inputs, output, or side effects need clarification.
- Do not restate type hints mechanically. Explain semantics, accepted values, defaults, constraints, and units when that information matters.

## Error Handling and Observability

- Catch specific exception types. Do not use bare `except` or silently swallow failures.
- Raise errors with actionable messages that explain what failed and which input or state caused it when safe to include.
- Use context managers for files, network clients, database connections, and other managed resources.
- Use the project logger for runtime diagnostics. Do not use `print()` in application code unless the surrounding code intentionally does so.
- Never log secrets, tokens, passwords, prompts, responses, PII, stable user identifiers, or URLs containing credentials.

## Testing and Verification

- Add or update tests for changed behavior, especially edge cases and error paths.
- Prefer focused unit tests for pure logic and integration tests only where boundaries with external systems matter.
- Mock external APIs, databases, file systems, and network calls unless the test is explicitly an integration test.
- Run the most relevant checks available for the touched area, such as `pytest`, `ruff`, `mypy`, or project-specific scripts.
- If a check cannot be run, document the command attempted and the reason it could not complete.

## Security and Configuration

- Do not commit secrets, API keys, passwords, tokens, or generated credentials.
- Read sensitive configuration from environment variables or the existing project configuration layer.
- Keep `.env` and local override files out of version control.
- Validate and sanitize untrusted input at the system boundary before using it in file paths, shell commands, SQL, or network requests.

## Change Discipline

- Keep commits and patches scoped to the requested behavior.
- Preserve existing public APIs unless the task explicitly requires a breaking change.
- Update nearby documentation or examples when behavior, configuration, or developer workflow changes.
- Before finishing, review the diff for avoidable complexity, weak names, missing tests, and accidental churn.
