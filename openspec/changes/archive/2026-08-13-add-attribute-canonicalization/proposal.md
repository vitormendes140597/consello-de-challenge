## Why

First-pass extracted alert and customer-profile attributes can use different wording for the same concept, causing deterministic downstream matching to miss valid intersections. A dedicated canonicalization stage is needed now because extraction intentionally preserves source-supported wording and defers alias merging, taxonomy normalization, and regulator entity resolution.

## What Changes

- Add an LLM-powered canonicalization operation that receives a complete structured source object plus locally generated canonical candidates in one request, without sending the full catalog in the prompt.
- Add a maintainable canonical catalog for supported fields: `companies`, `sectors`, `geo_markets`, `key_markets`, `commodities`, `regulators`, `macro_sensitivities`, and `themes`.
- Add deterministic and embedding-backed candidate generation over the canonical catalog, using `text-embedding-3-small` for similarity search when exact alias and explicit mapping rules do not resolve a value.
- Add a `CanonicalizedAlert` output schema that preserves original extracted `name`, `ticker` where present, and `rationale`, while adding `canonical` to each canonicalizable item.
- Write canonicalized alerts to a new processed output file instead of overwriting first-pass enriched alerts.
- Reuse the same canonicalization logic for enriched alerts and customer profiles.
- Add CLI support for canonicalizing enriched alerts and the configured customer profile.
- Canonicalize regulator-related laws, regimes, aliases, acronyms, and regulator names to canonical regulator entity IDs when the catalog explicitly defines the relationship.
- Allow canonicalization to return `null` when no canonical value is sufficiently equivalent.
- Do not let the canonicalization LLM spawn subagents or call catalog-search tools directly; candidate generation is owned by the ETL orchestration layer.
- Do not add per-field/per-attribute canonicalization LLM calls.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `alert-extraction-etl`: Add post-extraction canonicalization, canonical catalog usage, canonicalized alert/profile output contracts, and CLI behavior.

## Impact

- Affects ETL schemas, canonical candidate retrieval, embedding/index cache handling, prompt construction, model orchestration, processing flow, JSON IO boundaries, CLI commands, default processed output paths, tests, and README documentation.
- Adds a catalog configuration file and validation/loading code.
- Uses the existing LangChain/OpenAI structured-output model pattern for the canonicalization model call and the OpenAI embeddings API with `text-embedding-3-small` for catalog similarity search.
