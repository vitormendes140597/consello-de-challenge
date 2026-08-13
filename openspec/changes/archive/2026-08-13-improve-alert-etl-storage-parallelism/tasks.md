## 1. Storage Boundaries

- [x] 1.1 Add a minimal `StorageBackend` for JSON file reads and writes.
- [x] 1.2 Add an alert-focused loader that uses `StorageBackend` and yields validated `RawAlert` objects.
- [x] 1.3 Move client profile JSON object loading behind the alert-focused loader or a small ETL-specific boundary.

## 2. JSON Record Store

- [x] 2.1 Add an agnostic single-file JSON record store that depends on `StorageBackend`.
- [x] 2.2 Implement merge-by-id behavior that replaces matching records, preserves unrelated records, and appends new records.
- [x] 2.3 Serialize Pydantic models and plain mappings through the store without alert-specific logic.

## 3. Parallel Extraction

- [x] 3.1 Restore `context_hints` forwarding from ETL orchestration into prompt construction. Make it optional.
- [x] 3.2 Update alert enrichment to run per-alert extraction with `ThreadPoolExecutor(max_workers=20)`.
- [x] 3.3 Preserve source-alert association and deterministic result ordering after parallel extraction completes.

## 4. ETL Wiring

- [x] 4.1 Replace `AlertExtractionIO` orchestration usage with the split loader, storage backend, and record store.
- [x] 4.2 Update processed output writing so successful runs merge enriched alerts into the existing output file by alert `id`.
- [x] 4.3 Keep compatibility wrappers only where they remain small and useful; remove or simplify obsolete mixed-responsibility paths.

## 5. Verification

- [ ] 5.1 Run the existing relevant checks for the ETL package and fix production-code issues only.
