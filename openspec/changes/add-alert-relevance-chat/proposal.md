## Why

The ETL now produces canonicalized alerts and a profile-shaped canonical client
artifact, but users do not yet have a conversational way to ask which alerts are
most relevant to a client and why. A scored chat experience will make the
canonical data consumable while keeping relevance ranking deterministic,
inspectable, and time-aware.

## What Changes

- Add an AI chat CLI where users type alert-relevance questions in the terminal.
- Use LangChain `ChatOpenAI` with the OpenAI Responses API to keep the
  conversation going across user turns.
- Expose canonical data access and alert ranking as model tools.
- Support one client per user question.
- Parse time-aware questions such as "today" and "last 3 days".
- Add explicit CLI `--as-of` support so relative windows can be evaluated
  against a supplied date/time for demos, tests, and stale sample data.
- Rank alerts with a deterministic weighted scoring function that can add or
  remove criteria without changing the score engine.
- Prioritize proximity to the client's actual business relationships, with
  recency acting as a bounded time-sensitivity signal.
- Print user prompts, tool results, ranking tables, and final answers with
  Rich.

## Capabilities

### New Capabilities

- `alert-relevance-chat`: Conversational CLI for reading canonical alert/client
  artifacts, resolving time-aware alert windows, scoring alert relevance for one
  client, and explaining the top ranked alerts.

### Modified Capabilities

- None.

## Impact

- Affects the `ai-alert-scorer` package, including schemas, JSON loading,
  time-window resolution, scoring logic, LangChain/OpenAI tool orchestration,
  Rich CLI presentation, tests, and README documentation.
- Depends on existing canonicalized ETL outputs:
  `etl/data/processed/canonicalized_alerts.json` and
  `etl/data/processed/canonicalized_client_profile.json`.
- Adds or formalizes runtime dependencies for Rich and any LangChain/LangGraph
  components used by the chat loop.
- Does not change ETL extraction, canonicalization, catalog schema, or processed
  ETL output contracts.
