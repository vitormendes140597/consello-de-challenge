## ADDED Requirements

### Requirement: Define Canonical Catalog
The ETL SHALL define a maintainable canonical catalog for `companies`, `sectors`, `geo_markets`, `key_markets`, `commodities`, `regulators`, `macro_sensitivities`, and `themes`.

The catalog SHALL define allowed canonical IDs for each supported field. Each canonical entry SHALL be able to include a human-readable label, aliases, related terms, exclusions, and a description.

#### Scenario: Catalog provides allowed values
- **WHEN** canonicalization runs
- **THEN** the ETL loads allowed canonical IDs for every supported field from the canonical catalog

#### Scenario: Catalog validation rejects malformed entries
- **WHEN** the canonical catalog is missing required structure or contains invalid field definitions
- **THEN** the ETL fails validation before invoking the canonicalization model

### Requirement: Map Regulator References To Regulator Entities
The canonical catalog SHALL support regulator entries that map regulator names, acronyms, aliases, laws, regimes, review processes, and enforcement frameworks to canonical regulator entity IDs.

Canonicalized `regulators` values SHALL use regulator entity IDs as the `canonical` value. Laws, regulations, regimes, or review processes SHALL NOT be emitted as final canonical regulator values unless they are themselves configured as regulator entity IDs.

#### Scenario: Regulator acronym maps to canonical regulator entity
- **WHEN** an extracted regulator item has `name` set to `CFIUS`
- **THEN** canonicalization can return `canonical` set to `cfius`

#### Scenario: Regulator law maps through explicit catalog relationship
- **WHEN** an extracted regulator item has `name` set to `EU AI Act`
- **AND** the canonical catalog explicitly maps `EU AI Act` to a regulator entity
- **THEN** canonicalization can return that regulator entity ID as `canonical`

#### Scenario: Unmapped regulator-related law remains null
- **WHEN** an extracted regulator item names a law, regime, or review process with no explicit catalog mapping to a regulator entity
- **THEN** canonicalization returns `canonical` set to null for that item

### Requirement: Canonicalize Structured Sources With One LLM Request
The ETL SHALL canonicalize each structured source object by sending the complete source object, projected canonical candidates, and field-specific canonicalization guidance to the LLM in one structured-output request.

The ETL SHALL NOT canonicalize by making one canonicalization LLM request per field or per attribute. The ETL SHALL NOT require the canonicalization LLM to spawn subagents or call catalog-search tools directly.

#### Scenario: One enriched alert is canonicalized in one request
- **WHEN** the ETL canonicalizes an enriched alert
- **THEN** it invokes the canonicalization model once for the complete enriched alert and projected candidates

#### Scenario: One customer profile is canonicalized in one request
- **WHEN** the ETL canonicalizes a customer profile
- **THEN** it invokes the canonicalization model once for the complete profile-derived canonicalization payload and projected candidates

### Requirement: Generate Canonical Candidates Before LLM Canonicalization
The ETL SHALL generate candidate canonical IDs locally before invoking the canonicalization LLM.

Candidate generation SHALL first apply deterministic catalog matching for canonical IDs, labels, aliases, acronyms, exclusions, and regulator `law_or_regime_aliases`. When deterministic matching does not produce a strong unique result, the ETL SHALL use `text-embedding-3-small` similarity search over field-scoped catalog entries to retrieve a small top-K candidate set.

The ETL SHALL search only within the item's supported canonical field. The ETL SHALL pass only projected candidates, not the full canonical catalog, to the canonicalization LLM.

#### Scenario: Exact alias resolves without embedding fallback
- **WHEN** an extracted company item has `name` set to `SLRB`
- **AND** the canonical catalog defines `SLRB` as an alias of `solstice_robotics`
- **THEN** candidate generation returns `solstice_robotics` as a strong deterministic candidate without requiring embedding similarity search

#### Scenario: Embedding search retrieves field-scoped candidates
- **WHEN** an extracted key-market item has wording that does not exactly match any configured alias
- **THEN** candidate generation uses `text-embedding-3-small` similarity search against key-market catalog entries only
- **AND** it returns a bounded top-K candidate list for that item

#### Scenario: Prompt excludes full catalog
- **WHEN** the ETL builds the canonicalization prompt after candidate generation
- **THEN** the prompt includes projected candidates for extracted items
- **AND** the prompt does not include unrelated catalog entries outside those projected candidates

#### Scenario: LLM cannot select outside candidates
- **WHEN** the canonicalization model returns a non-null `canonical` value
- **THEN** the ETL validates that the value is present in the item's projected candidate set and the corresponding catalog field

### Requirement: Preserve Original Extraction Data During Canonicalization
The ETL SHALL preserve each original extracted item's `name` and `rationale` during canonicalization. Company items SHALL also preserve `ticker` when present.

The ETL SHALL add a `canonical` field to each canonicalizable item without adding or removing extracted attributes.

#### Scenario: Metadata item gains canonical value
- **WHEN** an extracted metadata item is canonicalized
- **THEN** the output item contains the original `name`, original `rationale`, and a `canonical` value or null

#### Scenario: Company item preserves ticker
- **WHEN** an extracted company item with a `ticker` is canonicalized
- **THEN** the output item contains the original `name`, original `ticker`, original `rationale`, and a `canonical` value or null

#### Scenario: Canonicalization does not change item count
- **WHEN** a structured source contains canonicalizable attributes
- **THEN** the canonicalized output contains the same number of items in each canonicalized field

### Requirement: Use Canonicalized Alert Schema
The ETL SHALL define a `CanonicalizedAlert` schema that preserves source alert fields and canonicalized metadata arrays for `companies`, `sectors`, `geo_markets`, `key_markets`, `commodities`, `regulators`, `macro_sensitivities`, and `themes`.

Each canonicalized non-company metadata item SHALL contain `name`, `canonical`, and `rationale`. Each canonicalized company item SHALL contain `name`, `ticker`, `canonical`, and `rationale`. `canonical` SHALL be either an allowed canonical ID for the item's field or null.

#### Scenario: Valid canonicalized alert is accepted
- **WHEN** the canonicalization model returns a canonicalized alert conforming to the `CanonicalizedAlert` schema
- **THEN** the ETL validates the result before writing canonicalized output

#### Scenario: Invalid canonicalized alert is rejected
- **WHEN** the canonicalization model returns malformed item structure or a non-null canonical value outside the corresponding field catalog
- **THEN** the ETL reports a validation error and does not silently write malformed canonicalized output

### Requirement: Support Unmapped Canonical Values
The ETL SHALL treat null `canonical` values as valid canonicalization results.

The canonicalization prompt SHALL instruct the model to return null when no projected candidate is sufficiently equivalent, and SHALL prioritize precision over forced coverage.

#### Scenario: Weak mapping remains unmapped
- **WHEN** an extracted item is related to a catalog value but not sufficiently equivalent
- **THEN** canonicalization returns `canonical` set to null for that item

### Requirement: Reuse Canonicalization Logic For Alerts And Customer Profiles
The ETL SHALL provide one reusable canonicalization service that can operate on enriched alerts and customer profiles through a common canonicalization payload.

The ETL SHALL adapt customer-profile fields into the supported canonical fields before canonicalization and write a canonicalized customer-profile output.

#### Scenario: Alert and profile synonyms canonicalize consistently
- **WHEN** an enriched alert contains `warehouse robotics`
- **AND** a customer profile contains `automated warehouse systems`
- **AND** the catalog defines both as equivalent to `warehouse_automation`
- **THEN** both canonicalized outputs can contain `canonical` set to `warehouse_automation`

#### Scenario: Profile company lists canonicalize as companies
- **WHEN** a customer profile contains focal companies, competitors, suppliers, customers, or client company names
- **THEN** the canonicalization payload represents those values under the `companies` canonicalization field

### Requirement: Build Canonicalization Prompt
The ETL SHALL build a dedicated canonicalization prompt that includes the structured source attributes, projected canonical candidates, and field-specific canonicalization guidance.

The prompt SHALL instruct the model to use only projected candidate canonical IDs, match by meaning rather than exact wording, preserve meaningful differences, prefer specific mappings when appropriate, preserve original `name` and `rationale`, preserve company `ticker`, avoid adding or removing attributes, and return null for weak or unsupported mappings.

#### Scenario: Prompt includes candidates and source object
- **WHEN** the ETL builds a canonicalization prompt
- **THEN** the prompt includes the structured source object and projected candidates

#### Scenario: Prompt includes regulator guidance
- **WHEN** the ETL builds a canonicalization prompt
- **THEN** the prompt includes guidance that regulator outputs must be regulator entity canonical IDs and that law or regime mappings require explicit catalog relationships

### Requirement: Write Canonicalized Alert Dataset
The ETL SHALL write canonicalized alerts to a configurable processed output path separate from the enriched alert output path.

The canonicalized alert output SHALL remain a JSON array of `CanonicalizedAlert` objects. On each successful canonicalization run, canonicalized records from the current run SHALL replace existing records with the same alert `id`, preserve existing records with ids absent from the current run, and append records for new ids.

#### Scenario: Canonicalized alerts are written to new file
- **WHEN** canonicalization succeeds for enriched alerts
- **THEN** the ETL writes canonicalized alerts to the configured canonicalized alert output path without overwriting `etl/data/processed/enriched_alerts.json`

#### Scenario: Repeated canonicalization updates matching ids
- **WHEN** the canonicalized alert output already contains a record with the same `id` as a record canonicalized in the current run
- **THEN** the ETL replaces the stored canonicalized record for that `id` with the current run's canonicalized record

### Requirement: Expose Canonicalization Through CLI
The ETL CLI SHALL expose a canonicalization command that reads enriched alerts and the customer profile, canonicalizes both through the shared canonicalization logic, and writes separate canonicalized alert and customer-profile outputs.

#### Scenario: CLI canonicalizes enriched alerts and profile
- **WHEN** the user runs the canonicalization CLI command with configured input, profile, alert output, and profile output paths
- **THEN** the ETL reads enriched alerts and the customer profile, invokes canonicalization, writes canonicalized alerts, and writes the canonicalized customer profile

#### Scenario: Canonicalization command uses explicit outputs
- **WHEN** the canonicalization CLI command runs
- **THEN** it writes canonicalized artifacts to canonicalization-specific output paths rather than replacing the first-pass enriched alert dataset
