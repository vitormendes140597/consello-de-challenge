## ADDED Requirements

### Requirement: Write Profile-Shaped Canonicalized Client Profile
The ETL SHALL write the canonicalized client profile as a JSON object that
preserves the raw profile field structure and uses canonical catalog IDs as
canonicalized values.

The output SHALL preserve `client_name` and `ticker` unchanged from the raw
client profile. The output SHALL represent `sector` as a single canonical
catalog ID when mapped. The output SHALL represent `focal_companies`,
`competitors`, `suppliers`, `customers`, `geo_markets`, `key_markets`,
`commodities`, `regulators`, `macro_sensitivities`, and `themes` as arrays of
canonical catalog IDs.

The ETL SHALL preserve company relationship fields instead of collapsing them
into one profile-level `companies` array. The ETL SHALL deduplicate repeated
canonical IDs within each profile-shaped field while preserving first-seen order.
The ETL SHALL omit unmapped/null canonical values from profile-shaped output
fields.

#### Scenario: Identity fields are preserved
- **WHEN** canonicalization writes the client profile output
- **THEN** `client_name` and `ticker` match the raw client profile values
  unchanged

#### Scenario: Sector is emitted as a canonical ID
- **WHEN** the raw client profile contains `sector` and canonicalization maps it
  to a catalog ID
- **THEN** the canonicalized client profile contains `sector` set to that
  catalog ID

#### Scenario: Company relationships remain separate
- **WHEN** the raw client profile contains values in `focal_companies`,
  `competitors`, `suppliers`, and `customers`
- **THEN** the canonicalized client profile emits those same relationship fields
  separately as arrays of company catalog IDs
- **AND** it does not require consumers to recover those relationships from a
  collapsed `companies` array

#### Scenario: Duplicate canonical IDs are deduplicated
- **WHEN** multiple values in the same profile field map to the same canonical
  catalog ID
- **THEN** the canonicalized profile field contains that catalog ID only once

#### Scenario: Null canonical values are omitted
- **WHEN** a profile value cannot be mapped to a canonical catalog ID
- **THEN** the canonicalized profile output omits that value from the
  corresponding profile-shaped field

#### Scenario: Canonicalized alerts remain unchanged
- **WHEN** the ETL canonicalizes enriched alerts and the client profile in the
  same canonicalization run
- **THEN** canonicalized alerts retain their existing alert-shaped output
  contract
