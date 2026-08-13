## Context

The canonicalization pipeline currently adapts the raw customer profile into the
same common metadata payload used for alerts. That gives the model one consistent
canonicalization surface, but the written customer-profile artifact preserves
the common metadata shape rather than the input profile shape.

The raw profile distinguishes different company relationships:

- `client_name`
- `focal_companies`
- `competitors`
- `suppliers`
- `customers`

Those relationships matter for downstream relevance scoring and debugging. A
single canonical `companies` array loses the profile field that supplied each
company unless consumers inspect rationale strings or `source_profile`.

## Goals / Non-Goals

**Goals:**

- Write `canonicalized_client_profile.json` as a profile-shaped JSON object.
- Preserve `client_name` and `ticker` exactly from the raw profile.
- Emit catalog IDs as the canonical values for canonicalized profile fields.
- Preserve relationship-specific company fields.
- Deduplicate repeated canonical IDs within each profile field.
- Drop unmapped/null canonical values from profile-shaped fields.
- Reuse the existing catalog, candidate generation, one-request profile
  canonicalization decision, and validation rules.

**Non-Goals:**

- Do not change canonicalized alert output.
- Do not change the canonical catalog schema or candidate projection algorithm.
- Do not add a second LLM call for the profile output projection.
- Do not calculate downstream relevance scores.
- Do not preserve original unmapped profile values in the profile-shaped
  canonical fields.

## Decisions

### Add a profile-shaped schema separate from canonicalized alert metadata

The customer profile output should have fields matching the raw profile contract:

```json
{
  "client_name": "Solstice Robotics",
  "ticker": "SLRB",
  "sector": "industrial_automation",
  "focal_companies": ["solstice_robotics"],
  "competitors": ["kestrel_automation"],
  "suppliers": ["ferrotech_alloys"],
  "customers": ["meridian_auto_group"],
  "geo_markets": ["germany"],
  "key_markets": ["warehouse_automation"],
  "commodities": ["rare_earth_magnets"],
  "regulators": ["cfius"],
  "macro_sensitivities": ["interest_rates"],
  "themes": ["ai_driven_automation"]
}
```

Rationale: downstream consumers can intersect alerts with profile attributes
without interpreting alert-style item objects or recovering profile field
membership from rationale strings.

Alternative considered: keep `source_profile` plus metadata arrays and require
downstream consumers to project the shape themselves. This was rejected because
it duplicates field-mapping policy outside the ETL and makes relationship-aware
matching less deterministic.

### Reuse existing profile canonicalization, then project by profile field

The existing profile adapter should still create one common canonicalization
payload and the model should still make one decision for the complete profile.
After canonicalized metadata is reconstructed and validated, the ETL should
project canonical IDs back into profile fields using the known adapter mapping:

- `sector` uses the canonicalized item from `sectors`.
- `focal_companies`, `competitors`, `suppliers`, and `customers` use the
  canonicalized company items derived from the corresponding source profile
  field.
- `geo_markets`, `key_markets`, `commodities`, `regulators`,
  `macro_sensitivities`, and `themes` use their matching canonicalized metadata
  fields.

Rationale: this keeps retrieval, prompting, validation, and model-call count
unchanged while changing only the output contract.

Alternative considered: canonicalize each raw profile field independently. This
was rejected because it would add per-field model calls and diverge from the
existing object-level canonicalization requirement.

### Track profile field provenance structurally

Projection back to the raw profile shape needs reliable provenance for each
adapted item. The adapter should retain the source profile field internally
rather than depending on generated rationale text.

Rationale: rationale strings are human-readable evidence, not a stable internal
mapping key. Structural provenance makes deduplication and field projection
testable.

Alternative considered: parse `Customer profile field <field> value.` from the
rationale. This was rejected because it is brittle and breaks when profile
object values provide custom rationales.

### Deduplicate and omit nulls during profile output projection

For each profile-shaped field, the ETL should keep only non-null canonical IDs
and preserve first-seen order while removing duplicates.

Rationale: the profile-shaped artifact is intended as the deterministic matching
surface. Duplicate IDs add no scoring information, and nulls are useful for
debugging the canonicalization decision but not for downstream intersections.

Alternative considered: preserve one output slot per source profile value. This
was rejected because the user explicitly wants deduplicated arrays with nulls
dropped.

### Treat `sector` as optional when unmapped

`sector` is a single string in the raw profile. In the canonicalized profile, it
should be a single catalog ID when mapped and absent or null when unmapped.

Rationale: this mirrors the "drop nulls" rule for arrays while preserving the
fact that sector is singular.

Alternative considered: emit `sector` as an empty array for consistency with
other fields. This was rejected because it would unnecessarily change the raw
profile field type.

## Risks / Trade-offs

- **Breaking output shape** -> Update tests and README, and keep canonicalized
  alerts unchanged so the blast radius is limited to profile consumers.
- **Loss of unmapped source values in the profile-shaped artifact** -> Preserve
  raw input in `etl/data/raw/client_profile.json`; use canonicalization logs or
  tests for mapping diagnostics.
- **Field provenance mismatch** -> Add focused adapter tests covering duplicate
  focal-company aliases, competitors, suppliers, customers, and object-shaped
  profile entries.
- **Catalog gaps produce shorter output arrays** -> This is intentional under
  the drop-null rule; tests should assert missing mappings are omitted.
