# Development Guide

Development guide for the Consello AI Alert Intelligence monorepo.

## Environment

Use Python 3.11+ and a local virtual environment from the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

Install both editable packages with test dependencies:

```bash
python -m pip install -e "./etl[test]"
python -m pip install -e "./ai-alert-scorer[test]"
```

Copy `.env.example` to `.env` when running flows that call models:

```bash
cp .env.example .env
```

Never commit API keys, tokens, or local environment files.

## Package Organization

The `etl` package owns data transformation:

- `etl.common`: configuration, IO, schemas, shared fields, and OpenAI clients.
- `etl.extraction`: prompts, structured model calls, and metadata
  normalization.
- `etl.canonicalization`: canonical catalog loading, candidate generation,
  prompts, decision validation, and profile projection.
- `etl.app`: CLI parsing and command dispatch.

The `ai-alert-scorer` package owns ranking and chat:

- `ai_alert_scorer.scoring`: deterministic relevance matrix.
- `ai_alert_scorer.io`: canonical alert and profile loading.
- `ai_alert_scorer.date_ranges`: time-window resolution.
- `ai_alert_scorer.tools`: tools used by the agent.
- `ai_alert_scorer.agent`: LangGraph/LangChain orchestration.
- `ai_alert_scorer.app`: CLI and terminal presentation.

## Coding Standards

- Follow local style before introducing new patterns.
- Keep changes small, focused, and testable.
- Add type hints to new or changed function signatures.
- Use Pydantic at JSON and model-output boundaries.
- Preserve raw alert fields when enriching or canonicalizing data.
- Validate model decisions before writing files.
- Use `None`/`null` for uncertain canonical values instead of weak mappings.

## OpenSpec Workflow

Use OpenSpec for new features, behavior changes, data-contract changes,
architecture decisions, or any work that needs an explicit product/technical
contract before implementation. Small docs-only edits, local cleanup, and
bug fixes that do not change expected behavior usually do not need a change
proposal.

OpenSpec artifacts live under:

- `openspec/specs/`: accepted behavior specs.
- `openspec/changes/`: proposed or in-progress changes.
- `openspec/changes/archive/`: completed changes after archive.

Start by inspecting the current state:

```bash
openspec list
openspec list --specs
openspec show alert-extraction-etl --type spec
```

### Create A Feature Change

Create one change per coherent feature or behavior change. Use a short
kebab-case name that starts with an action:

```bash
openspec new change add-alert-relevance-chat
```

This creates `openspec/changes/<change-name>/`. Fill the change with these
artifacts:

- `proposal.md`: explains why the change exists, what changes, which
  capabilities are new or modified, and the expected impact.
- `design.md`: explains how the change will be implemented. Keep it focused on
  decisions, trade-offs, migration, and risks.
- `specs/<capability>/spec.md`: defines the behavior contract for each
  capability named in the proposal.
- `tasks.md`: tracks implementation work with parseable checkbox tasks.

Use the CLI instructions when creating or refreshing artifacts:

```bash
openspec instructions proposal --change add-alert-relevance-chat
openspec instructions specs --change add-alert-relevance-chat
openspec instructions design --change add-alert-relevance-chat
openspec instructions tasks --change add-alert-relevance-chat
```

### Create Specs

A feature introduces or modifies capabilities. Capabilities are the units of
specification and use kebab-case names such as `alert-relevance-chat` or
`alert-extraction-etl`.

For a new capability, add it to `proposal.md` under `New Capabilities`, then
create:

```text
openspec/changes/<change-name>/specs/<new-capability>/spec.md
```

For an existing capability, list the existing spec name under
`Modified Capabilities`, then create a delta spec at the same relative path:

```text
openspec/changes/<change-name>/specs/<existing-capability>/spec.md
```

Spec files are deltas until the change is archived. Use these top-level
sections:

- `## ADDED Requirements` for new behavior.
- `## MODIFIED Requirements` for changed behavior. Copy the full existing
  requirement block from `openspec/specs/<capability>/spec.md` before editing
  it.
- `## REMOVED Requirements` for deprecated behavior. Include `Reason` and
  `Migration`.
- `## RENAMED Requirements` for name-only changes.

Each requirement must use normative language and at least one scenario:

```markdown
## ADDED Requirements

### Requirement: Rank Alerts By Client Relevance
The system SHALL rank canonicalized alerts against one canonicalized client
profile using deterministic scoring criteria.

#### Scenario: Ranking returns highest relevance first
- **WHEN** candidate alerts are scored for a client
- **THEN** the system returns alerts ordered by descending relevance score
```

Use `SHALL` or `MUST` for required behavior. Scenarios must use exactly
`#### Scenario:` headings and `WHEN`/`THEN` bullets so validation and archive
can process them correctly.

### Plan Tasks

Create `tasks.md` after the proposal, specs, and design are clear. Tasks must
use checkbox lines so OpenSpec can track progress:

```markdown
## 1. Scoring

- [ ] 1.1 Add deterministic scoring criteria.
- [ ] 1.2 Add tests for ranking order and score evidence.
```

Keep task groups ordered by dependency. Mark tasks complete as implementation
lands:

```markdown
- [x] 1.1 Add deterministic scoring criteria.
```

### Validate And Implement

Validate the change before implementation starts and again before handoff:

```bash
openspec validate add-alert-relevance-chat --type change --strict
openspec status --change add-alert-relevance-chat
```

Implementation should follow the accepted artifacts:

1. Read `proposal.md`, `design.md`, the relevant delta specs, and `tasks.md`.
2. Implement the smallest code change that satisfies the next unchecked tasks.
3. Add or update focused tests for each changed scenario.
4. Run the relevant package tests and update task checkboxes.
5. Re-run OpenSpec validation and normal project checks before handoff.

### Archive Completed Changes

After implementation, tests, docs, and task checkboxes are complete, archive the
change. Archive updates accepted specs under `openspec/specs/` and moves the
change into `openspec/changes/archive/`.

```bash
openspec archive add-alert-relevance-chat -y
openspec validate --specs --strict
```

Use `--skip-specs` only for completed infrastructure or docs changes that
intentionally do not update behavior specs.

## Tests

Run tests for the changed package:

```bash
python -m pytest etl/tests
```

```bash
python -m pytest ai-alert-scorer/tests
```

When changing a specific area, also run the nearest focused test file. Examples:

```bash
python -m pytest etl/tests/test_canonicalization.py
```

```bash
python -m pytest ai-alert-scorer/tests/test_scoring.py
```

## Lint And Formatting

Each package `pyproject.toml` configures Ruff with a line length of 88 and
rules `E`, `F`, `I`, `UP`, and `B`. Ruff is not currently listed as a project
dependency; install or run it separately if you want local lint checks.

## Documentation

Update the README for the affected package whenever commands, configuration,
data formats, or public behavior change. Keep the root README as the monorepo
entry point and keep detailed operational notes in the subproject READMEs.
