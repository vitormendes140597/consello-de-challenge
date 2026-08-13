## Context

The current ETL produces first-pass enriched alerts from raw alert text. It preserves source fields, extracts recall-oriented metadata, normalizes names to lower case, deduplicates within each alert, and writes `etl/data/processed/enriched_alerts.json`.

That output intentionally does not canonicalize aliases or map values to stable internal identifiers. Customer profiles contain overlapping conceptual fields, but profile values and alert values can use different wording for the same concept. Downstream relevance scoring needs deterministic intersections, so the ETL needs a separate canonicalization stage that standardizes extracted and profile attributes without replacing the original evidence-bearing extraction data.

The canonicalization stage must use an LLM in a single decision request per structured source object. To keep prompts bounded as the catalog grows, the ETL should generate a small set of candidates locally before invoking the LLM. Candidate generation should use deterministic catalog rules first and `text-embedding-3-small` similarity search when no strong deterministic match is available.

## Goals / Non-Goals

**Goals:**

- Add a reusable canonicalization service for enriched alerts and customer profiles.
- Preserve enriched alerts as first-pass extraction artifacts and write canonicalized alerts to a new output file.
- Add a `CanonicalizedAlert` schema whose metadata items preserve `name`, `ticker` where present, and `rationale`, and add `canonical`.
- Add a canonicalized customer profile output from the same canonicalization logic.
- Add a maintainable canonical catalog with allowed canonical IDs, labels, aliases, field-specific hints, and exclusions.
- Generate small candidate sets from the canonical catalog before the LLM call, instead of sending the full catalog to the LLM.
- Use `text-embedding-3-small` for embedding-backed similarity search over catalog entries after exact alias, label, ID, acronym, and explicit law/regime mappings have been checked.
- Use one structured-output LLM decision request per canonicalized alert or profile payload.
- Canonicalize regulator aliases, regulator names, laws, regimes, and review processes to regulator entity canonical IDs only when the catalog explicitly defines the relationship.
- Allow `canonical` to be `null` when no catalog value is sufficiently equivalent.
- Add CLI support for running canonicalization explicitly.

**Non-Goals:**

- Do not calculate customer-alert relevance scores.
- Do not replace first-pass extraction or force the extractor to emit canonical IDs.
- Do not overwrite `enriched_alerts.json` with canonicalized output.
- Do not send the full canonical catalog in every canonicalization prompt once candidate generation is available.
- Do not require an external vector database or long-lived retrieval service for this change.
- Do not let the canonicalization LLM spawn subagents or call catalog-search tools directly.
- Do not add separate per-field or per-attribute canonicalization LLM calls.
- Do not invent canonical values from model output.

## Decisions

### Store the catalog as versioned JSON and validate it with Pydantic

The catalog should live in a dedicated configuration file rather than being scattered through prompts or application code. A JSON file is easier to review and maintain than Python constants, while Pydantic validation keeps runtime behavior strict.

The catalog should use stable canonical IDs as object keys:

```json
{
  "version": 1,
  "fields": {
    "regulators": {
      "description": "Regulatory bodies or agencies. Laws and regimes may map to responsible regulator entities.",
      "values": {
        "cfius": {
          "label": "CFIUS",
          "aliases": [
            "committee on foreign investment in the united states"
          ],
          "law_or_regime_aliases": [],
          "related_terms": [
            "foreign investment review",
            "national security review"
          ],
          "exclude": [
            "us department of commerce"
          ],
          "description": "US interagency committee reviewing foreign investment for national security concerns."
        }
      }
    }
  }
}
```

Rationale: canonical IDs become the deterministic matching surface. Labels support readable debugging. Aliases represent strong equivalents. Related terms help the LLM reason without becoming automatic mappings. Exclusions reduce false positives.

Alternative considered: use a flat field-to-list catalog. This was rejected because regulators need explicit law/regime-to-entity mapping, and themes/key markets need guardrails between related but distinct concepts.

### Generate canonical candidates before invoking the LLM

Canonicalization should not depend on putting the full catalog in the model context. The ETL should create a projected candidate payload for each structured source object. For every extracted item, the candidate generator should:

1. Normalize the extracted value and check exact matches against canonical IDs, labels, aliases, acronyms, and field-specific strong aliases.
2. For regulators, check `law_or_regime_aliases` before semantic search and only allow law/regime-to-entity candidates when the catalog explicitly defines that relationship.
3. If no strong deterministic match exists, run similarity search against embeddings of catalog entries within the same field.
4. Return a small top-K candidate list with candidate IDs, labels, match source, similarity score when available, and boundary hints needed for the LLM to decide.

The LLM receives the complete structured source object and these candidates, not the full catalog. It may choose one candidate ID for each item or return `null`.

Rationale: candidate projection keeps prompt size stable as the catalog grows, makes catalog search testable outside the LLM, and reduces false positives by limiting the model to a small allowlist.

Alternative considered: allow the LLM to spawn subagents or call a catalog-search tool for each extracted value. This was rejected because it makes cost and latency harder to bound, complicates tests and retries, and puts retrieval policy inside the model rather than the ETL orchestration layer.

Alternative considered: deterministic matching only. This was rejected because aliases and source wording can drift beyond exact labels, especially for themes, key markets, sectors, and macro sensitivities.

### Use `text-embedding-3-small` for catalog similarity search

The ETL should build or load an embedding index for catalog search using `text-embedding-3-small`. Catalog entry text should include the canonical ID, label, aliases, related terms, field description, entry description, and law/regime aliases where applicable. The index should be versioned by catalog version and content hash so catalog edits trigger re-embedding.

Similarity search should be field-scoped. A company value should only search company candidates, a regulator value should only search regulator candidates, and so on.

Rationale: `text-embedding-3-small` gives a low-cost semantic retrieval layer that avoids repeatedly sending the full catalog to the canonicalization LLM. Field-scoped search reduces cross-field false positives.

Alternative considered: use an external vector database. This was rejected for the current scope because the catalog is still configuration-sized and can be searched with a local in-process index or persisted cache.

### Keep canonicalized schemas separate from enriched schemas

`EnrichedAlert` should remain the first-pass extraction contract. A new `CanonicalizedAlert` should preserve source alert fields and extracted metadata while adding `canonical` to every canonicalizable item.

Rationale: preserving first-pass output makes extraction behavior debuggable and allows canonicalization to be rerun after catalog edits without rerunning extraction.

Alternative considered: add `canonical` directly to `EnrichedAlert`. This was rejected because it would blur the boundary between extraction and standardization and make existing enriched output look like it had already passed through the new stage.

### Use a common canonicalization payload with adapters

The canonicalization service should operate on a common payload shaped around the supported canonical fields:

```text
companies
sectors
geo_markets
key_markets
commodities
regulators
macro_sensitivities
themes
```

Enriched alerts already use that shape. Customer profiles need an adapter that maps profile-specific keys into the common fields. For example, `client_name`, `focal_companies`, `competitors`, `suppliers`, and `customers` can contribute to `companies`; `sector` can contribute to `sectors`; existing profile arrays can map to their matching canonical fields.

Rationale: one canonicalization implementation can serve alerts and profiles while keeping profile IO and alert IO separate.

Alternative considered: build separate alert and profile canonicalizers. This was rejected because it would risk divergent semantics and inconsistent customer-alert matching.

### Canonicalize one source object per LLM decision request

Each canonicalization operation should send the complete structured source object, candidate projections, and field guidance in one structured-output LLM request. The implementation must not make canonicalization LLM calls per field or per attribute.

Rationale: field-level context matters. A single object-level decision request lets the model see all extracted values and apply consistent judgment across candidates, while candidate projection avoids sending the entire catalog and avoids excessive token use from batching an entire alert dataset into one request.

Alternative considered: canonicalize the whole alerts dataset in one model call. This was rejected because processed alert files can grow and would make failures harder to isolate and retry.

### Use structured outputs and validate allowed canonical IDs

The canonicalization model should be bound to a Pydantic structured output schema. The schema should enforce the output shape, and post-validation should reject any non-null `canonical` value not present in the corresponding field catalog or the item's projected candidate set.

Rationale: structured outputs ensure item shape, but catalog membership is dynamic configuration. Runtime validation must enforce the allowlist.

Alternative considered: trust the prompt instruction that the model will only emit allowed IDs. This was rejected because a false canonical mapping can create a false deterministic relevance match.

### Add explicit CLI canonicalization command

Canonicalization should be exposed as a separate CLI command, for example:

```bash
alert-extraction-etl canonicalize \
  --input-path data/processed/enriched_alerts.json \
  --client-profile-path data/raw/client_profile.json \
  --output-path data/processed/canonicalized_alerts.json \
  --profile-output-path data/processed/canonicalized_client_profile.json
```

Rationale: `run` remains raw-alert extraction, while `canonicalize` is an explicit post-processing stage that can be rerun after catalog changes.

Alternative considered: always run canonicalization automatically after extraction. This was rejected because extraction and canonicalization have different inputs, outputs, costs, and failure modes.

## Risks / Trade-offs

- Catalog drift or weak catalog entries can cause false matches -> keep catalog values conservative, support `null`, and validate canonical IDs after the model response.
- Embedding similarity can surface semantically related but non-equivalent candidates -> run deterministic explicit mappings first, keep top-K small, pass exclusions and boundary hints to the LLM, and allow `null`.
- Embedding/index cache drift can produce stale candidates -> key the cache by catalog version and content hash.
- Regulator law-to-entity mappings can be jurisdictionally ambiguous -> require explicit catalog relationships for law/regime aliases and return `null` when no relationship is configured.
- Profile adapter choices can hide profile field semantics -> document mappings and test representative profile fields.
- One call per alert can increase live-run cost after extraction -> keep canonicalization as an explicit CLI command and test with fake structured models.
- Candidate generation adds an embedding API dependency -> batch embedding requests and cache catalog embeddings so normal runs embed only new source values.
- The LLM can rewrite names or rationales despite instructions -> compare item counts and preserve original item fields through validation or reconstruction where practical.
- Existing processed files do not contain canonical fields -> write new output files and leave enriched output compatible with existing consumers.
