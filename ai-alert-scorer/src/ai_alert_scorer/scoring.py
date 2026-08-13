"""Deterministic matrix-based relevance scoring for canonical media alerts."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from ai_alert_scorer.date_ranges import (
    AlertDateRange,
    AlertDateRangeError,
    parse_absolute_timestamp,
)
from ai_alert_scorer.schemas import (
    CanonicalizedAlert,
    CanonicalizedClientProfile,
    CanonicalMetadataItem,
    CombinationBonus,
    CriterionScore,
    MatchedSignal,
    RankedAlertResult,
)

RELATIONSHIP_GROUP = "relationship_proximity"
OPERATIONAL_GROUP = "operational_exposure"
BROAD_CONTEXT_GROUP = "broad_context"
COMBINATION_GROUP = "signal_combination_bonus"
RECENCY_GROUP = "recency"
SUMMARY_MIN_SCORE = 15.0
RECENCY_LOOKBACK_DAYS = 5
RECENCY_WINDOW_SECONDS = RECENCY_LOOKBACK_DAYS * 24 * 60 * 60

GROUP_CAPS: dict[str, float] = {
    RELATIONSHIP_GROUP: 45.0,
    OPERATIONAL_GROUP: 25.0,
    BROAD_CONTEXT_GROUP: 10.0,
    COMBINATION_GROUP: 10.0,
    RECENCY_GROUP: 10.0,
}

SIGNAL_WEIGHTS: dict[str, float] = {
    "direct_client_canonical": 45.0,
    "client_name_text": 34.0,
    "competitor": 28.0,
    "customer": 26.0,
    "supplier": 24.0,
    "key_market": 12.0,
    "regulator": 10.0,
    "commodity": 8.0,
    "sector": 6.0,
    "geo_market": 5.0,
    "macro_sensitivity": 5.0,
    "strategic_theme": 4.0,
}

COMBINATION_WEIGHTS: dict[str, float] = {
    "direct_client_with_operational_or_relationship_signal": 10.0,
    "competitor_with_key_market": 8.0,
    "competitor_with_regulator": 7.0,
    "customer_with_key_market": 7.0,
    "supplier_with_commodity": 7.0,
    "supplier_with_regulator": 6.0,
    "commodity_with_macro_sensitivity": 5.0,
    "regulator_with_strategic_theme": 4.0,
    "broad_context_only_combination": 2.0,
}


@dataclass(frozen=True)
class _SignalDefinition:
    """Static scoring matrix row used for field-overlap signals."""

    name: str
    group: str
    weight: float
    label: str


def score_alert(
    alert: CanonicalizedAlert,
    client: CanonicalizedClientProfile,
    date_range: AlertDateRange,
    scored_at: datetime | None = None,
) -> RankedAlertResult:
    """Score one alert for one client with the explicit relevance matrix.

    Args:
        alert (CanonicalizedAlert): Candidate alert.
        client (CanonicalizedClientProfile): Client profile.
        date_range (AlertDateRange): Active alert date range.
        scored_at (datetime | None): Optional timezone-aware timestamp used as
            the recency anchor. Uses the current UTC time when omitted.

    Returns:
        RankedAlertResult: Unranked score result with auditable evidence.

    Raises:
        AlertDateRangeError: If ``alert.received_at`` or ``scored_at`` is
            invalid.
    """

    evaluation_time = _evaluation_time(scored_at)
    matched_signals = _matched_signals(alert, client)
    combination_bonuses = _combination_bonuses(matched_signals)
    criterion_scores = _criterion_scores(
        alert,
        evaluation_time,
        matched_signals,
        combination_bonuses,
    )
    final_score = round(
        min(sum(score.score_contribution for score in criterion_scores), 100.0),
        2,
    )

    return RankedAlertResult(
        rank=0,
        alert_id=alert.id,
        received_at=alert.received_at,
        subject=alert.subject,
        final_score=final_score,
        criterion_scores=criterion_scores,
        matched_signals=matched_signals,
        combination_bonuses=combination_bonuses,
        matched_canonical_ids=_matched_canonical_ids(matched_signals),
        evidence=_rank_evidence(criterion_scores, matched_signals, combination_bonuses),
    )


def rank_alerts_for_client(
    alerts: Sequence[CanonicalizedAlert],
    client: CanonicalizedClientProfile,
    date_range: AlertDateRange,
    top_n: int,
    scored_at: datetime | None = None,
) -> list[RankedAlertResult]:
    """Rank candidate alerts for one client profile.

    Args:
        alerts (Sequence[CanonicalizedAlert]): Candidate alerts to score.
        client (CanonicalizedClientProfile): Client profile.
        date_range (AlertDateRange): Active alert date range.
        top_n (int): Maximum number of results to return.
        scored_at (datetime | None): Optional timezone-aware timestamp used as
            the recency anchor. Uses the current UTC time when omitted.

    Returns:
        list[RankedAlertResult]: Top alerts ordered by descending score.

    Raises:
        AlertDateRangeError: If ``scored_at`` is invalid.
        ValueError: If ``top_n`` is not positive.
    """

    if top_n < 1:
        raise ValueError("top_n must be a positive integer")

    evaluation_time = _evaluation_time(scored_at)
    scored_alerts = [
        score_alert(alert, client, date_range, scored_at=evaluation_time)
        for alert in alerts
    ]
    scored_alerts.sort(
        key=lambda result: (
            result.final_score,
            _received_at_sort_key(result.received_at),
            result.alert_id,
        ),
        reverse=True,
    )

    ranked_results: list[RankedAlertResult] = []
    for rank, result in enumerate(scored_alerts[:top_n], start=1):
        ranked_results.append(result.model_copy(update={"rank": rank}))
    return ranked_results


def _matched_signals(
    alert: CanonicalizedAlert,
    client: CanonicalizedClientProfile,
) -> list[MatchedSignal]:
    signals: list[MatchedSignal] = []
    alert_company_ids = _alert_company_ids(alert)
    text = _alert_text(alert)

    focal_matches = alert_company_ids & set(client.focal_companies)
    if focal_matches:
        signals.append(
            _signal(
                name="direct_client_canonical",
                group=RELATIONSHIP_GROUP,
                ids=focal_matches,
                evidence_label="client focal company",
            )
        )
    elif _client_name_in_text(client, text):
        signals.append(
            MatchedSignal(
                name="client_name_text",
                group=RELATIONSHIP_GROUP,
                weight=SIGNAL_WEIGHTS["client_name_text"],
                evidence=[f"alert text mentions {client.client_name}"],
            )
        )

    relationship_fields = (
        ("competitor", client.competitors, "known competitor"),
        ("customer", client.customers, "known customer"),
        ("supplier", client.suppliers, "known supplier"),
    )
    for name, client_ids, evidence_label in relationship_fields:
        overlap = alert_company_ids & set(client_ids)
        if overlap:
            signals.append(
                _signal(
                    name=name,
                    group=RELATIONSHIP_GROUP,
                    ids=overlap,
                    evidence_label=evidence_label,
                )
            )

    signals.extend(_field_overlap_signals(alert, client))
    return signals


def _field_overlap_signals(
    alert: CanonicalizedAlert,
    client: CanonicalizedClientProfile,
) -> list[MatchedSignal]:
    sector_ids = {client.sector} if client.sector else set()
    fields = (
        (
            _SignalDefinition(
                name="key_market",
                group=OPERATIONAL_GROUP,
                weight=SIGNAL_WEIGHTS["key_market"],
                label="key market",
            ),
            _metadata_canonical_ids(alert.key_markets),
            set(client.key_markets),
        ),
        (
            _SignalDefinition(
                name="regulator",
                group=OPERATIONAL_GROUP,
                weight=SIGNAL_WEIGHTS["regulator"],
                label="regulator",
            ),
            _metadata_canonical_ids(alert.regulators),
            set(client.regulators),
        ),
        (
            _SignalDefinition(
                name="commodity",
                group=OPERATIONAL_GROUP,
                weight=SIGNAL_WEIGHTS["commodity"],
                label="commodity",
            ),
            _metadata_canonical_ids(alert.commodities),
            set(client.commodities),
        ),
        (
            _SignalDefinition(
                name="sector",
                group=BROAD_CONTEXT_GROUP,
                weight=SIGNAL_WEIGHTS["sector"],
                label="sector",
            ),
            _metadata_canonical_ids(alert.sectors),
            sector_ids,
        ),
        (
            _SignalDefinition(
                name="geo_market",
                group=BROAD_CONTEXT_GROUP,
                weight=SIGNAL_WEIGHTS["geo_market"],
                label="geo market",
            ),
            _metadata_canonical_ids(alert.geo_markets),
            set(client.geo_markets),
        ),
        (
            _SignalDefinition(
                name="macro_sensitivity",
                group=BROAD_CONTEXT_GROUP,
                weight=SIGNAL_WEIGHTS["macro_sensitivity"],
                label="macro sensitivity",
            ),
            _metadata_canonical_ids(alert.macro_sensitivities),
            set(client.macro_sensitivities),
        ),
        (
            _SignalDefinition(
                name="strategic_theme",
                group=BROAD_CONTEXT_GROUP,
                weight=SIGNAL_WEIGHTS["strategic_theme"],
                label="strategic theme",
            ),
            _metadata_canonical_ids(alert.themes),
            set(client.themes),
        ),
    )

    signals: list[MatchedSignal] = []
    for definition, alert_ids, client_ids in fields:
        overlap = alert_ids & client_ids
        if overlap:
            signals.append(
                MatchedSignal(
                    name=definition.name,
                    group=definition.group,
                    weight=definition.weight,
                    matched_canonical_ids=sorted(overlap),
                    evidence=[
                        f"{definition.label} overlap: {', '.join(sorted(overlap))}"
                    ],
                )
            )
    return signals


def _criterion_scores(
    alert: CanonicalizedAlert,
    scored_at: datetime,
    matched_signals: list[MatchedSignal],
    combination_bonuses: list[CombinationBonus],
) -> list[CriterionScore]:
    relationship = _relationship_contribution(matched_signals)
    operational = _capped_sum(matched_signals, OPERATIONAL_GROUP)
    broad_context = _capped_sum(matched_signals, BROAD_CONTEXT_GROUP)
    combination = min(
        sum(bonus.weight for bonus in combination_bonuses),
        GROUP_CAPS[COMBINATION_GROUP],
    )
    recency = _recency_contribution(alert, scored_at)

    return [
        _criterion_score(
            name=RELATIONSHIP_GROUP,
            contribution=relationship,
            evidence=_group_evidence(matched_signals, RELATIONSHIP_GROUP),
        ),
        _criterion_score(
            name=OPERATIONAL_GROUP,
            contribution=operational,
            evidence=_group_evidence(matched_signals, OPERATIONAL_GROUP),
        ),
        _criterion_score(
            name=BROAD_CONTEXT_GROUP,
            contribution=broad_context,
            evidence=_group_evidence(matched_signals, BROAD_CONTEXT_GROUP),
        ),
        _criterion_score(
            name=COMBINATION_GROUP,
            contribution=combination,
            evidence=_bonus_evidence(combination_bonuses),
        ),
        _criterion_score(
            name=RECENCY_GROUP,
            contribution=recency,
            evidence=[
                f"received at {alert.received_at}; scored as of {scored_at.isoformat()}"
            ],
        ),
    ]


def _relationship_contribution(matched_signals: list[MatchedSignal]) -> float:
    relationship_scores = [
        signal.weight
        for signal in matched_signals
        if signal.group == RELATIONSHIP_GROUP
    ]
    if not relationship_scores:
        return 0.0
    return min(max(relationship_scores), GROUP_CAPS[RELATIONSHIP_GROUP])


def _capped_sum(matched_signals: list[MatchedSignal], group: str) -> float:
    return min(
        sum(signal.weight for signal in matched_signals if signal.group == group),
        GROUP_CAPS[group],
    )


def _criterion_score(
    name: str,
    contribution: float,
    evidence: list[str],
) -> CriterionScore:
    weight = GROUP_CAPS[name]
    return CriterionScore(
        name=name,
        group=name,
        weight=weight,
        normalized_score=round(contribution / weight if weight else 0.0, 4),
        score_contribution=round(contribution, 2),
        evidence=evidence,
    )


def _combination_bonuses(
    matched_signals: list[MatchedSignal],
) -> list[CombinationBonus]:
    names = {signal.name for signal in matched_signals}
    bonuses: list[CombinationBonus] = []

    direct_names = {"direct_client_canonical", "client_name_text"}
    direct_context_names = {"key_market", "regulator", "customer", "supplier"}
    if names & direct_names and names & direct_context_names:
        bonuses.append(
            _bonus(
                "direct_client_with_operational_or_relationship_signal",
                names,
                direct_names | direct_context_names,
            )
        )
    if {"competitor", "key_market"} <= names:
        bonuses.append(
            _bonus(
                "competitor_with_key_market",
                names,
                {"competitor", "key_market"},
            )
        )
    if {"competitor", "regulator"} <= names:
        bonuses.append(
            _bonus(
                "competitor_with_regulator",
                names,
                {"competitor", "regulator"},
            )
        )
    if {"customer", "key_market"} <= names:
        bonuses.append(
            _bonus(
                "customer_with_key_market",
                names,
                {"customer", "key_market"},
            )
        )
    if {"supplier", "commodity"} <= names:
        bonuses.append(
            _bonus(
                "supplier_with_commodity",
                names,
                {"supplier", "commodity"},
            )
        )
    if {"supplier", "regulator"} <= names:
        bonuses.append(
            _bonus(
                "supplier_with_regulator",
                names,
                {"supplier", "regulator"},
            )
        )
    if {"commodity", "macro_sensitivity"} <= names:
        bonuses.append(
            _bonus(
                "commodity_with_macro_sensitivity",
                names,
                {"commodity", "macro_sensitivity"},
            )
        )
    if {"regulator", "strategic_theme"} <= names:
        bonuses.append(
            _bonus(
                "regulator_with_strategic_theme",
                names,
                {"regulator", "strategic_theme"},
            )
        )

    broad_only_names = {"sector", "geo_market", "strategic_theme"} & names
    has_only_broad_context = not names & {
        "direct_client_canonical",
        "client_name_text",
        "competitor",
        "customer",
        "supplier",
        "key_market",
        "regulator",
        "commodity",
        "macro_sensitivity",
    }
    if len(broad_only_names) >= 2 and has_only_broad_context:
        bonuses.append(
            _bonus(
                "broad_context_only_combination",
                names,
                {"sector", "geo_market", "strategic_theme"},
            )
        )
    return bonuses


def _bonus(
    name: str,
    matched_names: set[str],
    trigger_names: set[str],
) -> CombinationBonus:
    used_names = sorted(matched_names & trigger_names)
    return CombinationBonus(
        name=name,
        group=COMBINATION_GROUP,
        weight=COMBINATION_WEIGHTS[name],
        matched_signal_names=used_names,
        evidence=[f"combined signals: {', '.join(used_names)}"],
    )


def _recency_contribution(
    alert: CanonicalizedAlert,
    scored_at: datetime,
) -> float:
    received_at = parse_absolute_timestamp(alert.received_at, "received_at")
    age_seconds = max((scored_at - received_at).total_seconds(), 0.0)
    normalized = 1.0 - min(age_seconds / RECENCY_WINDOW_SECONDS, 1.0)
    return normalized * GROUP_CAPS[RECENCY_GROUP]


def _evaluation_time(scored_at: datetime | None) -> datetime:
    evaluation_time = scored_at or datetime.now(UTC)
    if evaluation_time.tzinfo is None or evaluation_time.utcoffset() is None:
        raise AlertDateRangeError("scored_at must include a timezone")
    return evaluation_time


def _signal(
    name: str,
    group: str,
    ids: set[str],
    evidence_label: str,
) -> MatchedSignal:
    return MatchedSignal(
        name=name,
        group=group,
        weight=SIGNAL_WEIGHTS[name],
        matched_canonical_ids=sorted(ids),
        evidence=[f"matches {evidence_label}: {', '.join(sorted(ids))}"],
    )


def _client_name_in_text(
    client: CanonicalizedClientProfile,
    text: str,
) -> bool:
    client_name = (client.client_name or "").strip().lower()
    return bool(client_name and client_name in text)


def _alert_company_ids(alert: CanonicalizedAlert) -> set[str]:
    return {company.canonical for company in alert.companies if company.canonical}


def _metadata_canonical_ids(items: Iterable[CanonicalMetadataItem]) -> set[str]:
    return {item.canonical for item in items if item.canonical}


def _matched_canonical_ids(matched_signals: list[MatchedSignal]) -> list[str]:
    ids = {
        matched_id
        for signal in matched_signals
        for matched_id in signal.matched_canonical_ids
    }
    return sorted(ids)


def _group_evidence(matched_signals: list[MatchedSignal], group: str) -> list[str]:
    return _dedupe(
        evidence
        for signal in matched_signals
        if signal.group == group
        for evidence in signal.evidence
    )


def _bonus_evidence(combination_bonuses: list[CombinationBonus]) -> list[str]:
    return _dedupe(
        evidence for bonus in combination_bonuses for evidence in bonus.evidence
    )


def _rank_evidence(
    criterion_scores: list[CriterionScore],
    matched_signals: list[MatchedSignal],
    combination_bonuses: list[CombinationBonus],
) -> list[str]:
    evidence: list[str] = []
    evidence.extend(_signal_rank_evidence(matched_signals))
    evidence.extend(_bonus_rank_evidence(combination_bonuses))
    evidence.extend(_recency_rank_evidence(criterion_scores))
    return _dedupe(evidence)


def _signal_rank_evidence(matched_signals: list[MatchedSignal]) -> list[str]:
    return [
        _scored_evidence(
            label=f"{signal.group}.{signal.name}",
            score=signal.weight,
            evidence=item,
        )
        for signal in matched_signals
        for item in signal.evidence
    ]


def _bonus_rank_evidence(combination_bonuses: list[CombinationBonus]) -> list[str]:
    return [
        _scored_evidence(
            label=bonus.name,
            score=bonus.weight,
            evidence=item,
        )
        for bonus in combination_bonuses
        for item in bonus.evidence
    ]


def _recency_rank_evidence(criterion_scores: list[CriterionScore]) -> list[str]:
    return [
        _scored_evidence(
            label=score.name,
            score=score.score_contribution,
            evidence=item,
        )
        for score in criterion_scores
        if score.name == RECENCY_GROUP
        for item in score.evidence
    ]


def _scored_evidence(label: str, score: float, evidence: str) -> str:
    return f"{label} +{score:.2f} pts: {evidence}"


def _alert_text(alert: CanonicalizedAlert) -> str:
    return f"{alert.subject} {alert.body}".lower()


def _received_at_sort_key(value: str) -> datetime:
    return parse_absolute_timestamp(value, "received_at")


def _dedupe(items: Iterable[str]) -> list[str]:
    unique_items: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        unique_items.append(item)
    return unique_items


__all__ = [
    "BROAD_CONTEXT_GROUP",
    "COMBINATION_GROUP",
    "COMBINATION_WEIGHTS",
    "GROUP_CAPS",
    "OPERATIONAL_GROUP",
    "RECENCY_GROUP",
    "RELATIONSHIP_GROUP",
    "RECENCY_LOOKBACK_DAYS",
    "SIGNAL_WEIGHTS",
    "SUMMARY_MIN_SCORE",
    "rank_alerts_for_client",
    "score_alert",
]
