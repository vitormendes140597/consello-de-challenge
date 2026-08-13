## Why

The ETL already canonicalizes the raw client profile, but the current output uses
the same metadata-array shape as canonicalized alerts and collapses profile
relationship fields into one `companies` array. Downstream consumers need a
profile-shaped artifact that preserves `focal_companies`, `competitors`,
`suppliers`, and `customers` while replacing canonicalizable values with stable
catalog IDs.

## What Changes

- Add a profile-shaped canonicalized client profile output contract.
- Preserve `client_name` and `ticker` unchanged from the raw profile.
- Convert `sector` to one canonical catalog ID when mapped.
- Convert profile arrays to arrays of canonical catalog IDs.
- Preserve company relationship fields instead of collapsing them into a shared
  `companies` array.
- Deduplicate repeated canonical IDs within each profile field.
- Drop unmapped/null canonical values from profile-shaped fields.
- Keep canonicalized alerts unchanged.
- **BREAKING**: `etl/data/processed/canonicalized_client_profile.json` changes
  from `source_profile` plus alert-style metadata arrays to the profile-shaped
  canonical ID contract.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `alert-extraction-etl`: Change the canonicalized customer profile output
  requirement to emit a profile-shaped JSON object using catalog IDs, with
  per-field deduplication and unmapped values omitted.

## Impact

- Affects canonicalized customer profile schemas, profile adapters, JSON output
  shape, CLI canonicalization output behavior, tests, and ETL README
  documentation.
- Does not change canonicalized alert output shape, canonical candidate
  generation, catalog schema, embedding cache behavior, or extraction behavior.
