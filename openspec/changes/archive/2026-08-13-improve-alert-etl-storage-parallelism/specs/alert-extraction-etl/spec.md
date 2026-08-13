## ADDED Requirements

### Requirement: Expose Validated Raw Alerts As Generator
The ETL SHALL expose raw alert records from the input boundary as an iterator that yields validated `RawAlert` objects.

#### Scenario: Raw alerts are yielded after root validation
- **WHEN** the configured raw alert input is a JSON array of valid alert objects
- **THEN** the alert input boundary yields one validated `RawAlert` object for each input alert

#### Scenario: Invalid raw alert stops before extraction
- **WHEN** any input alert is missing a required source field or has an invalid shape
- **THEN** the ETL fails validation before invoking the AI extraction step

### Requirement: Run Alert Extraction In Parallel
The ETL SHALL run independent AI metadata extraction calls for raw alerts in parallel using a thread pool with 20 workers.

#### Scenario: Multiple alerts are enriched concurrently
- **WHEN** the ETL enriches multiple valid raw alerts
- **THEN** it submits per-alert AI extraction work to a `ThreadPoolExecutor` configured with `max_workers=20`

#### Scenario: Parallel extraction preserves output association
- **WHEN** parallel extraction completes for a set of raw alerts
- **THEN** each enriched alert preserves the source fields and metadata for the corresponding input alert

### Requirement: Separate Storage From Alert Validation
The ETL SHALL separate JSON file storage operations from alert-specific schema validation.

#### Scenario: Storage backend handles JSON file operations
- **WHEN** ETL data is read from or written to disk
- **THEN** a storage backend handles JSON file access without depending on alert Pydantic models

#### Scenario: Alert loader validates decoded input
- **WHEN** raw alert data is decoded from storage
- **THEN** an alert-focused loader validates the JSON root and converts alert objects into `RawAlert` instances

### Requirement: Reuse Single-File JSON Record Store
The ETL SHALL provide an agnostic JSON record store that manages a single JSON array file and merges records by a configurable id field.

#### Scenario: Store creates missing output file
- **WHEN** records are merged into a store whose JSON file does not exist
- **THEN** the store writes a JSON array containing the incoming records

#### Scenario: Store replaces matching ids
- **WHEN** incoming records have ids that already exist in the store
- **THEN** the store replaces the existing records for those ids with the incoming records

#### Scenario: Store preserves unrelated records
- **WHEN** the store contains records whose ids are absent from the incoming records
- **THEN** those existing records remain in the stored JSON array

## MODIFIED Requirements

### Requirement: Write Processed Enriched Alert Dataset
The ETL SHALL merge enriched alert records into a configurable processed output path, defaulting to `etl/data/processed/enriched_alerts.json`.

The processed output SHALL remain a JSON array of enriched alert objects. On each successful run, enriched records from the current run SHALL replace existing records with the same alert `id`, preserve existing records with ids absent from the current run, and append records for new ids.

#### Scenario: Processed output is created
- **WHEN** all input alerts are successfully enriched and validated and no processed output file exists
- **THEN** the ETL writes a JSON array containing the current run's enriched alert objects to the configured processed output path

#### Scenario: Repeated run updates matching alerts
- **WHEN** the processed output already contains an enriched alert with the same `id` as an alert enriched in the current run
- **THEN** the ETL replaces the stored record for that `id` with the current run's enriched record

#### Scenario: Repeated run preserves previous alerts
- **WHEN** the processed output already contains enriched alerts whose ids are not present in the current run
- **THEN** the ETL preserves those existing enriched alerts in the processed output
