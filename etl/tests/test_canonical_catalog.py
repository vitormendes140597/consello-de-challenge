"""Tests for canonical catalog loading and validation."""

from __future__ import annotations

import copy
import json

import pytest
from pydantic import ValidationError

from etl.canonicalization.catalog import (
    load_canonical_catalog,
    validate_canonical_values,
)
from etl.canonicalization.schemas import CanonicalCatalog
from etl.common.fields import CANONICAL_FIELDS


def test_load_canonical_catalog_reads_default_catalog() -> None:
    """Verify the default canonical catalog covers all supported fields."""

    catalog = load_canonical_catalog()

    assert catalog.version == 1
    assert set(catalog.fields) == set(CANONICAL_FIELDS)
    assert "cfius" in catalog.allowed_values("regulators")
    assert (
        "eu ai act"
        in catalog.fields["regulators"]
        .values["european_commission"]
        .law_or_regime_aliases
    )


def test_load_canonical_catalog_validates_custom_path(tmp_path) -> None:
    """Verify a catalog can be loaded from an explicit path."""

    catalog_data = _minimal_catalog_data()
    catalog_path = tmp_path / "canonical_catalog.json"
    catalog_path.write_text(json.dumps(catalog_data), encoding="utf-8")

    catalog = load_canonical_catalog(catalog_path)

    assert catalog.allowed_values("companies") == {"companies_value"}


def test_load_canonical_catalog_rejects_malformed_custom_path(tmp_path) -> None:
    """Verify malformed catalog files fail during loading."""

    catalog_data = _minimal_catalog_data()
    catalog_data["fields"]["companies"]["values"] = {}
    catalog_path = tmp_path / "canonical_catalog.json"
    catalog_path.write_text(json.dumps(catalog_data), encoding="utf-8")

    with pytest.raises(ValidationError, match="at least one value"):
        load_canonical_catalog(catalog_path)


def test_canonical_catalog_rejects_missing_supported_field() -> None:
    """Verify catalog validation requires every supported canonical field."""

    catalog_data = _minimal_catalog_data()
    catalog_data["fields"].pop("themes")

    with pytest.raises(ValidationError, match="themes"):
        CanonicalCatalog.model_validate(catalog_data)


def test_canonical_catalog_rejects_empty_field_values() -> None:
    """Verify each catalog field must define allowed values."""

    catalog_data = _minimal_catalog_data()
    catalog_data["fields"]["companies"]["values"] = {}

    with pytest.raises(ValidationError, match="at least one value"):
        CanonicalCatalog.model_validate(catalog_data)


def test_validate_canonical_values_rejects_out_of_catalog_value() -> None:
    """Verify runtime canonical validation rejects unknown canonical IDs."""

    catalog = CanonicalCatalog.model_validate(_minimal_catalog_data())

    with pytest.raises(ValueError, match="not allowed"):
        validate_canonical_values(
            catalog=catalog,
            field="companies",
            canonical_values=["unknown_company"],
        )


def test_validate_canonical_values_accepts_null_values() -> None:
    """Verify null canonical values are accepted as valid unmapped outputs."""

    catalog = CanonicalCatalog.model_validate(_minimal_catalog_data())

    validate_canonical_values(
        catalog=catalog,
        field="companies",
        canonical_values=["companies_value", None],
    )


def _minimal_catalog_data() -> dict[str, object]:
    """Build a minimal valid catalog for tests.

    Returns:
        dict[str, object]: Catalog data with one canonical value per supported
        field.
    """

    fields = {}
    for field in CANONICAL_FIELDS:
        fields[field] = {
            "description": f"{field} field",
            "values": {
                f"{field}_value": {
                    "label": f"{field} value",
                    "aliases": [field],
                    "related_terms": [],
                    "law_or_regime_aliases": [],
                    "exclude": [],
                    "description": f"{field} description",
                }
            },
        }

    return {"version": 1, "fields": copy.deepcopy(fields)}
