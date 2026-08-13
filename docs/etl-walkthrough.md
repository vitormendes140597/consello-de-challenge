# ETL Walkthrough

This walkthrough explains the `etl` package for engineers who are seeing the
project for the first time. The ETL exists to turn noisy media-alert emails into
structured data that the alert scorer can rank for one client relationship.

## High-Level Overview

Consello advisors receive a continuous stream of market-news alerts. A single
client may be affected directly, when the alert names the client, or indirectly,
when it mentions a competitor, supplier, customer, regulator, market,
commodity, or macro theme connected to the client. The ETL prepares that raw
news stream for downstream ranking by producing clean, canonical artifacts.

The package has two model-assisted stages:

1. **Attribute extraction** uses `DATA_EXTRACTOR_MODEL=o3-mini` to extract
   first-pass metadata from each raw alert.
2. **Canonicalization** uses `STANDARD_DATA_MODEL=o3-mini` to map extracted
   metadata and customer-profile values onto stable IDs from a catalog.

It also uses `STANDARD_DATA_EMBEDDING_MODEL=text-embedding-3-small` to build or
query a local catalog embedding index for candidate retrieval.

```text
+-----------------------+      +----------------------+      +-----------------------+
| Raw media alerts      | ---> | Attribute extraction | ---> | Enriched alerts       |
| sample_alerts.json    |      | o3-mini              |      | enriched_alerts.json  |
+-----------------------+      +----------------------+      +-----------------------+
                                         |
                                         v
+-----------------------+      +----------------------+      +-----------------------+
| Customer profile      | ---> | Canonicalization     | ---> | Canonical artifacts   |
| Canonical catalog     |      | o3-mini + candidates |      | alerts + profile JSON |
+-----------------------+      +----------------------+      +-----------------------+
```

The split is intentional. Extraction is recall-oriented: capture plausible
entities and exposures from the alert text. Canonicalization is
precision-oriented: map only to supported IDs and return `null` when the match
is weak. Keeping those jobs separate makes each prompt easier to reason about,
test, and validate.

## Directory Map

```text
etl/
|-- data
|   |-- raw
|   |   |-- sample_alerts.json
|   |   |-- client_profile.json
|   |   `-- client2_profile.json
|   |-- config
|   |   `-- canonical_catalog.json
|   `-- processed
|       |-- enriched_alerts.json
|       |-- canonical_embedding_index.json
|       |-- canonicalized_alerts.json
|       `-- canonicalized_client_profile.json
|-- src
|   `-- etl
|       |-- app
|       |   `-- cli.py
|       |-- common
|       |   |-- config.py
|       |   |-- fields.py
|       |   |-- io.py
|       |   |-- openai.py
|       |   `-- schemas.py
|       |-- extraction
|       |   |-- model.py
|       |   |-- postprocessing.py
|       |   |-- processing.py
|       |   `-- prompts.py
|       `-- canonicalization
|           |-- candidates.py
|           |-- catalog.py
|           |-- processing.py
|           |-- prompts.py
|           |-- schemas.py
|           `-- service.py
|-- tests
|-- README.md
`-- pyproject.toml
```

## `etl.app`: CLI Entry Point

`etl.app.cli` exposes the package workflow as command-line actions:

- `run`: load raw alerts, extract attributes, write enriched alerts.
- `prompt`: print the extraction prompt for one raw alert without calling the
  model.
- `canonicalize`: load enriched alerts, customer profile, catalog, candidate
  index, run canonicalization, and write canonical artifacts.

```text
+--------------------------+
| python -m etl.app.cli    |
+------------+-------------+
             |
             v
+------------+-------------+
| argparse command router  |
+-----+-----------+--------+
      |           |
      v           v
+-----+-----+  +--+----------------+
| run       |  | canonicalize      |
| extract   |  | standardize data  |
+-----------+  +-------------------+
```

The CLI is deliberately thin. It parses paths and environment-backed model
settings, then delegates to package functions. That keeps the core ETL testable
without shelling out to the command line.

Example command:

```bash
python -m etl.app.cli canonicalize \
  --input-path etl/data/processed/enriched_alerts.json \
  --client-profile-path etl/data/raw/client_profile.json \
  --catalog-path etl/data/config/canonical_catalog.json \
  --embedding-index-path etl/data/processed/canonical_embedding_index.json \
  --output-path etl/data/processed/canonicalized_alerts.json \
  --profile-output-path etl/data/processed/canonicalized_client_profile.json
```

## `etl.common`: Shared Boundaries

`etl.common` contains the reusable foundations:

- `config.py`: default file paths and environment variable parsing.
- `fields.py`: shared metadata field names.
- `schemas.py`: Pydantic schemas for raw and enriched alerts.
- `io.py`: JSON reads/writes, validation loaders, and merge-by-id storage.
- `openai.py`: LangChain `ChatOpenAI` construction.

```text
+-------------------+      +-------------------+      +-------------------+
| JSON files        | ---> | AlertDataLoader   | ---> | Pydantic records  |
+-------------------+      +-------------------+      +-------------------+
                                      |
                                      v
                         +------------+-------------+
                         | JsonRecordStore          |
                         | atomic JSON merge by id  |
                         +--------------------------+
```

Input evidence, from `etl/data/raw/sample_alerts.json`:

```json
{
  "id": "a01",
  "received_at": "2026-08-11T09:00:00+00:00",
  "subject": "Solstice Robotics Beats Q2 Estimates, Raises Full-Year Guidance",
  "body": "Solstice Robotics (SLRB) reported Q2 revenue of $412M, above the $389M consensus, driven by strong bookings in warehouse automation. Management raised full-year revenue guidance to $1.68-1.72B and cited accelerating demand from e-commerce fulfillment customers. Shares rose 6% in after-hours trading."
}
```

The important architectural choice here is using Pydantic at every file
boundary. That turns malformed inputs into explicit validation failures before
model calls or writes happen. `JsonRecordStore` also merges by `id`, so repeated
runs can update processed data without blindly duplicating alerts.

## `etl.extraction`: Attribute Extraction

The extraction module turns raw alert text into first-pass metadata arrays:

- `prompts.py` defines reusable field guidance for `companies`, `sectors`,
  `geo_markets`, `key_markets`, `commodities`, `regulators`,
  `macro_sensitivities`, and `themes`.
- `model.py` binds the chat model to the `AlertMetadata` structured-output
  schema.
- `postprocessing.py` lower-cases names/tickers and deduplicates values.
- `processing.py` orchestrates per-alert enrichment using a
  `ThreadPoolExecutor(max_workers=20)`.

```text
+---------------------+
| RawAlert            |
| id/received/subject |
| body                |
+----------+----------+
           |
           v
+----------+----------+      +-------------------------------+
| build_synthesis_    | ---> | OpenAI chat model             |
| prompt              |      | DATA_EXTRACTOR_MODEL=o3-mini  |
+----------+----------+      | structured AlertMetadata      |
           |                 +---------------+---------------+
           |                                 |
           v                                 v
+----------+----------+      +---------------+---------------+
| Prompt context      |      | normalize + dedupe metadata   |
| alert + rules       |      +---------------+---------------+
+---------------------+                      |
                                             v
                                +------------+-------------+
                                | EnrichedAlert JSON       |
                                +--------------------------+
```

### Model Choice And Context Window

Attribute extraction uses `DATA_EXTRACTOR_MODEL=o3-mini` in the local
configuration. That is a reasonable fit because the task is not open-ended
generation; it is bounded analytical extraction. The model needs to separate
similar concepts, such as a sector versus a key market, or a regulator versus a
country, while returning a strict schema. `o3-mini` gives enough reasoning
capacity for those distinctions without making each per-alert call as expensive
as a larger reasoning model.

The prompt context contains:

- extraction persona;
- raw alert `subject`;
- raw alert `body`;
- optional client profile hints;
- global rules, such as no hallucination, lower-case names, empty arrays when
  unsupported, concise rationales, and no canonical IDs;
- one field-specific prompt section per extracted metadata field.


Prompt evidence, shortened from `python -m etl.app.cli prompt --alert-id a13`:

```text
You are a careful financial news metadata extraction analyst. Read only the provided alert text and contextual hints. Extract recall-oriented first-pass metadata for downstream canonicalization, keeping each concept in its proper field and grounding every rationale in the alert evidence.

<news>
<subject>
Solstice Robotics Beats Q2 Estimates, Raises Full-Year Guidance
</subject>
<body>
Solstice Robotics (SLRB) reported Q2 revenue of $412M, above the $389M consensus, driven by strong bookings in warehouse automation. Management raised full-year revenue guidance to $1.68-1.72B and cited accelerating demand from e-commerce fulfillment customers. Shares rose 6% in after-hours trading.
</body>
</news>

<global_rules>
- Do not hallucinate facts that are absent from the subject or body.
- Return lower-case names for all extracted companies and metadata items.
- Return lower-case tickers when present; use null when unavailable.
- Return an empty array when a field has no supported values.
- Keep rationales concise and grounded in alert evidence.
- Do not canonicalize aliases or map values to stable internal identifiers.
</global_rules>

<prompt_sections>

<prompt_section name="companies">
## companies
Purpose: Extract named operating businesses that are relevant to the alert.
Include: Focal companies, competitors, suppliers, customers, partners, acquirers, acquisition targets, and other named business entities.
Exclude: Countries, regions, regulators, laws, markets, sectors, commodities, macro drivers, investment themes, people, and generic organization types.
Evidence standard: Include a company only when the subject or body names it or clearly refers to a specific operating business.
Normalization: Return company names in lower case. Return tickers in lower case when explicitly present or highly confident; otherwise use null.
Rationale: Explain the alert evidence that makes the company relevant.
Edge cases: Do not put a country, customer market, regulator, or commodity in companies even when it affects a company.
</prompt_section>

<prompt_section name="sectors">
## sectors
Purpose: Extract broad industries or business verticals affected by the alert.
Include: Industries such as industrial automation, logistics, automotive, semiconductors, manufacturing, or robotics when materially affected.
Exclude: Single company names, specific product markets, customer markets, countries, regulators, commodities, and broad investment themes.
Evidence standard: Include a sector when the alert states it directly or the body gives clear industry-level context.
Normalization: Return sector names in lower case.
Rationale: Explain the text evidence connecting the alert to the sector.
Edge cases: Prefer key_markets for narrower demand pools such as warehouse automation or automotive manufacturing.
</prompt_section>

<prompt_section name="geo_markets">
## geo_markets
Purpose: Extract countries or regions materially connected to the alert.
Include: Countries, regions, trade blocs, or named geographies tied to operations, demand, supply chains, regulation, investment, or manufacturing.
Exclude: Company names, facility names without geographic meaning, vague phrases like overseas, and markets that are not geographic.
Evidence standard: Include a geography only when the subject or body mentions it or clearly ties it to the event.
Normalization: Return geographic market names in lower case.
Rationale: Explain why the geography matters to the alert.
Edge cases: A city can support a country or region when the country or region is material to the event.
</prompt_section>

<prompt_section name="key_markets">
## key_markets
Purpose: Extract specific product, end, customer, or demand markets.
Include: Markets such as warehouse automation, automotive manufacturing, e-commerce fulfillment, control chips, or robotics components.
Exclude: Broad sectors, individual company names, countries, regulators, raw materials, and abstract themes.
Evidence standard: Include a key market when the alert ties products, customers, demand, or applications to the event.
Normalization: Return key market names in lower case.
Rationale: Explain the alert evidence for the affected market.
Edge cases: If a phrase is broad industry context, put it in sectors instead of key_markets.
</prompt_section>

<prompt_section name="commodities">
## commodities
Purpose: Extract physical inputs whose availability, pricing, or supply matters.
Include: Raw materials, traded goods, industrial inputs, components, chips, magnets, bearings, motors, or other physical supply items.
Exclude: Broad industries, end markets, regulators, companies, macro drivers, and themes.
Evidence standard: Include a commodity or component when the alert links it to supply, cost, pricing, availability, production, or demand.
Normalization: Return commodity and component names in lower case.
Rationale: Explain the text evidence for why the input matters.
Edge cases: Treat components as commodities for this first pass when they create supply, cost, or production exposure.
</prompt_section>

<prompt_section name="regulators">
## regulators
Purpose: Extract regulatory bodies, laws, regimes, or formal review processes.
Include: Agencies, laws, enforcement regimes, export controls, national security reviews, compliance processes, and formal regulatory actions.
Exclude: Generic government mentions, countries without regulatory action, political themes, macro risks, and company names.
Evidence standard: Include a regulator or regime when the alert names it or clearly describes a formal regulatory action.
Normalization: Return regulator and regime names in lower case.
Rationale: Explain the regulatory evidence and why it matters.
Edge cases: Use geo_markets for countries unless the country reference is tied to a specific regulatory action.
</prompt_section>

<prompt_section name="macro_sensitivities">
## macro_sensitivities
Purpose: Extract broad economic or geopolitical drivers affecting the alert.
Include: Interest rates, tariffs, reshoring, labor costs, trade restrictions, geopolitical risk, financing conditions, inflation, or demand cycles.
Exclude: Specific companies, sectors, product markets, countries without macro driver relevance, commodities, and regulators.
Evidence standard: Include a macro sensitivity when the alert links it to valuation, demand, margins, financing, operations, or supply chains.
Normalization: Return macro sensitivity names in lower case.
Rationale: Explain the economic or geopolitical exposure in the alert.
Edge cases: Do not infer a macro driver just because a company is in a cyclical sector; require alert evidence.
</prompt_section>

<prompt_section name="themes">
## themes
Purpose: Extract strategic or investment themes explaining why the alert matters.
Include: Themes such as AI-driven automation, labor shortage, supply chain resilience, nearshoring, productivity gains, or vertical integration.
Exclude: Literal company names, countries, regulators, sectors, narrow markets, commodities, and one-off facts that do not generalize.
Evidence standard: Include a theme when the alert supports a broader strategic or investment interpretation beyond a single fact.
Normalization: Return theme names in lower case.
Rationale: Explain the alert evidence supporting the theme.
Edge cases: Prefer macro_sensitivities for economic drivers and key_markets for specific demand pools.
</prompt_section>

</prompt_sections>

```

Example structured model output for alert `a01`, represented by the enriched
artifact:

```json
{
  "companies": [
    {
      "name": "solstice robotics",
      "ticker": "slrb",
      "rationale": "the alert clearly names solstice robotics and provides its ticker (slrb) reporting Q2 revenue and guidance."
    }
  ],
  "sectors": [
    {
      "name": "robotics",
      "rationale": "the company's name and focus on automation imply it operates in the robotics sector."
    }
  ],
  "key_markets": [
    {
      "name": "warehouse automation",
      "rationale": "the alert cites strong bookings in warehouse automation as a revenue driver."
    },
    {
      "name": "e-commerce fulfillment",
      "rationale": "accelerating demand from e-commerce fulfillment customers is highlighted."
    }
  ],
  "geo_markets": [],
  "commodities": [],
  "regulators": [],
  "macro_sensitivities": [],
  "themes": []
}
```

The extraction stage intentionally does not canonicalize. It preserves recall
and evidence capture, then hands ambiguity to a second stage that has catalog
context and stricter validation.

## `etl.canonicalization`: Catalog Mapping

Canonicalization maps first-pass metadata to stable IDs:

- `catalog.py` loads and validates the canonical catalog.
- `candidates.py` generates item-specific candidates through deterministic
  matches and optional embedding similarity.
- `prompts.py` builds a canonicalization prompt with the source payload and
  only the projected candidates.
- `service.py` invokes the model and validates the decision.
- `processing.py` adapts both enriched alerts and customer profiles into a
  shared payload, then writes alert-shaped and profile-shaped outputs.
- `schemas.py` defines catalog, candidate, decision, and canonicalized output
  contracts.

```text
+----------------------+      +-------------------------+
| EnrichedAlert        |      | Customer profile        |
+----------+-----------+      +------------+------------+
           |                               |
           v                               v
+----------+-----------+      +------------+------------+
| Alert metadata       |      | Profile adapter         |
| payload              |      | CanonicalizationPayload |
+----------+-----------+      +------------+------------+
           |                               |
           +---------------+---------------+
                           v
              +------------+-------------+
              | Candidate generator      |
              | catalog + embeddings     |
              +------------+-------------+
                           |
                           v
              +------------+-------------+
              | o3-mini canonicalizer    |
              | structured decision      |
              +------------+-------------+
                           |
                           v
              +------------+-------------+
              | Validate + reconstruct   |
              | canonicalized outputs    |
              +--------------------------+
```

### Candidate Generation

The candidate generator first normalizes source text with case folding and
punctuation cleanup. It then looks for deterministic matches against canonical
IDs, labels, aliases, acronyms, and explicit `law_or_regime_aliases` for
regulator-law mappings. If there is not exactly one deterministic candidate and
an embedding client is available, it searches a field-scoped embedding index.

The embedding model is `STANDARD_DATA_EMBEDDING_MODEL=text-embedding-3-small`.
The catalog index embeds text shaped like:

```text
field: key_markets
field description: Product, application, customer, or demand-pool markets...
canonical id: warehouse_automation
label: Warehouse Automation
description: Automation systems and robotics used in warehouse operations.
aliases: warehouse automation, warehouse robotics, automated warehousing
related terms: picking arms, distribution centers
exclude: logistics
```

Query-time embedding input is the normalized extracted value, such as
`e commerce fulfillment`.

This design keeps the full catalog out of the canonicalization prompt. The
model sees only candidates that local logic projected for each item, reducing
context size and lowering the chance that the model chooses unsupported IDs.

Example candidate projection for alert `a01`:

```json
{
  "catalog_version": 1,
  "items": [
    {
      "field": "companies",
      "item_index": 0,
      "name": "solstice robotics",
      "candidates": [
        {
          "canonical_id": "solstice_robotics",
          "label": "Solstice Robotics",
          "match_source": "canonical_id"
        }
      ]
    },
    {
      "field": "key_markets",
      "item_index": 1,
      "name": "e-commerce fulfillment",
      "candidates": [
        {
          "canonical_id": "ecommerce_fulfillment",
          "label": "E-commerce Fulfillment",
          "match_source": "label"
        }
      ]
    }
  ]
}
```

The canonicalization prompt contains:

- canonicalization persona;
- complete structured `source_payload`;
- item-specific `projected_candidates`;
- global rules requiring candidate-only IDs, `null` for weak matches, no
  reordering, and exact source-item alignment;
- field guidance for every canonicalizable field;
- regulator-specific guidance that prevents loose law-to-regulator mappings.

Prompt evidence, shortened from alert `a01`:

```text
<source_payload>
{
  "id": "a01",
  "subject": "Solstice Robotics Beats Q2 Estimates, Raises Full-Year Guidance",
  "companies": [{"name": "solstice robotics", "ticker": "slrb"}],
  "sectors": [{"name": "robotics"}],
  "key_markets": [{"name": "warehouse automation"}, {"name": "e-commerce fulfillment"}]
}
</source_payload>

<projected_candidates>
{
  "items": [
    {
      "field": "companies",
      "item_index": 0,
      "candidates": [{"canonical_id": "solstice_robotics"}]
    },
    {
      "field": "sectors",
      "item_index": 0,
      "candidates": [{"canonical_id": "industrial_robotics"}]
    }
  ]
}
</projected_candidates>
```

Example structured model decision:

```json
{
  "companies": [{"canonical": "solstice_robotics"}],
  "sectors": [{"canonical": "industrial_robotics"}],
  "geo_markets": [],
  "key_markets": [
    {"canonical": "warehouse_automation"},
    {"canonical": "ecommerce_fulfillment"}
  ],
  "commodities": [],
  "regulators": [],
  "macro_sensitivities": [],
  "themes": []
}
```

The service validates that the decision:

- preserves the exact number and order of source items;
- returns only IDs from the projected candidates for that item;
- returns only IDs that exist in the catalog;
- maps regulator laws or regimes only through explicit catalog support.

Those checks are important because they turn the LLM into a constrained
adjudicator instead of letting it mutate the dataset.

## Alert Output Evidence

Input to canonicalization, from `etl/data/processed/enriched_alerts.json`:

```json
{
  "id": "a01",
  "companies": [
    {
      "name": "solstice robotics",
      "ticker": "slrb",
      "rationale": "the alert clearly names solstice robotics and provides its ticker (slrb) reporting Q2 revenue and guidance."
    }
  ],
  "sectors": [{"name": "robotics"}],
  "key_markets": [{"name": "warehouse automation"}, {"name": "e-commerce fulfillment"}]
}
```

Output from canonicalization, from
`etl/data/processed/canonicalized_alerts.json`:

```json
{
  "id": "a01",
  "companies": [
    {
      "name": "solstice robotics",
      "ticker": "slrb",
      "canonical": "solstice_robotics",
      "rationale": "the alert clearly names solstice robotics and provides its ticker (slrb) reporting Q2 revenue and guidance."
    }
  ],
  "sectors": [{"name": "robotics", "canonical": "industrial_robotics"}],
  "key_markets": [
    {"name": "warehouse automation", "canonical": "warehouse_automation"},
    {"name": "e-commerce fulfillment", "canonical": "ecommerce_fulfillment"}
  ]
}
```

The raw alert fields and original rationales are preserved. Canonicalization
only attaches the `canonical` IDs needed by the downstream scorer.

## Customer Profile Canonicalization

The profile path matters because relevance is client-specific. The scorer needs
canonical IDs for the client's own company, competitors, suppliers, customers,
markets, regulators, and themes.

```text
+-------------------------+
| client_profile.json     |
| relationship fields     |
+------------+------------+
             |
             v
+------------+------------+
| Profile adapter         |
| profile -> metadata     |
+------------+------------+
             |
             v
+------------+------------+
| Shared canonicalization |
| candidates + o3-mini    |
+------------+------------+
             |
             v
+------------+------------+
| Profile-shaped output   |
| canonical ID arrays     |
+-------------------------+
```

Input profile evidence:

```json
{
  "client_name": "Solstice Robotics",
  "ticker": "SLRB",
  "competitors": ["Kestrel Automation", "ArcWorks Robotics"],
  "suppliers": ["Ferrotech Alloys", "Quanta Sensing"],
  "geo_markets": ["Germany", "South Korea", "Mexico", "United States"],
  "key_markets": ["industrial automation", "warehouse automation"],
  "regulators": ["US Department of Commerce", "EU AI Act", "CFIUS"]
}
```

Output profile evidence:

```json
{
  "client_name": "Solstice Robotics",
  "ticker": "SLRB",
  "sector": "industrial_automation",
  "focal_companies": ["solstice_robotics"],
  "competitors": ["kestrel_automation", "arcworks_robotics", "vantage_motion_systems"],
  "suppliers": ["ferrotech_alloys", "quanta_sensing", "delta_servo_corp"],
  "geo_markets": ["germany", "south_korea", "mexico", "united_states"],
  "key_markets": ["warehouse_automation", "automotive_manufacturing"],
  "regulators": ["us_department_of_commerce", "european_commission", "cfius"]
}
```

Using the same canonicalization path for alerts and profiles avoids maintaining
two subtly different mapping systems. The adapter records source-field
provenance so the final result can be projected back into a profile-shaped JSON
object.

## End-To-End ETL Flow

```text
+--------------------------+
| 1. Raw input             |
| sample_alerts.json       |
| client_profile.json      |
+------------+-------------+
             |
             v
+------------+-------------+
| 2. Validate JSON shapes  |
| RawAlert / profile map   |
+------------+-------------+
             |
             v
+------------+-------------+
| 3. Extract attributes    |
| o3-mini -> AlertMetadata |
+------------+-------------+
             |
             v
+------------+-------------+
| 4. Normalize + merge     |
| enriched_alerts.json     |
+------------+-------------+
             |
             v
+------------+-------------+
| 5. Project candidates    |
| catalog + embeddings     |
+------------+-------------+
             |
             v
+------------+-------------+
| 6. Canonicalize          |
| o3-mini -> IDs/null      |
+------------+-------------+
             |
             v
+------------+-------------+
| 7. Validate + write      |
| canonicalized artifacts  |
+--------------------------+
```

The final artifacts consumed by the scorer are:

- `etl/data/processed/canonicalized_alerts.json`
- `etl/data/processed/canonicalized_client_profile.json`

### When Step 6 Calls An LLM

Step 6 is the second chat-model stage in the ETL. It uses
`STANDARD_DATA_MODEL=o3-mini` to choose canonical IDs from the projected
candidates. But honestly it can be run with the cheapest model that will be fine.

The ETL needs this step because candidate generation is retrieval, not final
judgment. Step 5 can say "these are plausible catalog IDs for this extracted
item," but it should not automatically decide that the item truly means the
same thing as one candidate. Step 6 asks the model to adjudicate that final
semantic match under strict rules.

For example, embedding similarity might retrieve a regulator, market, or theme
because the words are close, but the correct output may still be `null` if the
alert only mentions a nearby concept. The canonicalization LLM receives the
source item, its rationale, the surrounding alert/profile payload, and only the
projected candidates. It then chooses one candidate ID or `null`.

This separation is deliberate:

- deterministic and embedding logic narrow the search space;
- `o3-mini` handles the semantic decision that needs context;
- validation rejects any ID outside the projected candidates or catalog;
- downstream scoring receives stable IDs instead of raw phrases or weak
  embedding guesses.

### Why Not Use Cosine Similarity Alone?

A simpler implementation could embed every extracted value, compute cosine
similarity against catalog entries, and pick the highest-ranked result. That
would be cheaper and faster, but it would be less safe for this product
problem.

Cosine similarity answers "which catalog item is semantically close?" It does
not reliably answer "is this close item the correct canonical identity for
downstream scoring?" That distinction matters because canonical IDs become
strong signals in the relevance scorer. A false-positive canonical ID can make
an irrelevant alert look client-relevant.

Examples:

- `industrial automation` can be close to `warehouse automation`, but one is a
  broad sector and the other is a narrower key market.
- `EU AI Act` can be close to `European Commission`, but the ETL should only
  map a law or regime to a regulator entity when the catalog explicitly allows
  that relationship.
- `robotics components` can be close to `industrial_robotics`, but in some
  alerts it is a commodity/input exposure rather than a sector.
- `logistics` can be close to `e-commerce fulfillment`, but the catalog may
  intentionally exclude that broader term to avoid collapsing distinct markets.

The implemented design uses cosine similarity as retrieval, then uses `o3-mini`
as a constrained adjudicator:

```text
cosine similarity -> shortlist of candidates
o3-mini           -> choose one candidate or null
validation        -> reject unsupported IDs or shape changes
```

This costs more than a cosine-only approach, but it is a better fit for an
advisor workflow where precision and explainability matter. A cosine-only mode
could still be useful as a fast fallback if it had high per-field thresholds
and field-specific guardrails, but it should not be the default path for
client-facing relevance scoring.

During `python -m etl.app.cli canonicalize`, the chat LLM is called:

- once for each enriched alert loaded from
  `etl/data/processed/enriched_alerts.json`;
- once more for the customer profile loaded from
  `etl/data/raw/client_profile.json`.

So if the enriched input contains 30 alerts, the canonicalization command makes
31 `o3-mini` canonicalization requests: 30 alert requests plus 1 profile
request.

The embedding model is separate from this. `text-embedding-3-small` is used by
the candidate generator before the canonicalization prompt is built. It may be
called to build or rebuild `canonical_embedding_index.json`, and to embed source
values when embedding similarity is needed. If a value has exactly one strong
deterministic match, such as an exact alias match, the candidate generator does
not need embedding search for that value.

In short:

```text
Step 5 candidate generation:
  may call text-embedding-3-small for catalog/source similarity

Step 6 canonicalization:
  calls o3-mini once per enriched alert
  calls o3-mini once for the customer profile
```

This is why candidate generation exists as a separate local step. The LLM in
Step 6 does not receive the full catalog and does not search freely. It receives
only the source payload plus the projected candidates for each item, then
returns either one candidate ID or `null`.

## Operational Notes

- The default extraction output is merged by alert `id`, which makes repeated
  local runs safer for growing alert datasets.
- The extraction stage currently runs per-alert model calls in parallel with 20
  workers because each alert is independent and OpenAI latency is the slow
  step.
- The canonical catalog is validated before model calls, so missing fields or
  unsupported catalog shapes fail early.
- The embedding index is compatible only when catalog version, catalog content
  hash, and embedding model match. Catalog edits or embedding model changes
  trigger a rebuild.
- `null` canonical values are acceptable and intentional. They are safer than
  forcing a weak mapping into downstream scoring.
