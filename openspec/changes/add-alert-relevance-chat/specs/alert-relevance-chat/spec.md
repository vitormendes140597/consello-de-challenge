## ADDED Requirements

### Requirement: Run Conversational Alert Relevance CLI
The system SHALL provide a terminal chat interface where users can enter alert
relevance questions and receive assistant answers in the same session.

The CLI SHALL load runtime configuration for canonical alert input path,
canonical client profile input path, model settings, top-N result count, and
the optional `--as-of` anchor.

#### Scenario: User starts chat session
- **WHEN** the user starts the alert relevance chat CLI with valid
  configuration
- **THEN** the system opens an interactive terminal session ready to accept user
  prompts

#### Scenario: User exits chat session
- **WHEN** the user enters a supported exit command
- **THEN** the system ends the chat session without invoking the model again

### Requirement: Maintain Conversation With OpenAI Responses API
The system SHALL use LangChain `ChatOpenAI` configured for the OpenAI Responses
API to generate assistant responses and continue the conversation across turns.

The system SHALL preserve enough response state within the running CLI session
for follow-up questions to refer to prior turns.

#### Scenario: Follow-up question uses conversation state
- **WHEN** the user asks an alert relevance question and then asks a follow-up
  question in the same CLI session
- **THEN** the model invocation continues the existing conversation rather than
  treating the follow-up as an unrelated first turn

### Requirement: Expose Canonical Data Access As Model Tools
The system SHALL expose model tools for reading the canonicalized client profile
and canonicalized alerts from configured JSON files.

The canonical client tool SHALL return one validated canonicalized client
profile. The canonical alerts tool SHALL return validated canonicalized alerts,
filtered by a resolved time window when one is supplied.

#### Scenario: Model reads canonical client profile
- **WHEN** the assistant needs client context to answer a relevance question
- **THEN** it can call a model tool that returns the configured canonicalized
  client profile

#### Scenario: Model reads canonical alerts for a time window
- **WHEN** the assistant needs alerts for a resolved time window
- **THEN** it can call a model tool that returns only alerts whose
  `received_at` timestamps fall within that window

#### Scenario: Invalid canonical data is rejected
- **WHEN** a configured canonical JSON file is missing, malformed, or fails
  schema validation
- **THEN** the corresponding tool returns an actionable error instead of
  silently producing partial relevance results

### Requirement: Resolve Time-Aware Questions
The system SHALL resolve supported relative time phrases in user questions into
explicit time windows before filtering alerts.

The system SHALL support at least `today`, `yesterday`, `last N days`, and
`past week`. The system SHALL treat `today` as the full local calendar day
containing the active `as_of` timestamp.

#### Scenario: Today resolves from runtime clock
- **WHEN** the user asks for alerts "today" and the CLI was started without
  `--as-of`
- **THEN** the system resolves the alert window to the current local calendar
  day at runtime

#### Scenario: Today resolves from as-of date
- **WHEN** the user asks for alerts "today" and the CLI was started with
  `--as-of 2026-08-11`
- **THEN** the system resolves the alert window to the full local calendar day
  of August 11, 2026

#### Scenario: Last N days resolves from as-of date
- **WHEN** the user asks for alerts from the "last 3 days" and the active
  `as_of` date is August 11, 2026
- **THEN** the system resolves the alert window relative to August 11, 2026

#### Scenario: Unsupported time phrase asks for clarification
- **WHEN** the user asks a relevance question with an unsupported or ambiguous
  time phrase
- **THEN** the assistant asks for clarification before ranking alerts

### Requirement: Support CLI As-Of Anchor
The CLI SHALL provide an `--as-of` option that accepts an ISO date or ISO
datetime and anchors all relative time-window resolution for the chat session.

Date-only `--as-of` values SHALL be interpreted as the local calendar day for
that date. Invalid `--as-of` values SHALL fail before the chat session starts.

#### Scenario: Valid as-of date is accepted
- **WHEN** the user starts the CLI with `--as-of 2026-08-11`
- **THEN** the system starts the chat session with August 11, 2026 as the
  active relative-time anchor

#### Scenario: Valid as-of datetime is accepted
- **WHEN** the user starts the CLI with an ISO datetime `--as-of` value
- **THEN** the system starts the chat session with that datetime as the active
  relative-time anchor

#### Scenario: Invalid as-of value fails fast
- **WHEN** the user starts the CLI with an invalid `--as-of` value
- **THEN** the system reports the invalid value and exits before invoking the
  model

### Requirement: Restrict Ranking To One Client
The system SHALL answer relevant-news ranking questions for one client at a
time.

If a user asks for multiple clients in one relevance question, the assistant
SHALL ask the user to choose one client before reading alerts or ranking
results.

#### Scenario: Single configured client is used
- **WHEN** the user asks for relevant alerts for the configured client
- **THEN** the ranking tool scores alerts against only that client's canonical
  profile

#### Scenario: Multiple clients are requested
- **WHEN** the user asks one relevance question for multiple clients
- **THEN** the assistant asks the user to pick one client before ranking alerts

### Requirement: Rank Alerts With Deterministic Weighted Scoring
The system SHALL expose a model tool that ranks canonicalized alerts for one
canonicalized client profile using a deterministic weighted scoring function.

The scoring function SHALL compute a normalized final score from enabled
criteria. Each criterion SHALL provide a name, weight, normalized score, and
evidence. Adding, removing, or disabling a criterion SHALL NOT require changes
to the score aggregation algorithm.

#### Scenario: Ranking returns top N scored alerts
- **WHEN** the model calls the ranking tool with candidate alerts, a client
  profile, and `top_n` set to 5
- **THEN** the tool returns at most 5 alerts ordered by descending final score

#### Scenario: Score aggregation normalizes enabled criteria
- **WHEN** criteria are added, removed, or disabled
- **THEN** the scoring function computes final scores from the enabled
  criteria without changing the aggregation algorithm

#### Scenario: Ranking includes criterion evidence
- **WHEN** the ranking tool returns a scored alert
- **THEN** the result includes criterion-level scores and evidence supporting
  the final score

### Requirement: Weight Business Proximity Highest
The scoring configuration SHALL give the largest group cap to relationship
proximity signals for direct client matches, competitors, customers, and
suppliers.

The scoring configuration SHALL include a bounded recency criterion that scores
alerts relative to the active `as_of` timestamp. The resolved time window SHALL
filter eligible alerts, but it SHALL NOT define the recency baseline.

#### Scenario: Relationship proximity has highest cap
- **WHEN** the scoring configuration is loaded
- **THEN** the relationship proximity group has a cap greater than every other
  scoring group

#### Scenario: Newer alert scores higher for recency
- **WHEN** two candidate alerts fall within the same resolved time window and
  one alert was received more recently than the other
- **THEN** the newer alert receives a higher recency criterion score

#### Scenario: Business proximity can outweigh recency
- **WHEN** an older alert directly matches the client's canonical focal company
  and a newer alert has no client relationship or profile intersections
- **THEN** the older direct-client alert ranks above the newer generic alert

### Requirement: Score Client Connectedness
The scoring function SHALL measure how connected each alert is to the client
using direct client identity matches and canonical intersections with the client
profile.

Client connectedness SHALL include direct client company matches, client-name
text mentions, relationship-company overlap, and intersections with supported
canonical fields such as sectors, geographic markets, key markets, commodities,
regulators, macro sensitivities, and themes.

Ticker values SHALL NOT contribute to relevance scores or scoring evidence.

#### Scenario: Direct client mention increases relevance
- **WHEN** an alert mentions the client's canonical focal company
- **THEN** the direct client match criterion contributes positive evidence to
  the alert score

#### Scenario: Ticker-only mention is ignored
- **WHEN** an alert contains only the client's ticker in metadata or text
- **THEN** ticker evidence does not contribute positive score or scoring
  evidence

#### Scenario: Profile intersections increase relevance
- **WHEN** an alert contains canonical metadata values that intersect with the
  client's canonical profile fields
- **THEN** the canonical overlap criteria contribute positive evidence to the
  alert score

#### Scenario: Meaningful signal combinations increase relevance
- **WHEN** an alert combines a relationship signal with a relevant operational
  exposure, such as competitor plus key market or supplier plus commodity
- **THEN** the scoring function applies a bounded deterministic combination
  bonus with evidence

#### Scenario: Unconnected alert receives low connectedness
- **WHEN** an alert has no direct client match, no relationship-company overlap,
  and no canonical profile intersections
- **THEN** client connectedness criteria contribute no positive evidence to the
  alert score

### Requirement: Explain Why Each Ranked Alert Matters
The assistant SHALL answer ranking questions by explaining why each returned
alert matters to the client using the structured ranking result.

The explanation SHALL include the alert subject, received date, final score or
rank, and the most important relevance evidence. The assistant SHALL not invent
score evidence absent from the ranking tool result.

#### Scenario: Top 5 question receives ranked explanation
- **WHEN** the user asks "What are the top 5 most relevant media alerts for
  Solstice Robotics today, and why does each one matter to the client?"
- **THEN** the assistant responds with up to 5 ranked alerts and explains why
  each matters to Solstice Robotics

#### Scenario: No alerts in requested window
- **WHEN** no canonical alerts fall within the resolved time window
- **THEN** the assistant clearly states that no alerts were found for that
  window and does not fabricate ranked results

### Requirement: Render Chat With Rich
The CLI SHALL render user prompts, assistant messages, tool status, ranked
tables, and errors with Rich.

#### Scenario: Ranked results are printed as a Rich table
- **WHEN** the assistant receives ranked alert results from the ranking tool
- **THEN** the CLI prints the ranked alerts in a Rich-rendered table or panel

#### Scenario: Tool errors are printed clearly
- **WHEN** a tool returns an actionable error
- **THEN** the CLI prints the error using Rich formatting that distinguishes it
  from normal assistant output
