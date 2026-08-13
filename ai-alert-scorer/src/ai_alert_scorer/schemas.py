"""Pydantic schemas for canonical alert relevance inputs."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CanonicalMetadataItem(BaseModel):
    """Canonicalized non-company metadata item from an alert artifact.

    Attributes:
        name (str): Original extracted metadata value.
        canonical (str | None): Canonical catalog ID, or null when unmapped.
        rationale (str): Evidence from the source alert.
    """

    name: str = Field(description="Original extracted metadata value.")
    canonical: str | None = Field(
        default=None,
        description="Canonical catalog ID for the item, or null when unmapped.",
    )
    rationale: str = Field(description="Alert-grounded extraction rationale.")


class CanonicalCompanyItem(BaseModel):
    """Canonicalized company metadata item from an alert artifact.

    Attributes:
        name (str): Original extracted company name.
        ticker (str | None): Original extracted ticker when present.
        canonical (str | None): Canonical company catalog ID, or null.
        rationale (str): Evidence from the source alert.
    """

    name: str = Field(description="Original extracted company name.")
    ticker: str | None = Field(
        default=None,
        description="Original extracted ticker when present.",
    )
    canonical: str | None = Field(
        default=None,
        description="Canonical company catalog ID, or null when unmapped.",
    )
    rationale: str = Field(description="Alert-grounded extraction rationale.")


class CanonicalizedAlert(BaseModel):
    """Canonicalized alert record consumed by relevance scoring.

    Attributes:
        id (str): Source alert identifier.
        received_at (str): Source alert receipt timestamp.
        subject (str): Source alert subject or headline.
        body (str): Source alert body text.
        companies (list[CanonicalCompanyItem]): Canonicalized company items.
        sectors (list[CanonicalMetadataItem]): Canonicalized sector items.
        geo_markets (list[CanonicalMetadataItem]): Canonicalized geo-market
            items.
        key_markets (list[CanonicalMetadataItem]): Canonicalized key-market
            items.
        commodities (list[CanonicalMetadataItem]): Canonicalized commodity
            items.
        regulators (list[CanonicalMetadataItem]): Canonicalized regulator
            items.
        macro_sensitivities (list[CanonicalMetadataItem]): Canonicalized macro
            sensitivity items.
        themes (list[CanonicalMetadataItem]): Canonicalized theme items.
    """

    id: str = Field(description="Source alert identifier.")
    received_at: str = Field(description="Source alert receipt timestamp.")
    subject: str = Field(description="Source alert subject or headline.")
    body: str = Field(description="Source alert body text.")
    companies: list[CanonicalCompanyItem] = Field(default_factory=list)
    sectors: list[CanonicalMetadataItem] = Field(default_factory=list)
    geo_markets: list[CanonicalMetadataItem] = Field(default_factory=list)
    key_markets: list[CanonicalMetadataItem] = Field(default_factory=list)
    commodities: list[CanonicalMetadataItem] = Field(default_factory=list)
    regulators: list[CanonicalMetadataItem] = Field(default_factory=list)
    macro_sensitivities: list[CanonicalMetadataItem] = Field(default_factory=list)
    themes: list[CanonicalMetadataItem] = Field(default_factory=list)


class CanonicalizedClientProfile(BaseModel):
    """Profile-shaped canonicalized client profile consumed by scoring.

    Attributes:
        client_name (str | None): Raw client profile name.
        ticker (str | None): Raw client ticker.
        sector (str | None): Canonical sector ID.
        focal_companies (list[str]): Canonical IDs for focal companies.
        competitors (list[str]): Canonical IDs for competitors.
        suppliers (list[str]): Canonical IDs for suppliers.
        customers (list[str]): Canonical IDs for customers.
        geo_markets (list[str]): Canonical geographic market IDs.
        key_markets (list[str]): Canonical key market IDs.
        commodities (list[str]): Canonical commodity IDs.
        regulators (list[str]): Canonical regulator IDs.
        macro_sensitivities (list[str]): Canonical macro sensitivity IDs.
        themes (list[str]): Canonical theme IDs.
    """

    client_name: str | None = Field(default=None)
    ticker: str | None = Field(default=None)
    sector: str | None = Field(default=None)
    focal_companies: list[str] = Field(default_factory=list)
    competitors: list[str] = Field(default_factory=list)
    suppliers: list[str] = Field(default_factory=list)
    customers: list[str] = Field(default_factory=list)
    geo_markets: list[str] = Field(default_factory=list)
    key_markets: list[str] = Field(default_factory=list)
    commodities: list[str] = Field(default_factory=list)
    regulators: list[str] = Field(default_factory=list)
    macro_sensitivities: list[str] = Field(default_factory=list)
    themes: list[str] = Field(default_factory=list)


class CriterionScore(BaseModel):
    """Auditable score contribution for one scoring group.

    Attributes:
        name (str): Stable criterion name.
        group (str): Scoring matrix group.
        weight (float): Maximum contribution for this criterion.
        normalized_score (float): Criterion score normalized to 0.0-1.0.
        score_contribution (float): Point contribution to the final 0-100 score.
        evidence (list[str]): Concise evidence supporting the contribution.
    """

    name: str
    group: str
    weight: float = Field(ge=0.0)
    normalized_score: float = Field(ge=0.0, le=1.0)
    score_contribution: float = Field(ge=0.0)
    evidence: list[str] = Field(default_factory=list)


class MatchedSignal(BaseModel):
    """Individual matrix signal matched while scoring an alert.

    Attributes:
        name (str): Stable signal name.
        group (str): Scoring matrix group.
        weight (float): Base signal weight before group caps.
        matched_canonical_ids (list[str]): Canonical IDs supporting this signal.
        evidence (list[str]): Concise alert-grounded signal evidence.
    """

    name: str
    group: str
    weight: float = Field(ge=0.0)
    matched_canonical_ids: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class CombinationBonus(BaseModel):
    """Bonus applied for a meaningful combination of matched signals.

    Attributes:
        name (str): Stable bonus name.
        group (str): Scoring matrix group.
        weight (float): Bonus points before the combination group cap.
        matched_signal_names (list[str]): Signals that triggered the bonus.
        evidence (list[str]): Concise evidence supporting the bonus.
    """

    name: str
    group: str
    weight: float = Field(ge=0.0)
    matched_signal_names: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class RankedAlertResult(BaseModel):
    """Structured ranked alert output from deterministic scoring.

    Attributes:
        rank (int): One-based rank in the returned result set.
        alert_id (str): Source alert identifier.
        received_at (str): Source alert receipt timestamp.
        subject (str): Source alert subject or headline.
        final_score (float): Aggregated score on a 0-100 scale.
        criterion_scores (list[CriterionScore]): Group-level score breakdown.
        matched_signals (list[MatchedSignal]): Individual matrix signals
            matched while scoring.
        combination_bonuses (list[CombinationBonus]): Applied deterministic
            signal-combination bonuses.
        matched_canonical_ids (list[str]): Deduplicated canonical IDs matched
            across all criteria.
        evidence (list[str]): Concise top evidence for explaining relevance.
    """

    rank: int = Field(ge=0)
    alert_id: str
    received_at: str
    subject: str
    final_score: float = Field(ge=0.0, le=100.0)
    criterion_scores: list[CriterionScore] = Field(default_factory=list)
    matched_signals: list[MatchedSignal] = Field(default_factory=list)
    combination_bonuses: list[CombinationBonus] = Field(default_factory=list)
    matched_canonical_ids: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class RankingResult(BaseModel):
    """Collection of ranked alerts returned by the ranking tool.

    Attributes:
        top_n (int): Requested maximum result count.
        ranked_alerts (list[RankedAlertResult]): Ranked alert results.
    """

    top_n: int = Field(ge=1)
    ranked_alerts: list[RankedAlertResult] = Field(default_factory=list)


__all__ = [
    "CanonicalCompanyItem",
    "CanonicalMetadataItem",
    "CanonicalizedAlert",
    "CanonicalizedClientProfile",
    "CombinationBonus",
    "CriterionScore",
    "MatchedSignal",
    "RankedAlertResult",
    "RankingResult",
]
