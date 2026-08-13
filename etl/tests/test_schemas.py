"""Tests for ETL Pydantic schema contracts."""

import pytest
from pydantic import ValidationError

from etl.canonicalization.schemas import (
    CanonicalCatalog,
    CanonicalizedAlert,
    CanonicalizedCustomerProfile,
)
from etl.common.fields import CANONICAL_FIELDS
from etl.common.schemas import (
    AlertMetadata,
    CompanyItem,
    EnrichedAlert,
    RawAlert,
)


def test_raw_alert_requires_source_fields() -> None:
    """Verify raw alerts require all source fields."""

    with pytest.raises(ValidationError):
        RawAlert(
            id="a01",
            received_at="2026-08-11T09:00:00+00:00",
            subject="Solstice reports earnings",
        )


def test_company_item_allows_null_ticker() -> None:
    """Verify company ticker can be null when unavailable."""

    company = CompanyItem(
        name="solstice robotics",
        ticker=None,
        rationale="The alert names Solstice Robotics.",
    )

    assert company.ticker is None


def test_alert_metadata_defaults_to_empty_arrays() -> None:
    """Verify metadata arrays default to empty lists."""

    metadata = AlertMetadata()

    assert metadata.companies == []
    assert metadata.sectors == []
    assert metadata.geo_markets == []
    assert metadata.key_markets == []
    assert metadata.commodities == []
    assert metadata.regulators == []
    assert metadata.macro_sensitivities == []
    assert metadata.themes == []


def test_enriched_alert_combines_source_fields_and_metadata() -> None:
    """Verify enriched alerts keep source fields and metadata fields together."""

    enriched = EnrichedAlert(
        id="a01",
        received_at="2026-08-11T09:00:00+00:00",
        subject="Solstice reports earnings",
        body="Solstice Robotics reported stronger warehouse automation demand.",
        companies=[
            {
                "name": "solstice robotics",
                "ticker": "slrb",
                "rationale": "The alert names Solstice Robotics.",
            }
        ],
    )

    assert enriched.id == "a01"
    assert enriched.companies[0].name == "solstice robotics"
    assert enriched.companies[0].ticker == "slrb"


def test_canonicalized_alert_preserves_source_and_adds_canonical_metadata() -> None:
    """Verify canonicalized alerts preserve source fields and canonicalized items."""

    alert = CanonicalizedAlert(
        id="a01",
        received_at="2026-08-11T09:00:00+00:00",
        subject="Solstice reports earnings",
        body="Solstice Robotics reported warehouse automation demand.",
        companies=[
            {
                "name": "solstice robotics",
                "ticker": "slrb",
                "canonical": "solstice_robotics",
                "rationale": "The alert names Solstice Robotics.",
            }
        ],
        key_markets=[
            {
                "name": "warehouse robotics",
                "canonical": "warehouse_automation",
                "rationale": "The alert cites warehouse robotics demand.",
            }
        ],
    )

    assert alert.id == "a01"
    assert alert.companies[0].ticker == "slrb"
    assert alert.companies[0].canonical == "solstice_robotics"
    assert alert.key_markets[0].name == "warehouse robotics"


def test_canonicalized_metadata_allows_null_canonical_values() -> None:
    """Verify unmapped canonical values are represented as null."""

    alert = CanonicalizedAlert(
        id="a01",
        received_at="2026-08-11T09:00:00+00:00",
        subject="Solstice reports earnings",
        body="Solstice Robotics reported demand.",
        themes=[
            {
                "name": "capacity constraints",
                "canonical": None,
                "rationale": "The alert cites supplier capacity constraints.",
            }
        ],
    )

    assert alert.themes[0].canonical is None


def test_canonicalized_customer_profile_uses_profile_shaped_catalog_ids() -> None:
    """Verify canonicalized customer profiles use profile-shaped catalog IDs."""

    profile = CanonicalizedCustomerProfile(
        client_name="Solstice Robotics",
        ticker="SLRB",
        sector="sectors_value",
        focal_companies=["companies_value"],
        competitors=["companies_value"],
        geo_markets=["geo_markets_value"],
        key_markets=["key_markets_value"],
    )

    assert profile.client_name == "Solstice Robotics"
    assert profile.ticker == "SLRB"
    assert profile.sector == "sectors_value"
    assert profile.focal_companies == ["companies_value"]
    assert profile.competitors == ["companies_value"]
    assert profile.geo_markets == ["geo_markets_value"]
    assert profile.key_markets == ["key_markets_value"]


def test_canonicalized_customer_profile_validates_against_catalog() -> None:
    """Verify profile-shaped canonical IDs are validated by catalog field."""

    catalog = _minimal_catalog()
    profile = CanonicalizedCustomerProfile(
        focal_companies=["unknown_company"],
    )

    with pytest.raises(ValueError, match="not allowed"):
        profile.validate_canonical_values(catalog)


def test_canonicalized_metadata_validates_against_catalog() -> None:
    """Verify canonicalized records reject non-catalog canonical values."""

    catalog = _minimal_catalog()
    alert = CanonicalizedAlert(
        id="a01",
        received_at="2026-08-11T09:00:00+00:00",
        subject="Solstice reports earnings",
        body="Solstice Robotics reported demand.",
        companies=[
            {
                "name": "solstice robotics",
                "ticker": "slrb",
                "canonical": "unknown_company",
                "rationale": "The alert names Solstice Robotics.",
            }
        ],
    )

    with pytest.raises(ValueError, match="not allowed"):
        alert.validate_canonical_values(catalog)


def test_canonicalized_metadata_accepts_catalog_values() -> None:
    """Verify canonicalized records accept configured canonical values."""

    catalog = _minimal_catalog()
    alert = CanonicalizedAlert(
        id="a01",
        received_at="2026-08-11T09:00:00+00:00",
        subject="Solstice reports earnings",
        body="Solstice Robotics reported demand.",
        companies=[
            {
                "name": "solstice robotics",
                "ticker": "slrb",
                "canonical": "companies_value",
                "rationale": "The alert names Solstice Robotics.",
            }
        ],
    )

    alert.validate_canonical_values(catalog)


def _minimal_catalog() -> CanonicalCatalog:
    """Create a minimal valid canonical catalog for schema tests.

    Returns:
        CanonicalCatalog: Catalog with one allowed value per supported field.
    """

    return CanonicalCatalog.model_validate(
        {
            "version": 1,
            "fields": {
                field: {
                    "description": f"{field} field",
                    "values": {
                        f"{field}_value": {
                            "label": f"{field} value",
                            "description": f"{field} description",
                        }
                    },
                }
                for field in CANONICAL_FIELDS
            },
        }
    )
