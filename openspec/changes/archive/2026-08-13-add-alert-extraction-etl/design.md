## Context

The `etl` project currently contains raw alert data and a client profile, but no executable data shaping pipeline. The first enrichment step needs to transform raw alerts into structured metadata that downstream processes can canonicalize, standardize, score, and consume through tooling under `ai-alert-scorer/`.

The raw alert input is a JSON array of objects containing `id`, `received_at`, `subject`, and `body`. The client profile provides useful domain context, but this change must not treat the profile as a closed allowlist because real alerts will contain new aliases, companies, markets, and themes.

The output of this step is intentionally a first-pass extraction result. It captures what the model observed and why, while leaving final canonical IDs, alias merging, ticker enrichment, taxonomy normalization, and cross-record entity resolution to a later process.

## Goals / Non-Goals

**Goals:**

- Read raw alerts from JSON and produce one enriched output object per alert.
- Preserve the source alert fields unchanged.
- Use LangChain with an OpenAI chat model backend for extraction.
- Use Pydantic models as the source of truth for structured output validation.
- Extract companies, sectors, geo markets, key markets, commodities, regulators, macro sensitivities, and themes.
- Define the semantic meaning and extraction boundary for every output field.
- Create one reusable extraction prompt section per AI-extracted field.
- Create a synthesis prompt that assembles the field prompt sections into the final model instruction.
- Keep extracted names lower case and include concise rationales grounded in the alert text.
- Make the ETL reproducible from a local command and testable without requiring live model calls in unit tests.

**Non-Goals:**

- Canonicalizing entity names across the dataset.
- Mapping aliases to stable internal IDs.
- Maintaining closed allowlists for extracted attributes.
- Enriching missing tickers from external data sources.
- Scoring alert relevance or materiality.
- Building the downstream `ai-alert-scorer` tool integration.

## Decisions

### Use a two-stage architecture with this change covering extraction only

This change introduces only the first stage:

```text
raw alerts + profile context
          |
          v
AI extraction ETL
          |
          v
first-pass enriched JSON
          |
          v
future canonicalization and standardization
```

Rationale: the extractor should optimize for recall and evidence capture. Canonicalization has a different job: deduping aliases, applying stable vocabularies, enriching tickers, and assigning internal IDs. Combining both jobs would make prompts harder to test and would hide uncertainty.

Alternative considered: force the extraction model to emit canonical values directly. This was rejected because the user expects many variations and a later process will standardize them.

### Use Pydantic schemas for the model contract

The ETL will define Pydantic models for input alerts, metadata items, company items, and enriched alerts. The LangChain/OpenAI call will be configured for structured output against those models, and the ETL will validate model responses before writing processed JSON.

Rationale: Pydantic gives a single contract for prompt guidance, runtime validation, and tests. It also limits malformed JSON failure modes.

Alternative considered: prompt the model for free-form JSON and parse it manually. This was rejected because parsing and validation errors would be less predictable.

### Keep company extraction company-only

The `companies` array will contain named business entities only. Countries, commodities, regulators, markets, sectors, themes, and macro concepts will be extracted into their dedicated arrays rather than being mixed into `companies`.

Rationale: downstream canonicalization can then use different matching strategies for company entities versus markets, regulators, or themes.

Alternative considered: keep a generic entity array with a `type` field. This was rejected based on the updated output contract.

### Treat ticker as optional first-pass evidence

Company records will include `name`, `ticker`, and `rationale`. `ticker` will be lower case when explicitly present or highly confident from the alert context, and null when unavailable.

Rationale: source alerts sometimes include tickers, but many company mentions do not. This extraction step should not invent missing securities metadata.

Alternative considered: require a non-empty ticker for every company. This was rejected because it would encourage hallucinated values or arbitrary placeholders.

### Use prompt guidance instead of closed allowlists

The prompt will include field-specific inclusion and exclusion guidance, plus client profile context as hints. It will not instruct the model to only choose values from the profile.

Rationale: the profile is useful for domain awareness but insufficient for future real-world alert variation.

Alternative considered: enforce controlled vocabularies for each attribute. This was rejected because canonicalization is explicitly deferred.

### Define output field semantics before prompt implementation

The ETL will treat the output fields as follows:

| Field | Meaning | Extraction boundary |
| --- | --- | --- |
| `id` | Source alert identifier. | Copied unchanged from input; never AI-generated. |
| `received_at` | Source alert receipt timestamp. | Copied unchanged from input; never AI-generated. |
| `subject` | Source alert subject or headline. | Copied unchanged from input; never AI-generated. |
| `body` | Source alert body text. | Copied unchanged from input; never AI-generated. |
| `companies` | Named business entities relevant to the alert, including focal companies, competitors, suppliers, customers, partners, acquirers, acquisition targets, or other operating businesses. | Excludes countries, regulators, markets, sectors, commodities, themes, and macro concepts. |
| `sectors` | Broad industries or business verticals affected by the alert. | Should be broader than a single company and distinct from customer/end markets when possible. |
| `geo_markets` | Countries or regions materially connected to operations, demand, supply chains, regulation, investment, or manufacturing in the alert. | Excludes company names and generic phrases with no geographic meaning. |
| `key_markets` | Product markets, end markets, customer markets, or demand pools affected by the alert. | More specific than sectors; examples include warehouse automation, automotive manufacturing, and e-commerce fulfillment. |
| `commodities` | Raw materials, traded goods, physical inputs, or components whose availability, pricing, or supply affects the alert. | Excludes broad sectors and abstract themes. |
| `regulators` | Regulatory bodies, laws, agencies, enforcement regimes, or formal review processes mentioned or clearly implicated. | Excludes general government references unless tied to regulatory action. |
| `macro_sensitivities` | Broad economic or geopolitical drivers that can affect valuation, demand, margins, financing, or supply chains. | Examples include interest rates, tariffs, reshoring, labor costs, geopolitical risk, and trade restrictions. |
| `themes` | Strategic or investment themes that summarize why the alert matters across companies or markets. | Should be thematic rather than a literal entity; examples include AI-driven automation, labor shortage, and supply chain resilience. |

Rationale: the extractor needs field-specific semantics to avoid mixing concepts across arrays. These definitions also make tests and future prompt revisions easier to reason about.

Alternative considered: leave field definitions only inside the Pydantic schema descriptions. This was rejected because the prompt, tests, and documentation all need the same semantic source.

### Build prompts as modular field guidance plus synthesis prompt

The ETL will define one prompt section for each AI-extracted field:

- `companies_prompt`
- `sectors_prompt`
- `geo_markets_prompt`
- `key_markets_prompt`
- `commodities_prompt`
- `regulators_prompt`
- `macro_sensitivities_prompt`
- `themes_prompt`

Each field prompt will include:

- The field's purpose.
- What to include.
- What to exclude.
- Evidence standard for inclusion.
- Name normalization expectations.
- Rationale expectations.
- Field-specific edge cases.

The synthesis prompt will be the only prompt sent to the model. It will assemble:

- Task objective.
- Source alert `subject` and `body`.
- Client profile context as hints, not allowlists.
- All field prompt sections.
- Global extraction rules such as no hallucinated facts, lower-case names, empty arrays when no evidence exists, and concise rationales.
- Pydantic structured output instructions supplied through LangChain/OpenAI.

Rationale: modular field prompts make each extraction boundary maintainable while still using a single structured model call per alert. The synthesis prompt prevents conflicting partial outputs from multiple model calls and keeps cost, latency, and validation simpler.

Alternative considered: call the model separately once per field and merge the results. This was rejected for the first implementation because it increases cost, latency, and reconciliation complexity without improving the output contract.

## Risks / Trade-offs

- Model output can vary between runs -> use low temperature, strict Pydantic validation, and unit tests around deterministic post-processing.
- The extractor may over-extract weakly implied concepts -> include field-specific prompt guidance requiring evidence from the subject or body.
- The extractor may miss implicit but relevant entities -> pass client profile context as hints and rationales to make omissions easier to inspect.
- Prompt sections may drift from Pydantic field descriptions -> keep field semantics in one module or shared constants and test that the synthesis prompt includes every field section.
- Ticker values may be incomplete -> allow null tickers and defer enrichment to canonicalization.
- Live model calls make tests slow and costly -> isolate the model client behind a small interface and use mocked structured responses in unit tests.
- Large future datasets may hit token or cost limits -> process alerts one at a time and make batching an implementation optimization, not a contract requirement.
