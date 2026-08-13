## Why

The ETL project needs a reproducible first-pass enrichment step that turns raw news alerts into structured metadata for downstream scoring and `ai-alert-scorer` tool consumption. This first step should favor high-quality extraction with evidence, while leaving canonical naming and standardization to a later process.

## What Changes

- Add an ETL capability that reads `etl/data/raw/sample_alerts.json` as a list of alert records.
- Add AI-assisted extraction using LangChain with an OpenAI backend.
- Use Pydantic models to define and validate the structured output shape.
- Produce one enriched JSON object per input alert, preserving `id`, `received_at`, `subject`, and `body`.
- Extract first-pass metadata arrays for companies, sectors, geographic markets, key markets, commodities, regulators, macro sensitivities, and themes.
- Define the meaning and extraction boundaries for every output field.
- Create reusable prompt guidance for each AI-extracted field.
- Create a synthesis prompt that combines the field prompts, source alert, and optional context hints while leaving output shape enforcement to the structured response schema.
- Keep extracted names lower case and include concise rationales for why each entity or category was included.
- Treat extraction as a recall-oriented first pass; do not attempt final canonicalization, alias merging, or taxonomy standardization in this change.

## Capabilities

### New Capabilities

- `alert-extraction-etl`: First-pass AI extraction pipeline that enriches raw alert JSON with structured news metadata.

### Modified Capabilities

- None.

## Impact

- Adds implementation under `etl/src/etl/`.
- Adds tests under `etl/tests/`.
- Adds or updates ETL dependency configuration for Pydantic, LangChain, and the OpenAI backend.
- Adds prompt definitions for each extracted metadata field plus a synthesis prompt.
- Writes processed output under `etl/data/processed/`.
- Establishes an output contract that downstream canonicalization and scoring processes can consume.
