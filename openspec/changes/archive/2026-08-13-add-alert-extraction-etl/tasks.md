## 1. Project Setup

- [x] 1.1 Add ETL project dependency configuration for Pydantic, LangChain, OpenAI backend support, pytest, and any required packaging metadata.
- [x] 1.2 Add an ETL module layout under `etl/src/etl/` for schemas, IO, prompt definitions, extraction, post-processing, and command entrypoint code.
- [x] 1.3 Add reusable ETL configuration handling for default input path `etl/data/raw/sample_alerts.json` and default output path `etl/data/processed/enriched_alerts.json`.

## 2. Pydantic Data Contracts

- [x] 2.1 Define Pydantic models for raw alerts requiring `id`, `received_at`, `subject`, and `body`.
- [x] 2.2 Define Pydantic models for company items with `name`, nullable `ticker`, and `rationale`.
- [x] 2.3 Define Pydantic models for metadata items with `name` and `rationale`.
- [x] 2.4 Define the enriched alert model containing preserved source fields plus `companies`, `sectors`, `geo_markets`, `key_markets`, `commodities`, `regulators`, `macro_sensitivities`, and `themes`.
- [x] 2.5 Add Pydantic field descriptions that match the documented semantics for every output field.

## 3. Prompt Definitions

- [x] 3.1 Define the output field semantics for `id`, `received_at`, `subject`, `body`, `companies`, `sectors`, `geo_markets`, `key_markets`, `commodities`, `regulators`, `macro_sensitivities`, and `themes`.
- [x] 3.2 Create a reusable prompt section for `companies` describing purpose, include rules, exclude rules, evidence standard, normalization, rationale expectations, and edge cases.
- [x] 3.3 Create a reusable prompt section for `sectors` describing purpose, include rules, exclude rules, evidence standard, normalization, rationale expectations, and edge cases.
- [x] 3.4 Create a reusable prompt section for `geo_markets` describing purpose, include rules, exclude rules, evidence standard, normalization, rationale expectations, and edge cases.
- [x] 3.5 Create a reusable prompt section for `key_markets` describing purpose, include rules, exclude rules, evidence standard, normalization, rationale expectations, and edge cases.
- [x] 3.6 Create a reusable prompt section for `commodities` describing purpose, include rules, exclude rules, evidence standard, normalization, rationale expectations, and edge cases.
- [x] 3.7 Create a reusable prompt section for `regulators` describing purpose, include rules, exclude rules, evidence standard, normalization, rationale expectations, and edge cases.
- [x] 3.8 Create a reusable prompt section for `macro_sensitivities` describing purpose, include rules, exclude rules, evidence standard, normalization, rationale expectations, and edge cases.
- [x] 3.9 Create a reusable prompt section for `themes` describing purpose, include rules, exclude rules, evidence standard, normalization, rationale expectations, and edge cases.
- [x] 3.10 Create a synthesis prompt builder that combines alert content, context hints, global extraction rules, and all field prompt sections without embedding output schema instructions.
- [x] 3.11 Ensure client profile values are included as contextual hints without treating them as closed allowlists.

## 4. Extraction Chain

- [x] 4.1 Implement LangChain/OpenAI structured output invocation using the Pydantic enriched metadata schema and synthesis prompt.
- [x] 4.2 Keep model configuration suitable for repeatable extraction, including low temperature settings.

## 5. ETL Processing

- [x] 5.1 Implement JSON loading for raw alerts and client profile context.
- [x] 5.2 Validate raw alerts before invoking the AI extraction step.
- [x] 5.3 Process each input alert into one enriched alert object.
- [x] 5.4 Preserve `id`, `received_at`, `subject`, and `body` unchanged in every enriched output.
- [x] 5.5 Normalize extracted names and tickers to lower case.
- [x] 5.6 Deduplicate extracted items within each metadata array for each alert.
- [x] 5.7 Write the enriched alert dataset as a JSON array to the configured processed output path.

## 6. Tests

- [ ] 6.1 Add tests for raw alert validation, including missing required source fields.
- [ ] 6.2 Add tests for Pydantic output validation, including nullable company tickers.
- [ ] 6.3 Add tests for source field preservation.
- [ ] 6.4 Add tests for lower-case normalization and per-alert deduplication.
- [ ] 6.5 Add tests for company-only extraction boundaries using mocked structured model responses.
- [ ] 6.6 Add tests that every AI-extracted output field has a reusable field prompt section.
- [ ] 6.7 Add tests that the synthesis prompt includes every field prompt section, alert content, client profile hints, and global extraction rules.
- [ ] 6.8 Add tests for output count matching input count.

## 7. Documentation And Verification

- [x] 7.1 Document how to run the ETL locally and what environment variables are required for OpenAI access.
- [x] 7.2 Document the output JSON shape and the boundary between first-pass extraction and future canonicalization.
- [x] 7.3 Document the meaning of every output field and the prompt guidance approach.
- [x] 7.4 Run the ETL test suite and confirm all tests pass.
- [x] 7.5 Run `openspec status --change add-alert-extraction-etl` and confirm the change is ready for implementation.
