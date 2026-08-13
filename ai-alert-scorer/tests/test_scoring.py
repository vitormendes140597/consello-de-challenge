"""Tests for deterministic matrix-based alert relevance scoring."""

from collections.abc import Sequence
from datetime import UTC, datetime

import pytest

from ai_alert_scorer.date_ranges import AlertDateRange, build_alert_date_range
from ai_alert_scorer.schemas import (
    CanonicalCompanyItem,
    CanonicalizedAlert,
    CanonicalizedClientProfile,
    CanonicalMetadataItem,
    CriterionScore,
    RankedAlertResult,
)
from ai_alert_scorer.scoring import rank_alerts_for_client, score_alert


def _client() -> CanonicalizedClientProfile:
    """Build a canonical client profile for scoring tests.

    Returns:
        CanonicalizedClientProfile: Test client profile.
    """

    return CanonicalizedClientProfile(
        client_name="Solstice Robotics",
        ticker="SLRB",
        sector="industrial_robotics",
        focal_companies=["solstice_robotics"],
        competitors=["kestrel_automation"],
        suppliers=["quanta_sensing"],
        customers=["northline_logistics"],
        geo_markets=["united_states"],
        key_markets=["warehouse_automation"],
        commodities=["semiconductor_chips"],
        regulators=["cfius"],
        macro_sensitivities=["interest_rates"],
        themes=["ai_driven_automation"],
    )


def _company(canonical: str, ticker: str | None = None) -> CanonicalCompanyItem:
    """Build a canonical company item.

    Args:
        canonical (str): Canonical company ID.
        ticker (str | None): Optional ticker.

    Returns:
        CanonicalCompanyItem: Test company item.
    """

    return CanonicalCompanyItem(
        name=canonical.replace("_", " "),
        ticker=ticker,
        canonical=canonical,
        rationale=f"{canonical} appears in the alert.",
    )


def _metadata(canonical: str) -> CanonicalMetadataItem:
    """Build a canonical metadata item.

    Args:
        canonical (str): Canonical metadata ID.

    Returns:
        CanonicalMetadataItem: Test metadata item.
    """

    return CanonicalMetadataItem(
        name=canonical.replace("_", " "),
        canonical=canonical,
        rationale=f"{canonical} appears in the alert.",
    )


def _alert(
    alert_id: str,
    received_at: str = "2026-08-11T12:00:00Z",
    subject: str = "Market update",
    body: str = "General business update.",
    companies: Sequence[CanonicalCompanyItem] | None = None,
    **metadata: list[CanonicalMetadataItem],
) -> CanonicalizedAlert:
    """Build a canonical alert for scoring tests.

    Args:
        alert_id (str): Alert identifier.
        received_at (str): ISO received-at timestamp.
        subject (str): Alert subject.
        body (str): Alert body.
        companies (Sequence[CanonicalCompanyItem] | None): Company metadata.
        **metadata (list[CanonicalMetadataItem]): Canonical metadata fields.

    Returns:
        CanonicalizedAlert: Test alert.
    """

    return CanonicalizedAlert(
        id=alert_id,
        received_at=received_at,
        subject=subject,
        body=body,
        companies=list(companies or []),
        **metadata,
    )


def _date_range() -> AlertDateRange:
    """Build a fixed scoring date range.

    Returns:
        AlertDateRange: Test date range.
    """

    return build_alert_date_range(
        "2026-08-10T00:00:00Z",
        "2026-08-11T23:59:59Z",
    )


def _scored_at() -> datetime:
    """Build a fixed recency anchor for scoring tests.

    Returns:
        datetime: Timezone-aware scoring anchor.
    """

    return datetime(2026, 8, 11, 23, 59, 59, tzinfo=UTC)


def _score_alert(
    alert: CanonicalizedAlert,
    client: CanonicalizedClientProfile | None = None,
    date_range: AlertDateRange | None = None,
    scored_at: datetime | None = None,
) -> RankedAlertResult:
    """Score a test alert with deterministic defaults.

    Args:
        alert (CanonicalizedAlert): Candidate alert.
        client (CanonicalizedClientProfile | None): Optional client override.
        date_range (AlertDateRange | None): Optional date range override.
        scored_at (datetime | None): Optional recency anchor override.

    Returns:
        RankedAlertResult: Scored alert result.
    """

    return score_alert(
        alert,
        client or _client(),
        date_range or _date_range(),
        scored_at=scored_at or _scored_at(),
    )


def _criterion(result_score: list[CriterionScore], name: str) -> CriterionScore:
    """Find a criterion score by name.

    Args:
        result_score (list[CriterionScore]): Criterion scores to search.
        name (str): Criterion name.

    Returns:
        CriterionScore: Matching criterion score.

    Raises:
        AssertionError: If the criterion is absent.
    """

    for score in result_score:
        if score.name == name:
            return score
    raise AssertionError(f"Missing criterion score {name}")


def test_direct_client_canonical_match_beats_related_company_matches() -> None:
    """Verify direct client proximity outranks isolated business relationships."""

    client = _client()
    direct = _score_alert(
        _alert("direct", companies=[_company("solstice_robotics")]),
        client,
    )
    competitor = _score_alert(
        _alert("competitor", companies=[_company("kestrel_automation")]),
        client,
    )
    customer = _score_alert(
        _alert("customer", companies=[_company("northline_logistics")]),
        client,
    )
    supplier = _score_alert(
        _alert("supplier", companies=[_company("quanta_sensing")]),
        client,
    )

    assert direct.final_score > competitor.final_score
    assert direct.final_score > customer.final_score
    assert direct.final_score > supplier.final_score
    assert direct.matched_signals[0].name == "direct_client_canonical"


def test_textual_client_name_scores_below_canonical_client_match() -> None:
    """Verify client-name text is useful but weaker than canonical matching."""

    client = _client()
    canonical = _score_alert(
        _alert("canonical", companies=[_company("solstice_robotics")]),
        client,
    )
    textual = _score_alert(
        _alert(
            "textual",
            subject="Solstice Robotics expands its automation program",
        ),
        client,
    )

    assert canonical.final_score > textual.final_score
    assert [signal.name for signal in textual.matched_signals] == ["client_name_text"]


def test_ticker_metadata_and_text_do_not_affect_score() -> None:
    """Verify ticker remains in data but does not contribute to relevance."""

    client = _client()
    plain = _score_alert(_alert("plain"), client)
    ticker_only = _score_alert(
        _alert(
            "ticker-only",
            subject="SLRB market update",
            body="SLRB appears in text and metadata.",
            companies=[_company("unrelated_company", ticker="SLRB")],
        ),
        client,
    )

    assert ticker_only.final_score == plain.final_score
    assert ticker_only.matched_signals == []
    assert not any("ticker" in evidence for evidence in ticker_only.evidence)


def test_competitor_key_market_combination_beats_isolated_signals() -> None:
    """Verify competitor plus key market earns an explicit combination bonus."""

    client = _client()
    competitor = _score_alert(
        _alert("competitor", companies=[_company("kestrel_automation")]),
        client,
    )
    key_market = _score_alert(
        _alert("key-market", key_markets=[_metadata("warehouse_automation")]),
        client,
    )
    combined = _score_alert(
        _alert(
            "combined",
            companies=[_company("kestrel_automation")],
            key_markets=[_metadata("warehouse_automation")],
        ),
        client,
    )

    assert combined.final_score > competitor.final_score
    assert combined.final_score > key_market.final_score
    assert [bonus.name for bonus in combined.combination_bonuses] == [
        "competitor_with_key_market"
    ]


def test_supplier_commodity_combination_beats_supplier_only() -> None:
    """Verify supplier plus commodity earns an explicit combination bonus."""

    client = _client()
    supplier = _score_alert(
        _alert("supplier", companies=[_company("quanta_sensing")]),
        client,
    )
    combined = _score_alert(
        _alert(
            "combined",
            companies=[_company("quanta_sensing")],
            commodities=[_metadata("semiconductor_chips")],
        ),
        client,
    )

    assert combined.final_score > supplier.final_score
    assert [bonus.name for bonus in combined.combination_bonuses] == [
        "supplier_with_commodity"
    ]


def test_rank_evidence_includes_all_reason_scores_and_recency() -> None:
    """Verify rank evidence exposes every scoring reason with point values."""

    result = _score_alert(
        _alert(
            "combined",
            received_at="2026-08-11T20:00:00Z",
            companies=[_company("kestrel_automation")],
            key_markets=[_metadata("warehouse_automation")],
        ),
    )

    assert any(
        evidence.startswith("relationship_proximity.competitor +28.00 pts")
        for evidence in result.evidence
    )
    assert any(
        evidence.startswith("operational_exposure.key_market +12.00 pts")
        for evidence in result.evidence
    )
    assert any(
        evidence.startswith("competitor_with_key_market +8.00 pts")
        for evidence in result.evidence
    )
    assert any(evidence.startswith("recency +") for evidence in result.evidence)
    assert len(result.evidence) == 4


def test_broad_context_only_scores_low() -> None:
    """Verify broad sector, geography, and theme context stays bounded."""

    alert = _alert(
        "broad",
        received_at="2026-08-10T00:00:00Z",
        sectors=[_metadata("industrial_robotics")],
        geo_markets=[_metadata("united_states")],
        themes=[_metadata("ai_driven_automation")],
    )

    result = _score_alert(alert, scored_at=datetime(2026, 8, 15, tzinfo=UTC))

    assert result.final_score <= 12
    assert _criterion(result.criterion_scores, "broad_context").score_contribution == 10
    assert [bonus.name for bonus in result.combination_bonuses] == [
        "broad_context_only_combination"
    ]


def test_newer_alert_scores_higher_when_business_signals_match() -> None:
    """Verify recency orders equally relevant alerts."""

    older = _alert(
        "older",
        received_at="2026-08-10T08:00:00Z",
        companies=[_company("solstice_robotics")],
    )
    newer = _alert(
        "newer",
        received_at="2026-08-11T20:00:00Z",
        companies=[_company("solstice_robotics")],
    )

    older_result = _score_alert(older)
    newer_result = _score_alert(newer)

    assert newer_result.final_score > older_result.final_score


def test_recency_uses_scoring_anchor_not_filter_range_end() -> None:
    """Verify historical ranges do not make old alerts look newly received."""

    scored_at = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)
    june_range = build_alert_date_range(
        "2026-05-01T00:00:00Z",
        "2026-06-30T23:59:59Z",
    )
    august_range = build_alert_date_range(
        "2026-08-09T00:00:00Z",
        "2026-08-13T23:59:59Z",
    )

    june_result = score_alert(
        _alert(
            "june",
            received_at="2026-06-27T09:00:00Z",
            companies=[_company("solstice_robotics")],
        ),
        _client(),
        june_range,
        scored_at=scored_at,
    )
    august_result = score_alert(
        _alert(
            "august",
            received_at="2026-08-11T09:00:00Z",
            companies=[_company("solstice_robotics")],
        ),
        _client(),
        august_range,
        scored_at=scored_at,
    )

    june_recency = _criterion(june_result.criterion_scores, "recency")
    august_recency = _criterion(august_result.criterion_scores, "recency")
    assert june_recency.score_contribution == 0
    assert august_recency.score_contribution > june_recency.score_contribution
    assert "scored as of 2026-08-13T12:00:00+00:00" in august_result.evidence[-1]


def test_old_direct_alert_beats_recent_generic_alert() -> None:
    """Verify business proximity has greater influence than recency alone."""

    old_direct = _score_alert(
        _alert(
            "old-direct",
            received_at="2026-08-10T00:00:00Z",
            companies=[_company("solstice_robotics")],
        ),
    )
    recent_generic = _score_alert(
        _alert("recent-generic", received_at="2026-08-11T23:00:00Z"),
    )

    assert old_direct.final_score > recent_generic.final_score


def test_ranking_orders_by_score_and_truncates_top_n() -> None:
    """Verify ranked results are ordered and limited to top N."""

    alerts = [
        _alert("weak", received_at="2026-08-11T20:00:00Z"),
        _alert(
            "best",
            received_at="2026-08-11T18:00:00Z",
            companies=[_company("solstice_robotics")],
            key_markets=[_metadata("warehouse_automation")],
            themes=[_metadata("ai_driven_automation")],
        ),
        _alert(
            "second",
            received_at="2026-08-11T17:00:00Z",
            companies=[_company("kestrel_automation")],
            key_markets=[_metadata("warehouse_automation")],
        ),
    ]

    ranked = rank_alerts_for_client(
        alerts,
        _client(),
        _date_range(),
        top_n=2,
        scored_at=_scored_at(),
    )

    assert [result.alert_id for result in ranked] == ["best", "second"]
    assert [result.rank for result in ranked] == [1, 2]


def test_ranking_rejects_invalid_top_n() -> None:
    """Verify top-N must be positive."""

    with pytest.raises(ValueError, match="top_n"):
        rank_alerts_for_client([], _client(), _date_range(), top_n=0)
