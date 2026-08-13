## Context

The repository currently has an `etl` package that extracts and canonicalizes
media alerts and a minimal `ai-alert-scorer` package intended for LangChain and
LangGraph agent work. The canonical artifacts already contain the fields needed
for relevance scoring:

- Canonicalized alerts preserve `id`, `received_at`, `subject`, `body`, and
  canonicalized metadata arrays.
- The canonicalized client profile preserves `client_name`, `ticker`, and
  profile-shaped canonical ID arrays for focal companies, competitors,
  suppliers, customers, markets, commodities, regulators, macro sensitivities,
  and themes.

The new chat layer should consume those artifacts as read-only inputs. It should
not ask the model to invent relevance scores. The model should call tools, get
deterministic scored results, and explain those results in client-facing
language.

## Goals / Non-Goals

**Goals:**

- Provide a terminal chat interface for alert relevance questions.
- Keep conversation state with LangChain `ChatOpenAI` using the OpenAI Responses
  API.
- Expose canonical client loading, canonical alert loading, and relevance
  ranking as model tools.
- Resolve relative time language against a deterministic `as_of` timestamp.
- Support `--as-of` on the CLI for demos, repeatable tests, and data snapshots
  whose latest alert is not the actual current date.
- Restrict each relevance request to one client.
- Compute relevance with a deterministic weighted scoring function.
- Make scoring criteria pluggable so criteria can be added or removed without
  changing the score aggregation logic.
- Prioritize proximity to the client's actual business relationships, with
  recency acting as a bounded time-sensitivity signal.
- Present inputs, tool activity, ranked alerts, and answers with Rich.

**Non-Goals:**

- Do not modify ETL extraction, canonicalization, catalog schema, or processed
  ETL output contracts.
- Do not support ranking across multiple clients in one user question.
- Do not use live news search or external media APIs.
- Do not rely on the model to calculate numeric relevance scores.
- Do not add persistence for chat transcripts beyond the Responses API
  conversation state used during the CLI session.

## Decisions

### Build the chat layer in `ai-alert-scorer`

The `ai-alert-scorer` package should own schemas, loaders, scoring, tools,
agent orchestration, and the Rich CLI. It can read canonical JSON files from the
ETL defaults but should not import ETL internals unless the packaging makes that
dependency explicit.

Rationale: this keeps ETL as the data-production boundary and keeps downstream
ranking/chat behavior modular.

Alternative considered: add a chat command to the `etl` CLI. This was rejected
because the chat agent is a consumer of canonical data, not part of extraction
or canonicalization.

### Use deterministic tools for data and ranking

The model-facing tools should include:

- `read_canonical_client`: load and validate one canonicalized client profile.
- `read_canonical_alerts`: load and validate canonicalized alerts, optionally
  filtered by a resolved time window.
- `rank_alerts_for_client`: score candidate alerts for one client and return
  ranked results with criterion-level evidence.

Rationale: tools make data interaction explicit while keeping numeric scoring
auditable. The model can decide when to call tools and can explain the returned
score details, but the final rank order comes from code.

Alternative considered: pass all alert and client JSON directly in the system
prompt. This was rejected because it hides data access, makes context size grow
with the dataset, and prevents focused tests around tool behavior.

### Resolve relative dates against an `as_of` timestamp

The CLI should accept `--as-of` as an ISO date or datetime. If omitted, the
runtime current time is used. Relative phrases such as "today", "yesterday",
"last 3 days", and "past week" should resolve against this anchor. Date-only
anchors represent the full local day for that date.

Rationale: the sample data can be older than the actual current date. Without
`--as-of`, a literal "today" query on a stale fixture correctly returns no
alerts, but demos and tests need a stable way to ask "today" as of the fixture
date.

Alternative considered: automatically infer "today" from the newest alert date.
This was rejected because it silently changes the meaning of user questions and
would be wrong against live or continuously updated datasets.

### Treat one user request as one-client scoped

The tool layer should validate that a ranking request identifies one client
profile. If the user asks for multiple clients, the assistant should ask them to
choose one before ranking.

Rationale: the scoring criteria depend on one canonical profile and relationship
sets. Multi-client comparisons need a different output contract and aggregation
policy.

Alternative considered: run ranking once per mentioned client. This was rejected
for the initial version because it complicates tool outputs and conflicts with
the stated one-client scope.

### Implement a configurable scoring matrix

Each criterion should expose a stable name, weight, and evaluator. An evaluator
returns a normalized `0.0` to `1.0` score plus evidence. The aggregate score is
computed as the weighted average over enabled criteria:

```text
score = 100 * sum(criterion_score * weight) / sum(enabled_weights)
```

Initial matrix groups should include:

- Relationship proximity for direct canonical client matches, client-name text
  mentions, competitors, customers, and suppliers. Ticker values remain in the
  input schema but do not contribute to score or evidence.
- Operational exposure for key markets, regulators, and commodities.
- Broad context for sectors, geo markets, macro sensitivities, and themes.
- Signal-combination bonuses for meaningful intersections such as competitor
  plus key market or supplier plus commodity.
- Recency as a bounded time-sensitivity signal.

Rationale: normalized aggregation allows criteria to be added, removed, or
disabled without changing the score engine or silently changing the score scale.
Business proximity receives the largest cap because those relationships have
the most direct potential impact on the client's competitive position, revenue,
or operations.

Alternative considered: hard-code one formula that references every current
field. This was rejected because it makes criterion evolution brittle.

### Return score explanations as structured data

Ranking results should include alert identifiers, received timestamps, subjects,
final score, criterion scores, matched canonical IDs, and concise evidence
snippets or rationales. The final assistant answer should be generated from this
structured result.

Rationale: users ask not only for top alerts but why each matters. The scoring
tool must provide enough evidence for the model to explain relevance without
reading hidden state or hallucinating.

Alternative considered: return only the top alert IDs and scores. This was
rejected because it would force the model to reconstruct evidence from raw text.

### Use Rich as the only terminal presentation layer

The CLI should use Rich prompts, panels, progress/status lines, tables, and
Markdown rendering for user-visible interaction. Application code should avoid
plain `print()` except through Rich console abstractions.

Rationale: the user requested polished terminal input/output, and a single
presentation layer keeps tests and formatting behavior easier to reason about.

Alternative considered: start with plain argparse/stdout. This was rejected
because the user-facing CLI experience is part of the requested capability.

## Risks / Trade-offs

- **Relative date parsing ambiguity** -> Keep supported phrases explicit,
  document them, and ask the model to clarify unsupported or ambiguous windows.
- **Stale data makes "today" look empty** -> Use literal current-date behavior
  by default and provide `--as-of` for deterministic fixture-relative runs.
- **Model skips required tools** -> Prompt the assistant that relevance answers
  MUST use the data and ranking tools, and test the orchestration path with fake
  tools/models where possible.
- **Score weights feel subjective** -> Keep weights configured in one place,
  expose score breakdowns in results, and add focused tests for each criterion.
- **Large alert datasets exceed useful tool payload size** -> Filter by time
  window before ranking and return bounded top-N ranked results by default.
- **Package dependency drift between ETL and scorer** -> Define scorer-local
  schemas matching the canonical artifact contract or formalize a shared schema
  dependency before importing ETL internals.
