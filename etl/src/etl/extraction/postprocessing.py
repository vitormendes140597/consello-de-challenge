"""Post-processing helpers for first-pass alert extraction results."""

from __future__ import annotations

from etl.common.fields import METADATA_FIELDS
from etl.common.schemas import (
    AlertMetadata,
    CompanyItem,
    EnrichedAlert,
    MetadataItem,
    RawAlert,
)


def build_enriched_alert(
    alert: RawAlert,
    metadata: AlertMetadata,
) -> EnrichedAlert:
    """Combine a raw alert with normalized first-pass metadata.

    Args:
        alert (RawAlert): Source alert whose fields must be preserved unchanged.
        metadata (AlertMetadata): Metadata extracted from the alert text.

    Returns:
        EnrichedAlert: Source fields plus normalized and deduplicated metadata.
    """

    normalized_metadata = normalize_alert_metadata(metadata)
    return EnrichedAlert.model_validate(
        {
            **alert.model_dump(mode="json"),
            **normalized_metadata.model_dump(mode="json"),
        }
    )


def normalize_alert_metadata(metadata: AlertMetadata) -> AlertMetadata:
    """Normalize names and deduplicate extracted metadata within one alert.

    Args:
        metadata (AlertMetadata): Validated model extraction result.

    Returns:
        AlertMetadata: Metadata with lower-case names and tickers, deduplicated
        independently within each metadata array.
    """

    updates: dict[str, object] = {
        "companies": _deduplicate_companies(metadata.companies),
    }
    for field in METADATA_FIELDS:
        updates[field] = _deduplicate_metadata_items(getattr(metadata, field))

    return metadata.model_copy(update=updates)


def _deduplicate_companies(companies: list[CompanyItem]) -> list[CompanyItem]:
    """Normalize and deduplicate company items by lower-case name.

    Args:
        companies (list[CompanyItem]): Extracted company items.

    Returns:
        list[CompanyItem]: First item for each normalized company name.
    """

    deduplicated: dict[str, CompanyItem] = {}
    for company in companies:
        normalized_name = company.name.lower()
        if normalized_name in deduplicated:
            continue
        normalized_ticker = company.ticker.lower() if company.ticker else None
        deduplicated[normalized_name] = company.model_copy(
            update={
                "name": normalized_name,
                "ticker": normalized_ticker,
            }
        )
    return list(deduplicated.values())


def _deduplicate_metadata_items(items: list[MetadataItem]) -> list[MetadataItem]:
    """Normalize and deduplicate metadata items by lower-case name.

    Args:
        items (list[MetadataItem]): Extracted non-company metadata items.

    Returns:
        list[MetadataItem]: First item for each normalized metadata name.
    """

    deduplicated: dict[str, MetadataItem] = {}
    for item in items:
        normalized_name = item.name.lower()
        if normalized_name in deduplicated:
            continue
        deduplicated[normalized_name] = item.model_copy(
            update={"name": normalized_name},
        )
    return list(deduplicated.values())


__all__ = [
    "METADATA_FIELDS",
    "build_enriched_alert",
    "normalize_alert_metadata",
]
