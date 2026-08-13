## 1. Package Setup

- [x] 1.1 Add or update `ai-alert-scorer` Python package configuration with console script entrypoint, dependencies, test configuration, and source/test package discovery.
- [x] 1.2 Add runtime configuration for canonical alerts path, canonical client profile path, OpenAI model settings, default top-N, timezone, and optional `--as-of`.
- [x] 1.3 Add README usage notes for installing and running the alert relevance chat CLI.

## 2. Schemas And Data Loading

- [x] 2.1 Add Pydantic schemas for canonicalized alert records matching the ETL canonical alert artifact.
- [x] 2.2 Add Pydantic schema for the profile-shaped canonicalized client profile artifact.
- [x] 2.3 Implement JSON loaders for canonical alerts and canonical client profile files with actionable validation errors.
- [x] 2.4 Add tests for valid canonical artifacts, malformed JSON roots, missing files, and schema validation failures.

## 3. Time Window Resolution And As-Of Support

- [x] 3.1 Implement `--as-of` parsing for ISO dates and ISO datetimes, including fast failure for invalid values.
- [x] 3.2 Implement supported relative time-window resolution for `today`, `yesterday`, `last N days`, and `past week`.
- [x] 3.3 Interpret date-only `--as-of` values as the full local calendar day for that date.
- [x] 3.4 Filter canonical alerts by resolved `received_at` time windows.
- [x] 3.5 Add tests for runtime-clock `today`, `--as-of` `today`, `last 3 days`, unsupported phrases, boundary inclusivity, and stale data returning no alerts.

## 4. Relevance Scoring

- [x] 4.1 Define criterion interfaces that expose name, weight, evaluator, normalized score, and evidence.
- [x] 4.2 Implement normalized weighted aggregation over enabled criteria.
- [x] 4.3 Implement bounded recency criterion for time-sensitive ordering.
- [x] 4.4 Implement direct client company and client-name text match criteria without ticker scoring.
- [x] 4.5 Implement relationship-company overlap criterion for competitors, suppliers, and customers.
- [x] 4.6 Implement canonical profile overlap criteria for sectors, geo markets, key markets, commodities, regulators, macro sensitivities, and themes.
- [x] 4.7 Implement bounded signal-combination bonuses for meaningful intersections across relationship and exposure signals.
- [x] 4.8 Add ranking result schemas with final score, criterion breakdowns, matched canonical IDs, and concise evidence.
- [x] 4.9 Add tests for each criterion, aggregation normalization, disabled criteria, score ordering, top-N truncation, and no-match low connectedness.

## 5. Model Tools And Agent Orchestration

- [x] 5.1 Expose `read_canonical_client` as a LangChain model tool.
- [x] 5.2 Expose `read_canonical_alerts` as a LangChain model tool with optional resolved time-window filtering.
- [x] 5.3 Expose `rank_alerts_for_client` as a LangChain model tool that returns structured ranked results.
- [x] 5.4 Configure `ChatOpenAI` to use the OpenAI Responses API and continue the conversation across CLI turns.
- [x] 5.5 Add system/developer instructions requiring relevance answers to call data and ranking tools rather than inventing scores.
- [x] 5.6 Validate one-client scope and ask for clarification when a user asks for multiple clients.
- [x] 5.7 Add tests for tool schemas, tool error paths, and orchestration using fake model/tool responses.

## 6. Rich CLI Experience

- [x] 6.1 Implement the interactive chat loop with Rich prompt/input handling and supported exit commands.
- [x] 6.2 Render assistant messages, tool status, ranked results, and errors with Rich console abstractions.
- [x] 6.3 Render ranked alert results in a table or panel containing rank, score, received date, subject, and key evidence.
- [x] 6.4 Add tests or snapshot-style assertions for CLI formatting boundaries where practical.

## 7. Documentation And Verification

- [ ] 7.1 Document sample commands, including a fixture-friendly run with `--as-of 2026-08-11`.
- [ ] 7.2 Document supported relative time phrases and the behavior when no alerts exist in the requested window.
- [x] 7.3 Document scoring criteria, default weights, and how to add or remove criteria.
- [x] 7.4 Run the relevant scorer test suite.
- [x] 7.5 Run linting and formatting checks for the scorer package.
- [ ] 7.6 Manually smoke test the target prompt: "What are the top 5 most relevant media alerts for Solstice Robotics today, and why does each one matter to the client?" with and without `--as-of`.
