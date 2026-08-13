"""Canonical catalog loading and validation helpers."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from etl.canonicalization.schemas import CanonicalCatalog
from etl.common.config import DEFAULT_CANONICAL_CATALOG_PATH
from etl.common.io import StorageBackend


def load_canonical_catalog(
    path: Path | str = DEFAULT_CANONICAL_CATALOG_PATH,
    storage: StorageBackend | None = None,
) -> CanonicalCatalog:
    """Load and validate the configured canonical catalog.

    Args:
        path (Path | str): JSON catalog path to read.
        storage (StorageBackend | None): Optional storage backend used for JSON
            file access. A default backend is created when omitted.

    Returns:
        CanonicalCatalog: Validated catalog configuration.

    Raises:
        OSError: If the catalog file cannot be read.
        json.JSONDecodeError: If the catalog file is not valid JSON.
        pydantic.ValidationError: If the decoded catalog does not match the
            catalog schema.
    """

    backend = storage or StorageBackend()
    return CanonicalCatalog.model_validate(backend.read_json(path))


def validate_canonical_values(
    catalog: CanonicalCatalog,
    field: str,
    canonical_values: Iterable[str | None],
) -> None:
    """Validate non-null canonical values are allowed for one catalog field.

    Args:
        catalog (CanonicalCatalog): Catalog defining allowed field values.
        field (str): Canonical field name to validate against.
        canonical_values (Iterable[str | None]): Canonical values emitted for
            the field. Null values are accepted.

    Returns:
        None: The function raises on invalid values.

    Raises:
        ValueError: If ``field`` does not exist or a non-null canonical value is
            not configured for that field.
    """

    allowed_values = catalog.allowed_values(field)
    for canonical in canonical_values:
        if canonical is None or canonical in allowed_values:
            continue
        raise ValueError(
            f"Canonical value {canonical!r} is not allowed for field {field!r}"
        )


__all__ = [
    "load_canonical_catalog",
    "validate_canonical_values",
]
