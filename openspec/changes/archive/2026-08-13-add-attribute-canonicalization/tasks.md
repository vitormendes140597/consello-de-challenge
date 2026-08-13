## 1. Catalog And Schema Contracts

- [x] 1.1 Add a versioned canonical catalog JSON file covering `companies`, `sectors`, `geo_markets`, `key_markets`, `commodities`, `regulators`, `macro_sensitivities`, and `themes`.
- [x] 1.2 Define Pydantic schemas for canonical catalog fields, canonical entries, aliases, related terms, exclusions, and regulator law/regime mappings.
- [x] 1.3 Implement catalog loading and validation from the dedicated catalog configuration path.
- [x] 1.4 Add canonicalized item schemas for metadata items and company items with nullable `canonical`.
- [x] 1.5 Add `CanonicalizedAlert` and canonicalized customer-profile schemas that preserve original source values and add canonicalized attributes.
- [x] 1.6 Add runtime validation that rejects non-null canonical IDs not present in the corresponding field catalog.

## 2. Prompt And Model Orchestration

- [x] 2.1 Create field-specific canonicalization guidance for every supported canonical field.
- [x] 2.2 Create regulator-specific prompt guidance for aliases, acronyms, laws, regimes, review processes, and regulator entity canonical outputs.
- [x] 2.3 Define candidate projection schemas for per-item canonical candidates, match source, similarity score, and field-scoped candidate lists.
- [x] 2.4 Implement deterministic candidate generation for canonical IDs, labels, aliases, acronyms, exclusions, and regulator `law_or_regime_aliases`.
- [x] 2.5 Implement catalog embedding text construction and a versioned local embedding index using `text-embedding-3-small`.
- [x] 2.6 Implement field-scoped similarity search that returns top-K candidates only when deterministic matching does not produce a strong unique result.
- [x] 2.7 Implement candidate caching keyed by catalog version/content hash and normalized source values.
- [x] 2.8 Implement a canonicalization prompt builder that includes the complete source payload, projected candidates, global rules, and field guidance without embedding the full catalog.
- [x] 2.9 Define structured-output model protocols for canonicalization using the existing LangChain/OpenAI pattern.
- [x] 2.10 Implement one-request canonicalization decision for a complete enriched alert.
- [x] 2.11 Implement one-request canonicalization decision for a complete customer-profile canonicalization payload.
- [x] 2.12 Ensure canonicalization preserves original item `name`, `rationale`, and company `ticker` values and does not add or remove items.

## 3. Profile And Alert Processing

- [x] 3.1 Implement an adapter from enriched alerts to the common canonicalization payload.
- [x] 3.2 Implement an adapter from customer-profile JSON fields to the common canonicalization payload.
- [x] 3.3 Implement conversion from canonicalized alert payloads into `CanonicalizedAlert`.
- [x] 3.4 Implement conversion from canonicalized profile payloads into the canonicalized customer-profile output.
- [x] 3.5 Add processing orchestration that reads enriched alerts, loads the customer profile, canonicalizes both, and returns validated outputs.
- [x] 3.6 Write canonicalized alerts to a separate JSON array file using merge-by-id semantics.
- [x] 3.7 Write the canonicalized customer profile to a separate JSON object file.

## 4. CLI And Configuration

- [x] 4.1 Add default canonicalized alert and canonicalized customer-profile output paths.
- [x] 4.2 Add CLI arguments for canonicalization input path, client profile path, catalog path, embedding index/cache path, canonicalized alert output path, and canonicalized profile output path.
- [x] 4.3 Add a `canonicalize` CLI command that runs the canonicalization processing flow.
- [x] 4.4 Load the standard data model configuration and embedding model configuration for canonicalization without changing extraction model configuration behavior.
- [x] 4.5 Preserve existing `run` and `prompt` command behavior.

## 5. Tests

- [x] 5.1 Add catalog schema and loader tests for valid catalog data and malformed catalog failures.
- [x] 5.2 Add deterministic candidate-generation tests for IDs, labels, aliases, exclusions, and regulator law/regime mappings.
- [x] 5.3 Add embedding-index tests verifying catalog entries are embedded once per catalog version/content hash and similarity search is field-scoped.
- [x] 5.4 Add prompt tests verifying the canonicalization prompt includes source payload, projected candidates, global rules, and regulator guidance without including the full catalog.
- [x] 5.5 Add model orchestration tests verifying one structured-output decision call per alert or profile payload.
- [x] 5.6 Add schema validation tests for valid canonicalized alerts, nullable canonical values, preserved tickers, rejected out-of-catalog canonical IDs, and rejected IDs outside the item's candidate set.
- [x] 5.7 Add regulator canonicalization tests for direct acronyms, full regulator names, explicit law/regime mappings, embedding-similar but unmapped laws, and unmapped law/regime null outputs.
- [x] 5.8 Add profile adapter tests for client company, focal companies, competitors, suppliers, customers, sector, and existing metadata arrays.
- [x] 5.9 Add processing tests verifying canonicalized alerts write to a new file and do not overwrite enriched alerts.
- [x] 5.10 Add CLI tests for the new `canonicalize` command and unchanged existing commands.

## 6. Documentation And Verification

- [x] 6.1 Update the ETL README with the canonical catalog format, candidate projection behavior, embedding index/cache behavior, canonicalized output shape, and canonicalization CLI command.
- [x] 6.2 Document the boundary between extraction, canonicalization, and downstream relevance scoring.
- [x] 6.3 Run the ETL test suite.
- [x] 6.4 Run relevant linting or formatting checks for touched Python files.
- [x] 6.5 Inspect the final diff for unrelated churn and accidental application-code changes outside the requested implementation.
