# Alert Relevance Scoring

This document explains how `ai-alert-scorer` calculates alert relevance scores,
why the scoring model is structured this way, and which backend modules are
responsible for each step.

The short version: scoring is deterministic. The model does not invent numeric
scores. The backend compares canonical alert metadata against one canonical
client profile, applies a weighted relevance matrix, and returns auditable
ranked results.

## Goals

The scoring system is designed to rank media alerts by client relevance, not by
generic news importance. A recent article about the market is not automatically
important to a specific client. Conversely, an older alert can remain relevant
when it directly touches the client, a competitor, a customer, a supplier, a key
market, a regulator, or another client-specific exposure.

The main goals are:

- Determinism: the same canonical inputs produce the same scores.
- Auditability: every score includes matched signals, group-level
  contributions, combination bonuses, canonical IDs, and concise evidence.
- Business relevance: direct client and business-relationship signals matter
  more than broad context or recency alone.
- Bounded scoring: each scoring group has a cap so one signal family cannot
  dominate the entire result.
- Tunability: engineers can adjust the matrix in `scoring.py` without changing
  the aggregation algorithm.

## Inputs

The scorer expects canonicalized data. It does not perform extraction or
canonicalization itself.

### Client Profile

`CanonicalizedClientProfile` represents one client profile shaped for scoring.
Important fields include:

- `client_name`: raw profile name, used only for fallback text matching.
- `ticker`: raw ticker, preserved but not used for scoring.
- `focal_companies`: canonical company IDs for the client itself.
- `competitors`, `customers`, `suppliers`: canonical company IDs for known
  business relationships.
- `key_markets`, `regulators`, `commodities`, `macro_sensitivities`, `themes`:
  canonical IDs for operational and strategic exposure.
- `sector`, `geo_markets`: canonical IDs for broad context.

### Alert

`CanonicalizedAlert` represents one canonical media alert. Important fields
include:

- `id`, `received_at`, `subject`, `body`: source alert identity and text.
- `companies`: canonicalized company mentions.
- `key_markets`, `regulators`, `commodities`, `sectors`, `geo_markets`,
  `macro_sensitivities`, `themes`: canonicalized metadata extracted from the
  alert.

Ticker values may appear on `CanonicalCompanyItem`, but ticker values do not
contribute to relevance score or evidence. This is intentional because ticker
mentions can be noisy, ambiguous, and detached from business relevance.

## Scoring Theory

The scoring model treats relevance as a weighted intersection between an alert
and a client profile.

The score answers this question:

> How strongly does this alert connect to this client's known business
> identity, relationships, exposures, and context inside the requested time
> window?

The model separates signals into five groups:

1. Relationship proximity: direct or relationship-based company relevance.
2. Operational exposure: concrete business exposures like markets, regulators,
   and commodities.
3. Broad context: softer contextual overlap like sector, geography, and themes.
4. Signal combination bonus: extra credit for meaningful intersections.
5. Recency: bounded freshness relative to the scoring anchor.

This structure is deliberate. Relationship proximity is the strongest group
because direct company relevance is usually more actionable than broad context.
Operational exposure is second because a key market or regulator can materially
affect a client even when the client is not directly named. Broad context is
bounded to stay useful but low-impact. Combination bonuses reward alerts that
contain multiple independent reasons to matter. Recency breaks ties and helps
surface fresh alerts, but it cannot make a generic alert outrank strongly
relevant business signals by itself.

## Final Score Formula

Each alert receives a final score on a 0-100 scale:

```text
final_score = min(
    relationship_proximity
    + operational_exposure
    + broad_context
    + signal_combination_bonus
    + recency,
    100
)
```

Each group contribution is also represented as a normalized score:

```text
normalized_score = group_contribution / group_cap
```

For example, a `relationship_proximity` contribution of `28` has a normalized
score of `28 / 45 = 0.6222`.

## Groups and Weights

### Group Caps

| Group | Cap | Rationale |
| --- | ---: | --- |
| `relationship_proximity` | 45 | Direct and relationship-based company relevance is the strongest signal. |
| `operational_exposure` | 25 | Concrete business exposures can be highly relevant even without a direct client mention. |
| `broad_context` | 10 | Broad context is useful but should not dominate ranking. |
| `signal_combination_bonus` | 10 | Meaningful combinations should lift alerts, but only within a bounded range. |
| `recency` | 10 | Freshness matters, but not more than business relevance. |

### Relationship Proximity Signals

Only the highest matched relationship signal contributes to this group. This
prevents relationship metadata from stacking into an oversized relationship
score.

| Signal | Weight | Meaning |
| --- | ---: | --- |
| `direct_client_canonical` | 45 | The alert's canonical company IDs overlap with `client.focal_companies`. |
| `client_name_text` | 34 | The alert text mentions `client.client_name`, but no canonical focal-company match exists. |
| `competitor` | 28 | The alert mentions a known competitor. |
| `customer` | 26 | The alert mentions a known customer. |
| `supplier` | 24 | The alert mentions a known supplier. |

The canonical direct-client match is stronger than raw text matching because it
uses the canonical company identity rather than substring matching. The text
fallback is still useful when extraction misses a canonical company but the
client name is present in the alert subject or body.

### Operational Exposure Signals

Operational exposure signals can add together, capped at `25`.

| Signal | Weight | Meaning |
| --- | ---: | --- |
| `key_market` | 12 | Alert key markets overlap with the client's key markets. |
| `regulator` | 10 | Alert regulators overlap with the client's regulators. |
| `commodity` | 8 | Alert commodities overlap with the client's commodities. |

These signals represent concrete areas where an alert may affect the client
through operations, regulation, supply chain, market demand, or input costs.

### Broad Context Signals

Broad context signals can add together, capped at `10`.

| Signal | Weight | Meaning |
| --- | ---: | --- |
| `sector` | 6 | Alert sectors overlap with the client's sector. |
| `geo_market` | 5 | Alert geographic markets overlap with the client's geographic markets. |
| `macro_sensitivity` | 5 | Alert macro sensitivities overlap with the client's macro sensitivities. |
| `strategic_theme` | 4 | Alert themes overlap with the client's strategic themes. |

Broad context helps when alerts are not directly about the client or a specific
business relationship. The cap keeps this group from overstating generic sector
or geography matches.

### Combination Bonuses

Combination bonuses reward alerts that contain multiple independent reasons to
matter. Bonuses can add together, capped at `10`.

| Combination | Bonus | Trigger |
| --- | ---: | --- |
| `direct_client_with_operational_or_relationship_signal` | 10 | Direct client signal plus `key_market`, `regulator`, `customer`, or `supplier`. |
| `competitor_with_key_market` | 8 | `competitor` plus `key_market`. |
| `competitor_with_regulator` | 7 | `competitor` plus `regulator`. |
| `customer_with_key_market` | 7 | `customer` plus `key_market`. |
| `supplier_with_commodity` | 7 | `supplier` plus `commodity`. |
| `supplier_with_regulator` | 6 | `supplier` plus `regulator`. |
| `commodity_with_macro_sensitivity` | 5 | `commodity` plus `macro_sensitivity`. |
| `regulator_with_strategic_theme` | 4 | `regulator` plus `strategic_theme`. |
| `broad_context_only_combination` | 2 | At least two of `sector`, `geo_market`, and `strategic_theme`, with no stronger signal. |

The combination cap matters. If several combinations trigger, the scorer sums
their bonus weights and then limits the group to `10`.

### Recency

Recency contributes up to `10` points based on how old `alert.received_at` is
relative to the scoring anchor. The scoring anchor represents the app's notion
of "today" or "now" for the current ranking run.

The chat app chooses the scoring anchor in this order:

1. If the CLI was started with `--as-of`, use that timezone-aware timestamp.
2. Otherwise, use the session clock at ranking time, in UTC.

The requested date range only decides which alerts are eligible to be scored.
It does not reset the recency baseline. This distinction is important for
historical queries: an alert from June should not look fresh just because the
user asked for a May-June date window in August.

```text
window_seconds = 5 days
recency_cap = 10
raw_age_seconds = scored_at - alert.received_at
age_seconds = max(raw_age_seconds, 0)
normalized = 1 - min(age_seconds / window_seconds, 1)
recency = normalized * recency_cap
```

The resulting behavior is:

| Alert age at scoring time | Recency contribution |
| --- | ---: |
| `0 days` | `10.00` |
| `1 day` | `8.00` |
| `2 days` | `6.00` |
| `3 days` | `4.00` |
| `4 days` | `2.00` |
| `5+ days` | `0.00` |

If an alert timestamp is after the scoring anchor, age is clamped to `0`, so
recency is capped at `10`. In normal application flow this should be rare
because alerts are first filtered into the requested date range.

Each recency evidence entry includes both timestamps:

```text
recency +5.75 pts: received at 2026-08-11T09:00:00Z; scored as of 2026-08-13T12:00:00+00:00
```

#### Historical Range Example

Assume the user asks for:

```text
top news from 2026-05-01 to 2026-06-30
```

And the scoring anchor is:

```text
2026-08-13T12:00:00Z
```

A June 27 alert is eligible for the May-June query because it falls inside the
requested date range. Its recency is still calculated against August 13, not
June 30:

```text
received_at = 2026-06-27T09:00:00Z
scored_at = 2026-08-13T12:00:00Z
age > 5 days
recency = 0.00
```

An August 11 alert scored with the same August 13 anchor is much fresher:

```text
received_at = 2026-08-11T09:00:00Z
scored_at = 2026-08-13T12:00:00Z
age = 2 days, 3 hours
recency = 5.75
```

So August receives a higher recency contribution than June when both are
compared to the same scoring anchor.

## Backend Responsibilities

The scoring backend is intentionally small. These are the main modules and
classes involved.

### `ai_alert_scorer.agent`

`AlertRelevanceSession` orchestrates a chat turn. It resolves the requested date
range, loads the canonical client profile, loads alerts inside that range, calls
the deterministic ranking function, and then sends only the ranked results to
the response model for explanation.

This module owns orchestration. It does not calculate the numeric score.

### `ai_alert_scorer.date_ranges`

`AlertDateRange` stores an inclusive, timezone-aware date window.

`resolve_request_date_range` parses explicit ISO timestamps, explicit dates,
relative phrases like `today`, `yesterday`, `last N days`, and `past week`, or
falls back to the default lookback window.

`filter_alerts_by_date_range` filters alerts before ranking.

`parse_absolute_timestamp` validates timezone-aware timestamps used by filtering
and recency scoring.

### `ai_alert_scorer.io`

`CanonicalDataLoader` reads canonical JSON artifacts from disk and validates
them into Pydantic schemas. It is responsible for getting well-shaped
`CanonicalizedAlert` and `CanonicalizedClientProfile` objects into the pipeline.

This module does not score alerts.

### `ai_alert_scorer.schemas`

The scoring-related schemas are:

- `CanonicalizedAlert`: canonical alert input.
- `CanonicalizedClientProfile`: canonical client profile input.
- `CanonicalCompanyItem`: canonical company metadata attached to an alert.
- `CanonicalMetadataItem`: canonical non-company metadata attached to an alert.
- `MatchedSignal`: one matched matrix signal, including weight and evidence.
- `CombinationBonus`: one triggered bonus, including weight and evidence.
- `CriterionScore`: one group-level score contribution.
- `RankedAlertResult`: final structured score output for one alert.
- `RankingResult`: container returned by ranking tools.

These classes define the data contract between loading, scoring, rendering, and
model explanation.

### `ai_alert_scorer.scoring`

This module owns all numeric scoring logic.

Important constants:

- `GROUP_CAPS`: maximum contribution per scoring group.
- `SIGNAL_WEIGHTS`: base weights for individual signals.
- `COMBINATION_WEIGHTS`: weights for deterministic signal combinations.

Important public functions:

- `score_alert(alert, client, date_range, scored_at=None)`: scores one alert
  and returns a `RankedAlertResult` with `rank=0`. `scored_at` is the optional
  timezone-aware recency anchor.
- `rank_alerts_for_client(alerts, client, date_range, top_n, scored_at=None)`:
  scores all candidate alerts, sorts them, truncates to `top_n`, and assigns
  one-based ranks. The same `scored_at` anchor is applied to every alert in the
  ranking run.

Important internal helpers:

- `_matched_signals`: finds all alert/profile intersections.
- `_field_overlap_signals`: compares canonical metadata fields such as markets,
  regulators, commodities, sector, geography, macro sensitivities, and themes.
- `_relationship_contribution`: takes the highest relationship signal, capped
  at the relationship group cap.
- `_capped_sum`: sums all matched signals for additive groups and applies the
  group cap.
- `_combination_bonuses`: detects deterministic signal combinations.
- `_recency_contribution`: calculates bounded recency points.
- `_top_evidence`: builds concise evidence used by downstream explanations.

## End-to-End Flow

The normal application flow is:

```text
user question
  -> resolve date range
  -> resolve scoring anchor from --as-of or current UTC time
  -> load canonical client profile
  -> load and filter canonical alerts by received_at
  -> score each alert with score_alert using the scoring anchor
  -> sort and truncate with rank_alerts_for_client
  -> pass ranked results to the model for explanation
```

The model receives structured ranked results and is instructed not to invent
scores, ranks, alert IDs, or evidence.

## Ranking and Tie-Breaking

`rank_alerts_for_client` sorts scored alerts by:

1. `final_score`, descending.
2. `received_at`, descending.
3. `alert_id`, descending.

Then it returns only the requested `top_n` results and assigns ranks starting at
`1`.

`top_n` must be a positive integer.

## Practical Examples

The following examples use fictitious canonical data.

### Fictitious Client Profile

```json
{
  "client_name": "Solstice Robotics",
  "ticker": "SLRB",
  "sector": "industrial_robotics",
  "focal_companies": ["solstice_robotics"],
  "competitors": ["kestrel_automation"],
  "suppliers": ["quanta_sensing"],
  "customers": ["northline_logistics"],
  "geo_markets": ["united_states"],
  "key_markets": ["warehouse_automation"],
  "commodities": ["semiconductor_chips"],
  "regulators": ["cfius"],
  "macro_sensitivities": ["interest_rates"],
  "themes": ["ai_driven_automation"]
}
```

Assume the active date range is:

```text
2026-08-10T00:00:00Z to 2026-08-11T23:59:59Z
```

Assume the scoring anchor is:

```text
2026-08-12T00:00:00Z
```

### Example 1: Direct Client Match

Alert:

```json
{
  "id": "direct-client",
  "received_at": "2026-08-10T00:00:00Z",
  "subject": "Solstice Robotics announces expansion",
  "companies": [
    {"name": "Solstice Robotics", "canonical": "solstice_robotics"}
  ]
}
```

Matched signals:

| Signal | Group | Points |
| --- | --- | ---: |
| `direct_client_canonical` | `relationship_proximity` | 45 |

Score:

```text
relationship_proximity = 45
operational_exposure = 0
broad_context = 0
signal_combination_bonus = 0
recency = 6

final_score = 51.00
```

This alert is directly about the client. It scores strongly even though it is
less fresh than alerts received closer to the scoring anchor.

### Example 2: Competitor Plus Key Market

Alert:

```json
{
  "id": "competitor-market",
  "received_at": "2026-08-11T17:00:00Z",
  "subject": "Kestrel Automation expands warehouse automation platform",
  "companies": [
    {"name": "Kestrel Automation", "canonical": "kestrel_automation"}
  ],
  "key_markets": [
    {"name": "warehouse automation", "canonical": "warehouse_automation"}
  ]
}
```

Matched signals:

| Signal | Group | Points |
| --- | --- | ---: |
| `competitor` | `relationship_proximity` | 28 |
| `key_market` | `operational_exposure` | 12 |
| `competitor_with_key_market` | `signal_combination_bonus` | 8 |

Score:

```text
relationship_proximity = 28
operational_exposure = 12
broad_context = 0
signal_combination_bonus = 8
recency = 9.42

final_score = 57.42
```

This alert outranks the direct-client example above because it combines several
independent relevance signals and is much newer relative to the scoring anchor.
That outcome is expected: not every direct mention is automatically the top
alert if another alert has richer business relevance and meaningful recency.

### Example 3: Very Recent Generic Alert

Alert:

```json
{
  "id": "recent-generic",
  "received_at": "2026-08-11T23:00:00Z",
  "subject": "General market update",
  "companies": []
}
```

Matched signals:

```text
none
```

Score:

```text
relationship_proximity = 0
operational_exposure = 0
broad_context = 0
signal_combination_bonus = 0
recency = 9.92

final_score = 9.92
```

This alert is fresh but generic. Recency alone cannot make it highly relevant to
the client.

### Example 4: Broad Context Only

Alert:

```json
{
  "id": "broad-context",
  "received_at": "2026-08-10T00:00:00Z",
  "subject": "Industrial robotics adoption grows in the United States",
  "sectors": [
    {"name": "industrial robotics", "canonical": "industrial_robotics"}
  ],
  "geo_markets": [
    {"name": "United States", "canonical": "united_states"}
  ],
  "themes": [
    {"name": "AI-driven automation", "canonical": "ai_driven_automation"}
  ]
}
```

Matched signals:

| Signal | Group | Raw Points |
| --- | --- | ---: |
| `sector` | `broad_context` | 6 |
| `geo_market` | `broad_context` | 5 |
| `strategic_theme` | `broad_context` | 4 |
| `broad_context_only_combination` | `signal_combination_bonus` | 2 |

Score:

```text
broad_context raw sum = 6 + 5 + 4 = 15
broad_context cap = 10

relationship_proximity = 0
operational_exposure = 0
broad_context = 10
signal_combination_bonus = 2
recency = 6

final_score = 18.00
```

This example shows why broad context is capped. The alert overlaps with the
client's sector, geography, and strategic theme, but it does not mention the
client, a relationship, or a concrete operational exposure.

### Example 5: Direct Client Plus Regulator

Alert:

```json
{
  "id": "direct-regulatory",
  "received_at": "2026-08-11T18:00:00Z",
  "subject": "CFIUS reviews Solstice Robotics transaction",
  "companies": [
    {"name": "Solstice Robotics", "canonical": "solstice_robotics"}
  ],
  "regulators": [
    {"name": "CFIUS", "canonical": "cfius"}
  ]
}
```

Matched signals:

| Signal | Group | Points |
| --- | --- | ---: |
| `direct_client_canonical` | `relationship_proximity` | 45 |
| `regulator` | `operational_exposure` | 10 |
| `direct_client_with_operational_or_relationship_signal` | `signal_combination_bonus` | 10 |

Approximate score:

```text
relationship_proximity = 45
operational_exposure = 10
broad_context = 0
signal_combination_bonus = 10
recency ~= 9.5

final_score ~= 74.5
```

This is the kind of alert the matrix is designed to surface: it directly names
the client and also intersects with a known regulatory exposure.

## How to Tune the Matrix

To adjust scoring behavior, edit the constants in `src/ai_alert_scorer/scoring.py`:

- `GROUP_CAPS` changes each group's maximum influence.
- `SIGNAL_WEIGHTS` changes individual signal strength.
- `COMBINATION_WEIGHTS` changes bonus strength for multi-signal intersections.

When tuning, preserve these invariants unless the product behavior explicitly
changes:

- Keep scores deterministic and model-independent.
- Keep ticker values out of score and evidence.
- Keep broad context bounded below direct and operational business relevance.
- Keep recency bounded so generic freshness does not dominate relevance.
- Update `tests/test_scoring.py` when expected ranking behavior changes.
