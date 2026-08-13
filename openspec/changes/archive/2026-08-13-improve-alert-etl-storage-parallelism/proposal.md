## Why

The alert extraction ETL currently enriches alerts sequentially and overwrites the processed output on each run, which makes it slower than needed and unsuitable for repeated ingestion as more alerts arrive. The IO layer also mixes storage, schema validation, and ETL-specific orchestration concerns, making the data boundary harder to reuse or evolve.

## What Changes

- Read raw alerts through a generator-oriented validation boundary so alert records can stream from the input layer.
- Run AI metadata extraction calls in parallel with a thread pool sized to 20 workers.
- Persist enriched alerts through a reusable single-file JSON record store that merges records by alert `id`.
- Split current `AlertExtractionIO` responsibilities into a storage backend for JSON file reads/writes and an alert-focused loader/parser for Pydantic validation.
- Keep client profile context available to extraction prompts while preserving the existing enriched alert schema.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `alert-extraction-etl`: Adds generator-based raw alert ingestion, parallel alert enrichment, merge-by-id output persistence, and clearer storage/validation boundaries.

## Impact

- Affected code: `etl/src/etl/io.py`, `etl/src/etl/processing.py`, and any direct callers of `AlertExtractionIO`.
- Public behavior: repeated ETL runs update the configured enriched-alert JSON file by alert `id` instead of replacing the entire dataset with only the latest run's records.
- Runtime behavior: OpenAI calls are issued concurrently using up to 20 worker threads.
- Dependencies: no new runtime dependency is expected; use the Python standard library for thread pooling and JSON file management.
