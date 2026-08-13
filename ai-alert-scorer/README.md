# ai-alert-scorer

Conversational PoC for ranking canonical media alerts by relevance to one
configured client.

The application combines a deterministic scoring backend with an OpenAI chat
model. The backend loads canonical JSON artifacts, resolves an absolute alert
date window, filters eligible alerts, assigns auditable 0-100 relevance scores,
and sends only the ranked result context to the model for explanation.

## What It Does

- Runs an interactive Rich terminal chat.
- Answers normal conversation without loading alert data.
- Detects alert, news, briefing, summary, and ranking requests.
- Supports one configured client per run.
- Resolves explicit and relative date ranges before loading alerts.
- Applies deterministic scoring in Python; the model does not create scores.
- Shows ranked alerts, scores, timestamps, and evidence in the terminal.
- Keeps alerts below the summary threshold as ranking evidence only.

## Documentation Map

| Page | Use it for |
| --- | --- |
| [scoring.md](scoring.md) | Details about how alert relevance scoring works, including weights, caps, evidence, recency, tie-breaking, and examples. |

## Requirements

- Python 3.11 or newer.
- An OpenAI API key available as `OPENAI_API_KEY`.
- `ALERT_RELEVANCE_MODEL` set to the model used for chat responses.
- Canonicalized alert and client-profile JSON artifacts.

The repository-level `.env.example` includes the supported environment
variables:

```dotenv
OPENAI_API_KEY=
ALERT_RELEVANCE_MODEL=
ALERT_RELEVANCE_TEMPERATURE=0
ALERT_RELEVANCE_REASONING_EFFORT=
ALERT_RELEVANCE_REASONING_SUMMARY=
```

`ALERT_RELEVANCE_TEMPERATURE`,
`ALERT_RELEVANCE_REASONING_EFFORT`, and
`ALERT_RELEVANCE_REASONING_SUMMARY` are optional.

## Install

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e "./ai-alert-scorer[test]"
```

On Windows, activate the environment with:

```powershell
.venv\Scripts\activate
```

## Configure

Set environment variables directly or create a local `.env` file from the
repository-level example:

```bash
cp .env.example .env
```

At minimum, fill in:

```dotenv
OPENAI_API_KEY=...
ALERT_RELEVANCE_MODEL=...
```

The production model is created through `langchain-openai` with the OpenAI
Responses API enabled.

## Run

After installation, start the chat with the console script:

```bash
alert-relevance-chat
```

You can also run the module directly:

```bash
python -m ai_alert_scorer.app.cli
```

By default, the app reads:

```text
etl/data/processed/canonicalized_alerts.json
etl/data/processed/canonicalized_client2_profile.json
```

Use explicit canonical data paths for another dataset or client:

```bash
alert-relevance-chat \
  --canonical-alerts-path etl/data/processed/canonicalized_alerts.json \
  --canonical-client-profile-path etl/data/processed/canonicalized_client_profile.json
```

Set the default result count with `--top-n`:

```bash
alert-relevance-chat --top-n 10
```

A user request such as `show the top 2 alerts` overrides that configured
default for the current turn.

Exit the interactive session with `exit`, `quit`, `q`, `:q`, `/exit`, EOF, or
Ctrl-C.

## Date Ranges

Every alert-ranking turn is resolved to an inclusive, timezone-aware date
range before alerts are loaded.

If the request does not include a date range, the app uses a rolling last
3-day default window and the assistant is instructed to say that default was
applied.

Supported request styles include:

| Request phrase | Applied range |
| --- | --- |
| `today` | The full calendar day at the active anchor. |
| `yesterday` | The prior full calendar day. |
| `last N days` | Calendar days through the active anchor day. |
| `past week` | Seven calendar days through the active anchor day. |
| `N days ago` | That historical full calendar day. |
| `from N days ago` / `since N days ago` | Rolling lookback from that timestamp to the active anchor. |
| One ISO date | That full UTC calendar day. |
| Two ISO dates | Full UTC day boundaries from start date through end date. |
| Two timezone-aware ISO timestamps | Exact inclusive timestamp range. |

Use `--as-of` to make relative phrases reproducible against snapshot data:

```bash
alert-relevance-chat --as-of 2026-08-11
alert-relevance-chat --as-of 2026-08-11T09:30:00-03:00
```

A date-only `--as-of` value anchors to noon UTC for that date. A datetime
`--as-of` value must include a timezone.

Example prompt using exact timestamps:

```text
What are the top alerts from 2026-08-11T00:00:00Z to 2026-08-11T23:59:59Z?
```

## Input Artifacts

The scorer expects canonicalized data. It does not extract or canonicalize raw
media content.

`canonicalized_alerts.json` must be a JSON array. Each alert can include:

```json
{
  "id": "alert-id",
  "received_at": "2026-08-11T09:00:00Z",
  "subject": "Alert subject",
  "body": "Alert body",
  "companies": [],
  "sectors": [],
  "geo_markets": [],
  "key_markets": [],
  "commodities": [],
  "regulators": [],
  "macro_sensitivities": [],
  "themes": []
}
```

`canonicalized_client*_profile.json` must be one JSON object. Important fields
include:

```json
{
  "client_name": "Client Name",
  "ticker": "TICKER",
  "sector": "canonical_sector_id",
  "focal_companies": [],
  "competitors": [],
  "suppliers": [],
  "customers": [],
  "geo_markets": [],
  "key_markets": [],
  "commodities": [],
  "regulators": [],
  "macro_sensitivities": [],
  "themes": []
}
```

Company and metadata items in alerts should include canonical IDs when
available. Tickers are preserved in input data, but ticker values are ignored
for scoring and evidence.

## Scoring Summary

Scoring is deterministic and auditable. Final scores use a 0-100 scale with
these capped groups:

| Group | Cap |
| --- | ---: |
| `relationship_proximity` | 45 |
| `operational_exposure` | 25 |
| `broad_context` | 10 |
| `signal_combination_bonus` | 10 |
| `recency` | 10 |

Relationship signals use only the highest matched value in the group:

| Signal | Weight |
| --- | ---: |
| Client focal company in `companies.canonical` | 45 |
| Client name in alert text without a canonical focal-company match | 34 |
| Known competitor | 28 |
| Known customer | 26 |
| Known supplier | 24 |

Operational and broad-context signals can add together up to their group caps:

| Signal | Weight |
| --- | ---: |
| Key market | 12 |
| Regulator | 10 |
| Commodity | 8 |
| Sector | 6 |
| Geographic market | 5 |
| Macro sensitivity | 5 |
| Strategic theme | 4 |

Combination bonuses reward meaningful intersections and are capped at 10 total
points. Recency is calculated relative to `--as-of` or the current UTC time,
not relative to the end of the requested alert filter window.

Each ranked alert includes:

- `criterion_scores`
- `matched_signals`
- `combination_bonuses`
- `matched_canonical_ids`
- top `evidence`

Alerts below `SUMMARY_MIN_SCORE` (`15.0`) remain in `ranked_alerts` for audit
and terminal display, but are excluded from `summary_alerts`; the model is
instructed not to summarize them as key alerts.

See [scoring.md](scoring.md) for the full scoring model, examples, tie-breaking
rules, and backend module responsibilities.

## Development

Run the focused test suite from `ai-alert-scorer/`:

```bash
python -m pytest
```

Run linting:

```bash
python -m ruff check .
```

Relevant modules:

| Module | Responsibility |
| --- | --- |
| `ai_alert_scorer.app.cli` | CLI argument parsing and command entrypoint. |
| `ai_alert_scorer.app.presentation` | Rich terminal rendering and chat loop. |
| `ai_alert_scorer.agent` | Chat-turn orchestration and model context construction. |
| `ai_alert_scorer.config` | Runtime paths, top-N, `--as-of`, and model env config. |
| `ai_alert_scorer.date_ranges` | Date parsing, default windows, and alert filtering. |
| `ai_alert_scorer.io` | JSON loading and Pydantic validation. |
| `ai_alert_scorer.schemas` | Canonical input and ranking output contracts. |
| `ai_alert_scorer.scoring` | Deterministic scoring matrix and ranking. |
| `ai_alert_scorer.tools` | LangChain structured tools for canonical data and ranking. |
