## Context

The ETL currently uses `AlertExtractionIO` as a config-bound service that reads JSON, validates raw alerts, loads client profile context, and writes the processed output. `run_alert_extraction_etl` loads all alerts into a list, enriches them with a sequential loop, and writes the current run's enriched records as the full output file.

The next iteration needs to handle repeated runs over growing alert data. Roughly 30 alerts are expected now, but additional alerts can arrive later. OpenAI extraction is the slow step, so independent alert calls should run concurrently while the file boundary remains simple and reproducible.

## Goals / Non-Goals

**Goals:**

- Keep the implementation small, readable, and standard-library based.
- Separate JSON file storage from alert-specific Pydantic validation.
- Expose validated raw alerts through a generator-oriented boundary.
- Run per-alert OpenAI extraction in parallel with `ThreadPoolExecutor(max_workers=20)`.
- Persist enriched alerts through a reusable JSON record store that merges by record id.
- Preserve existing enriched alert fields and client profile prompt context.

**Non-Goals:**

- Do not introduce a real database, queue, async runtime, or new runtime dependency.
- Do not change the enriched alert JSON schema.
- Do not add retry, rate-limit backoff, batching, or partial failure recovery in this change.
- Do not include test updates in the implementation task list.

## Decisions

### Use a simple `StorageBackend` for JSON file boundaries

Create a small storage abstraction responsible only for reading and writing JSON values from paths. It should create parent directories when writing and keep JSON serialization formatting consistent with the current output.

Alternative considered: keep storage helpers as private functions in `io.py`. That keeps fewer public names, but it does not give the reusable record store a clean storage dependency.

### Move alert parsing and validation into an alert-focused loader

The alert loader should use `StorageBackend` to load decoded JSON, validate that the raw root is a JSON array, and yield `RawAlert` instances one at a time. Client profile loading can remain alert-ETL specific, but schema validation should be separate from file operations.

Alternative considered: make `StorageBackend` validate model arrays generically. That would make the storage layer know too much about Pydantic and repeat the current mixed-responsibility problem.

### Implement the single-file store as an agnostic JSON record store

Create a reusable class that manages a JSON array file as records keyed by a configurable field, defaulting to `id`. On merge, existing records with matching ids are replaced by incoming records, existing records with missing ids are preserved, and new ids are appended.

Alternative considered: store records as a JSON object keyed by id. That would simplify lookup, but it would break the current processed output shape, which is a JSON array.

### Keep output writes atomic enough for single-process ETL

Write merged JSON through a temporary sibling file and replace the target path after serialization succeeds. This avoids truncated/corrupt output if a write fails partway through.

Alternative considered: add file locking. That is more complexity than needed unless multiple ETL processes are expected to write the same output path concurrently.

### Use a thread pool for OpenAI calls

Use `ThreadPoolExecutor(max_workers=20)` for independent per-alert extraction. Preserve deterministic result ordering by collecting results according to input order before merging them into storage.

Alternative considered: use asyncio. The current LangChain model boundary is synchronous, and a thread pool is the smallest change that parallelizes blocking network calls.

### Validate inputs before model calls

Even though raw alerts are exposed by a generator, the orchestrator should exhaust validation before submitting OpenAI work. That preserves the current behavior where invalid source alerts stop the ETL before any model invocation.

Alternative considered: stream validation directly into the executor. That reduces memory pressure, but for roughly 30 alerts the memory benefit is negligible and the failure behavior is less predictable.

## Risks / Trade-offs

- Lost updates if two ETL processes write the same output file concurrently -> Accept for now; add file locking later if concurrent writers become a real requirement.
- More parallel calls can hit provider rate limits -> Keep worker count fixed at 20 as requested; retry/backoff is out of scope for this change.
- A single failed extraction can fail the whole run after other calls have already completed -> Accept current all-or-fail behavior; partial persistence is out of scope.
- The generator boundary does not make JSON parsing fully streaming because the input file is a JSON array -> Accept for now; true streaming would require newline-delimited JSON or a streaming parser dependency.
