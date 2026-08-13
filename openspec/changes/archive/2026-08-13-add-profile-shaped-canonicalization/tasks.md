## 1. Schema And Adapter Contracts

- [x] 1.1 Add a profile-shaped canonicalized client profile schema that preserves `client_name` and `ticker`, represents `sector` as an optional catalog ID, and represents canonicalized profile arrays as catalog ID lists.
- [x] 1.2 Add internal profile item provenance so adapted profile values retain their source profile field without relying on rationale text.
- [x] 1.3 Update customer-profile canonicalization conversion to return the profile-shaped schema instead of `source_profile` plus alert-style metadata arrays.

## 2. Profile Output Projection

- [x] 2.1 Implement projection from canonicalized profile metadata back to `focal_companies`, `competitors`, `suppliers`, and `customers`.
- [x] 2.2 Implement projection for `sector`, `geo_markets`, `key_markets`, `commodities`, `regulators`, `macro_sensitivities`, and `themes`.
- [x] 2.3 Deduplicate canonical IDs within each profile-shaped field while preserving first-seen order.
- [x] 2.4 Drop null/unmapped canonical values from profile-shaped output fields.
- [x] 2.5 Keep canonicalized alert output and merge-by-id behavior unchanged.

## 3. Tests

- [x] 3.1 Add schema tests for valid profile-shaped canonicalized client profiles.
- [x] 3.2 Add adapter/projection tests for relationship-specific company fields.
- [x] 3.3 Add tests proving duplicate profile aliases collapse to one canonical ID within a field.
- [x] 3.4 Add tests proving unmapped/null canonical values are omitted from profile-shaped output.
- [x] 3.5 Update canonicalization processing tests for the new written `canonicalized_client_profile.json` shape.
- [x] 3.6 Run the relevant ETL test suite.

## 4. Documentation And Sample Data

- [x] 4.1 Update the ETL README canonicalized customer profile output section.
- [x] 4.2 Regenerate or update `etl/data/processed/canonicalized_client_profile.json` to match the profile-shaped contract.
- [x] 4.3 Review the diff for accidental changes to canonicalized alert output, catalog data, or extraction behavior.
