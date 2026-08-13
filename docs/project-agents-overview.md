# Project Agents Overview

This repository includes repo-local Codex agent definitions to make the
development workflow more explicit. The agents are not product code. They are
working roles used to help write, review, and harden the Python implementation
in this repository.

The goal is to keep implementation work disciplined: one agent focuses on
writing high-quality Python, another reviews changes for defects and missing
tests, and another checks security, privacy, and operational risk.

## Scope Rules

The repository has layered instructions for agents and contributors:

- [`AGENTS.md`](../AGENTS.md) defines general rules for the full monorepo.
- [`etl/AGENTS.md`](../etl/AGENTS.md) adds ETL-specific rules for code under
  `etl/`.
- [`ai-alert-scorer/AGENTS.md`](../ai-alert-scorer/AGENTS.md) adds scorer and
  chat-agent rules for code under `ai-alert-scorer/`.

Agents and contributors should read the most specific applicable file before
editing code. The narrower file wins when instructions overlap.

## Specialized Agents

The [`.codex/agents/`](../.codex/agents/) directory defines three specialized
agents. Each file documents the agent's goals, recurring tasks, and directives.

### Python Expert

[`python_expert.toml`](../.codex/agents/python_expert.toml) describes the agent
used for Python implementation work. Its role is to operate like a principal
software engineer: strong on design fundamentals, pragmatic about delivery, and
careful about long-term maintainability.

This agent is most useful for:

- applying SOLID, DRY, YAGNI, KISS, and design patterns only where they clarify
  the implementation;
- writing clean Python code that is readable, well-typed, and easy to test;
- shaping test strategy across unit, integration, and end-to-end layers;
- balancing maintainability, testability, performance, security, and delivery
  constraints.

### Code Reviewer

[`code_reviewer.toml`](../.codex/agents/code_reviewer.toml) describes the agent
used to review code after implementation. Its role is to inspect diffs,
nearby code, tests, docs, and relevant design artifacts for concrete issues.

This agent is most useful for:

- finding behavioral regressions and edge cases;
- checking whether new behavior has enough test coverage;
- validating public contracts, architecture boundaries, and user-facing
  behavior;
- keeping feedback grounded in specific files, lines, and user impact.

### Security Auditor

[`security_auditor.toml`](../.codex/agents/security_auditor.toml) describes the
agent used to review security, privacy, and operational-risk concerns. Its role
is to protect secrets, credentials, private data, logs, prompts, model
responses, and generated artifacts.

This agent is most useful for:

- reviewing configuration and environment-variable handling;
- checking logging, errors, and generated outputs for sensitive data exposure;
- identifying injection, path traversal, insecure deserialization, permission,
  and data-leakage risks;
- validating that untrusted input, trusted logic, external services, and
  persisted artifacts stay separated and auditable.

## How They Fit Together

A typical agent-assisted change uses these roles in sequence:

1. The Python Expert implements the smallest practical code change and related
   tests.
2. The Code Reviewer checks the diff for correctness, regression risk, missing
   tests, and documentation gaps.
3. The Security Auditor reviews sensitive boundaries such as configuration,
   model inputs, logs, file paths, and persisted outputs.

This division keeps the work easier to audit. The implementation agent focuses
on building the change, while the review agents apply separate lenses before
the change is considered complete.

## OpenSpec Context

The [`openspec/`](../openspec/) directory stores proposals, specs, and task
lists for planned changes. Agents should use these documents to understand
product decisions, accepted behavior, and scope before implementing larger
features.

## Shared Practices

All agents should follow the same baseline practices:

- Preserve existing user changes.
- Use small patches and review the diff before finishing.
- Run the relevant tests for the changed package when code changes.
- Do not log secrets, sensitive prompts, model responses, or personal data.
- Follow the typing, docstring, and test standards described in the
  [`Development Guide`](development-guide.md).
