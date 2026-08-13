"""Pydantic schemas for canonical catalog and canonicalized ETL records."""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel, Field, model_validator

from etl.common.fields import CANONICAL_FIELDS
from etl.common.schemas import AlertMetadata, RawAlert


class CanonicalizationPayload(AlertMetadata):
    """Common first-pass metadata payload accepted by canonicalization.

    Attributes:
        source_type (str): Source kind, such as ``alert`` or
            ``customer_profile``.
        source_id (str | None): Optional stable source identifier used for
            tracing prompts and model responses.
    """

    source_type: str = Field(
        description="Structured source kind being canonicalized.",
    )
    source_id: str | None = Field(
        default=None,
        description="Optional source identifier for traceability.",
    )


class CanonicalCatalogEntry(BaseModel):
    """Allowed canonical value and mapping hints for one catalog entry.

    Attributes:
        label (str): Human-readable name for the stable canonical ID.
        aliases (list[str]): Strong naming variants that can map to this
            canonical value.
        related_terms (list[str]): Semantic hints that can help the LLM reason
            but do not by themselves force a match.
        law_or_regime_aliases (list[str]): Laws, regimes, review processes, or
            enforcement frameworks that explicitly map to this canonical entity.
        exclude (list[str]): Nearby concepts that should not map here.
        description (str): Short boundary description for this canonical entry.
    """

    label: str = Field(
        description="Human-readable label for the stable canonical value.",
    )
    aliases: list[str] = Field(
        default_factory=list,
        description="Direct aliases or naming variants for the canonical value.",
    )
    related_terms: list[str] = Field(
        default_factory=list,
        description="Semantic hints that do not automatically force a mapping.",
    )
    law_or_regime_aliases: list[str] = Field(
        default_factory=list,
        description=(
            "Laws, regimes, review processes, or enforcement frameworks that "
            "explicitly map to this canonical entity."
        ),
    )
    exclude: list[str] = Field(
        default_factory=list,
        description="Related concepts that should not map to this value.",
    )
    description: str = Field(
        description="Concise boundary description for this canonical entry.",
    )


class CanonicalCatalogField(BaseModel):
    """Canonical catalog entries for one supported metadata field.

    Attributes:
        description (str): Field-level mapping guidance and boundary.
        values (dict[str, CanonicalCatalogEntry]): Canonical entries keyed by
            stable canonical IDs.
    """

    description: str = Field(
        description="Field-level mapping guidance and semantic boundary.",
    )
    values: dict[str, CanonicalCatalogEntry] = Field(
        description="Allowed canonical entries keyed by stable canonical IDs.",
    )

    @model_validator(mode="after")
    def require_values(self) -> CanonicalCatalogField:
        """Require each catalog field to define at least one canonical value.

        Returns:
            CanonicalCatalogField: Validated field definition.

        Raises:
            ValueError: If the field has no allowed canonical values.
        """

        if not self.values:
            raise ValueError("Canonical catalog field must define at least one value")
        return self


class CanonicalCatalog(BaseModel):
    """Versioned canonical catalog for all supported metadata fields.

    Attributes:
        version (int): Positive catalog schema/data version.
        fields (dict[str, CanonicalCatalogField]): Supported canonical fields
            keyed by field name.
    """

    version: int = Field(
        ge=1,
        description="Positive catalog version.",
    )
    fields: dict[str, CanonicalCatalogField] = Field(
        description="Canonical catalog fields keyed by supported field name.",
    )

    @model_validator(mode="after")
    def require_supported_fields(self) -> CanonicalCatalog:
        """Require the catalog to cover exactly the supported metadata fields.

        Returns:
            CanonicalCatalog: Validated catalog.

        Raises:
            ValueError: If a supported field is missing or an unknown field is
                configured.
        """

        expected_fields = set(CANONICAL_FIELDS)
        actual_fields = set(self.fields)
        missing_fields = sorted(expected_fields - actual_fields)
        unknown_fields = sorted(actual_fields - expected_fields)
        if missing_fields:
            raise ValueError(
                "Canonical catalog is missing fields: " + ", ".join(missing_fields)
            )
        if unknown_fields:
            raise ValueError(
                "Canonical catalog has unknown fields: " + ", ".join(unknown_fields)
            )
        return self

    def allowed_values(self, field: str) -> set[str]:
        """Return allowed canonical IDs for one supported field.

        Args:
            field (str): Supported canonical field name.

        Returns:
            set[str]: Allowed canonical IDs for the field.

        Raises:
            ValueError: If the field is not configured in the catalog.
        """

        catalog_field = self.fields.get(field)
        if catalog_field is None:
            raise ValueError(f"Unknown canonical catalog field: {field}")
        return set(catalog_field.values)


class CanonicalCandidate(BaseModel):
    """One projected canonical candidate for an extracted item.

    Attributes:
        canonical_id (str): Candidate canonical ID from the catalog.
        label (str): Human-readable catalog label for the candidate.
        match_source (str): Retrieval source, such as ``alias`` or
            ``embedding_similarity``.
        score (float | None): Optional similarity score for ranked candidates.
        description (str): Catalog boundary description for the candidate.
        aliases (list[str]): Strong aliases relevant to model adjudication.
        related_terms (list[str]): Related terms that can help adjudication but
            should not force a match by themselves.
        exclude (list[str]): Nearby concepts that should not map here.
    """

    canonical_id: str = Field(
        description="Candidate canonical ID from the catalog.",
    )
    label: str = Field(
        description="Human-readable candidate label.",
    )
    match_source: str = Field(
        description="How the candidate was projected for this item.",
    )
    score: float | None = Field(
        default=None,
        description="Optional similarity score when candidate ranking used embeddings.",
    )
    description: str = Field(
        description="Catalog boundary description for this candidate.",
    )
    aliases: list[str] = Field(
        default_factory=list,
        description="Strong aliases for this candidate.",
    )
    related_terms: list[str] = Field(
        default_factory=list,
        description="Semantic hints that do not automatically force a match.",
    )
    exclude: list[str] = Field(
        default_factory=list,
        description="Related concepts that should not map to this candidate.",
    )


class CanonicalItemCandidates(BaseModel):
    """Projected candidates for one extracted item.

    Attributes:
        field (str): Supported canonical field containing the item.
        item_index (int): Zero-based item position within the field array.
        name (str): Original item name preserved for traceability.
        normalized_name (str): Locally normalized name used for lookup/cache.
        candidates (list[CanonicalCandidate]): Candidate canonical IDs for the
            item, ordered from strongest to weakest.
    """

    field: str = Field(
        description="Supported canonical field for the extracted item.",
    )
    item_index: int = Field(
        ge=0,
        description="Zero-based item position within the field array.",
    )
    name: str = Field(
        description="Original extracted item name.",
    )
    normalized_name: str = Field(
        description="Normalized item name used for deterministic lookup and cache.",
    )
    candidates: list[CanonicalCandidate] = Field(
        default_factory=list,
        description="Projected canonical candidates for this item.",
    )

    @model_validator(mode="after")
    def require_supported_field(self) -> CanonicalItemCandidates:
        """Validate the candidate set belongs to a supported canonical field.

        Returns:
            CanonicalItemCandidates: Validated candidate set.

        Raises:
            ValueError: If ``field`` is not one of the supported canonical
                fields.
        """

        if self.field not in CANONICAL_FIELDS:
            raise ValueError(f"Unsupported canonical candidate field: {self.field}")
        return self

    def candidate_ids(self) -> set[str]:
        """Return candidate canonical IDs for this item.

        Returns:
            set[str]: Canonical IDs projected for this item.
        """

        return {candidate.canonical_id for candidate in self.candidates}


class CanonicalCandidateProjection(BaseModel):
    """Candidate projection for one structured source object.

    Attributes:
        catalog_version (int): Catalog version used to create candidates.
        catalog_hash (str): Stable content hash of the catalog used for cache
            invalidation.
        items (list[CanonicalItemCandidates]): Candidate sets for extracted
            source items.
    """

    catalog_version: int = Field(
        ge=1,
        description="Catalog version used for candidate generation.",
    )
    catalog_hash: str = Field(
        description="Stable content hash of the catalog used for candidate generation.",
    )
    items: list[CanonicalItemCandidates] = Field(
        default_factory=list,
        description="Projected candidate sets for each extracted item.",
    )

    def candidate_ids_for(self, field: str, item_index: int) -> set[str]:
        """Return candidate IDs for one field item.

        Args:
            field (str): Supported canonical field name.
            item_index (int): Zero-based item position inside the field array.

        Returns:
            set[str]: Candidate IDs projected for the item, or an empty set when
            the item has no candidates.
        """

        for item in self.items:
            if item.field == field and item.item_index == item_index:
                return item.candidate_ids()
        return set()


class CanonicalDecisionItem(BaseModel):
    """LLM decision for one canonicalizable extracted item."""

    canonical: str | None = Field(
        default=None,
        description="Selected projected candidate ID, or null when unmapped.",
    )


class CanonicalizationDecision(BaseModel):
    """Structured canonicalization decision returned by the LLM.

    Attributes:
        companies (list[CanonicalDecisionItem]): Decisions for company items,
            aligned by source item order.
        sectors (list[CanonicalDecisionItem]): Decisions for sector items,
            aligned by source item order.
        geo_markets (list[CanonicalDecisionItem]): Decisions for geographic
            market items, aligned by source item order.
        key_markets (list[CanonicalDecisionItem]): Decisions for key-market
            items, aligned by source item order.
        commodities (list[CanonicalDecisionItem]): Decisions for commodity
            items, aligned by source item order.
        regulators (list[CanonicalDecisionItem]): Decisions for regulator
            items, aligned by source item order.
        macro_sensitivities (list[CanonicalDecisionItem]): Decisions for macro
            sensitivity items, aligned by source item order.
        themes (list[CanonicalDecisionItem]): Decisions for theme items,
            aligned by source item order.
    """

    companies: list[CanonicalDecisionItem] = Field(default_factory=list)
    sectors: list[CanonicalDecisionItem] = Field(default_factory=list)
    geo_markets: list[CanonicalDecisionItem] = Field(default_factory=list)
    key_markets: list[CanonicalDecisionItem] = Field(default_factory=list)
    commodities: list[CanonicalDecisionItem] = Field(default_factory=list)
    regulators: list[CanonicalDecisionItem] = Field(default_factory=list)
    macro_sensitivities: list[CanonicalDecisionItem] = Field(default_factory=list)
    themes: list[CanonicalDecisionItem] = Field(default_factory=list)


class CanonicalMetadataItem(BaseModel):
    """Canonicalized non-company metadata item."""

    name: str = Field(
        description="Original extracted metadata value preserved unchanged.",
    )
    canonical: str | None = Field(
        default=None,
        description=(
            "Allowed canonical ID for the item's field, or null when unmapped."
        ),
    )
    rationale: str = Field(
        description="Original extraction rationale preserved unchanged.",
    )


class CanonicalCompanyItem(BaseModel):
    """Canonicalized company metadata item."""

    name: str = Field(
        description="Original extracted company name preserved unchanged.",
    )
    ticker: str | None = Field(
        default=None,
        description="Original extracted ticker preserved unchanged when present.",
    )
    canonical: str | None = Field(
        default=None,
        description="Allowed canonical company ID, or null when unmapped.",
    )
    rationale: str = Field(
        description="Original extraction rationale preserved unchanged.",
    )


class CanonicalizedMetadata(BaseModel):
    """Canonicalized metadata arrays shared by alerts and profiles."""

    companies: list[CanonicalCompanyItem] = Field(
        default_factory=list,
        description="Canonicalized company metadata items.",
    )
    sectors: list[CanonicalMetadataItem] = Field(
        default_factory=list,
        description="Canonicalized sector metadata items.",
    )
    geo_markets: list[CanonicalMetadataItem] = Field(
        default_factory=list,
        description="Canonicalized geographic market metadata items.",
    )
    key_markets: list[CanonicalMetadataItem] = Field(
        default_factory=list,
        description="Canonicalized key market metadata items.",
    )
    commodities: list[CanonicalMetadataItem] = Field(
        default_factory=list,
        description="Canonicalized commodity metadata items.",
    )
    regulators: list[CanonicalMetadataItem] = Field(
        default_factory=list,
        description="Canonicalized regulator metadata items.",
    )
    macro_sensitivities: list[CanonicalMetadataItem] = Field(
        default_factory=list,
        description="Canonicalized macro sensitivity metadata items.",
    )
    themes: list[CanonicalMetadataItem] = Field(
        default_factory=list,
        description="Canonicalized theme metadata items.",
    )

    def validate_canonical_values(self, catalog: CanonicalCatalog) -> None:
        """Validate non-null canonical values against the configured catalog.

        Args:
            catalog (CanonicalCatalog): Catalog defining allowed canonical IDs.

        Returns:
            None: The method raises on invalid canonical values.

        Raises:
            ValueError: If a non-null canonical value is not allowed for its
                metadata field.
        """

        for field in CANONICAL_FIELDS:
            values = (item.canonical for item in getattr(self, field))
            _validate_field_canonical_values(
                catalog=catalog,
                field=field,
                canonical_values=values,
            )


class CanonicalizedAlert(RawAlert, CanonicalizedMetadata):
    """Raw alert record combined with canonicalized structured metadata."""


class CanonicalizedCustomerProfile(BaseModel):
    """Profile-shaped canonicalized customer profile.

    Attributes:
        client_name (str | None): Raw client profile name preserved unchanged.
        ticker (str | None): Raw profile ticker preserved unchanged.
        sector (str | None): Canonical sector ID, or null when unmapped.
        focal_companies (list[str]): Canonical company IDs for focal companies.
        competitors (list[str]): Canonical company IDs for competitors.
        suppliers (list[str]): Canonical company IDs for suppliers.
        customers (list[str]): Canonical company IDs for customers.
        geo_markets (list[str]): Canonical geographic market IDs.
        key_markets (list[str]): Canonical key market IDs.
        commodities (list[str]): Canonical commodity IDs.
        regulators (list[str]): Canonical regulator entity IDs.
        macro_sensitivities (list[str]): Canonical macro sensitivity IDs.
        themes (list[str]): Canonical theme IDs.
    """

    client_name: str | None = Field(
        default=None,
        description="Raw client profile name preserved unchanged.",
    )
    ticker: str | None = Field(
        default=None,
        description="Raw client profile ticker preserved unchanged.",
    )
    sector: str | None = Field(
        default=None,
        description="Canonical sector ID, or null when unmapped.",
    )
    focal_companies: list[str] = Field(
        default_factory=list,
        description="Deduplicated canonical company IDs for focal companies.",
    )
    competitors: list[str] = Field(
        default_factory=list,
        description="Deduplicated canonical company IDs for competitors.",
    )
    suppliers: list[str] = Field(
        default_factory=list,
        description="Deduplicated canonical company IDs for suppliers.",
    )
    customers: list[str] = Field(
        default_factory=list,
        description="Deduplicated canonical company IDs for customers.",
    )
    geo_markets: list[str] = Field(
        default_factory=list,
        description="Deduplicated canonical geographic market IDs.",
    )
    key_markets: list[str] = Field(
        default_factory=list,
        description="Deduplicated canonical key market IDs.",
    )
    commodities: list[str] = Field(
        default_factory=list,
        description="Deduplicated canonical commodity IDs.",
    )
    regulators: list[str] = Field(
        default_factory=list,
        description="Deduplicated canonical regulator entity IDs.",
    )
    macro_sensitivities: list[str] = Field(
        default_factory=list,
        description="Deduplicated canonical macro sensitivity IDs.",
    )
    themes: list[str] = Field(
        default_factory=list,
        description="Deduplicated canonical theme IDs.",
    )

    def validate_canonical_values(self, catalog: CanonicalCatalog) -> None:
        """Validate non-null canonical IDs against the configured catalog.

        Args:
            catalog (CanonicalCatalog): Catalog defining allowed canonical IDs.

        Returns:
            None: The method raises on invalid canonical values.

        Raises:
            ValueError: If a non-null canonical ID is not allowed for its
                profile field.
        """

        _validate_field_canonical_values(
            catalog=catalog,
            field="companies",
            canonical_values=self.focal_companies,
        )
        _validate_field_canonical_values(
            catalog=catalog,
            field="companies",
            canonical_values=self.competitors,
        )
        _validate_field_canonical_values(
            catalog=catalog,
            field="companies",
            canonical_values=self.suppliers,
        )
        _validate_field_canonical_values(
            catalog=catalog,
            field="companies",
            canonical_values=self.customers,
        )
        _validate_field_canonical_values(
            catalog=catalog,
            field="sectors",
            canonical_values=(self.sector,),
        )
        for field in (
            "geo_markets",
            "key_markets",
            "commodities",
            "regulators",
            "macro_sensitivities",
            "themes",
        ):
            _validate_field_canonical_values(
                catalog=catalog,
                field=field,
                canonical_values=getattr(self, field),
            )


def _validate_field_canonical_values(
    catalog: CanonicalCatalog,
    field: str,
    canonical_values: Iterable[str | None],
) -> None:
    """Validate canonical values for one metadata field.

    Args:
        catalog (CanonicalCatalog): Catalog defining allowed canonical IDs.
        field (str): Supported canonical field name.
        canonical_values (object): Iterable of canonical values emitted for the
            field.

    Returns:
        None: The function raises on invalid canonical values.

    Raises:
        ValueError: If a non-null canonical value is not allowed.
    """

    allowed_values = catalog.allowed_values(field)
    for canonical in canonical_values:
        if canonical is None or canonical in allowed_values:
            continue
        raise ValueError(
            f"Canonical value {canonical!r} is not allowed for field {field!r}"
        )


__all__ = [
    "CanonicalCatalog",
    "CanonicalCatalogEntry",
    "CanonicalCatalogField",
    "CanonicalCandidate",
    "CanonicalCandidateProjection",
    "CanonicalCompanyItem",
    "CanonicalDecisionItem",
    "CanonicalItemCandidates",
    "CanonicalMetadataItem",
    "CanonicalizationDecision",
    "CanonicalizationPayload",
    "CanonicalizedAlert",
    "CanonicalizedCustomerProfile",
    "CanonicalizedMetadata",
]
