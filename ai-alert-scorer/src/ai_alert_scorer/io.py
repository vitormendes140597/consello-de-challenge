"""JSON loading boundaries for canonical alert relevance data."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path

from ai_alert_scorer.date_ranges import AlertDateRange, filter_alerts_by_date_range
from ai_alert_scorer.schemas import (
    CanonicalizedAlert,
    CanonicalizedClientProfile,
)


class CanonicalDataLoadError(ValueError):
    """Raised when canonical relevance input data cannot be loaded."""


@dataclass(frozen=True)
class CanonicalDataLoader:
    """Loader for canonical alerts and client profile JSON artifacts."""

    def iter_alerts(self, path: Path | str) -> Iterator[CanonicalizedAlert]:
        """Yield validated canonicalized alerts from a JSON array file.

        Args:
            path (Path | str): File path containing canonicalized alerts.

        Yields:
            CanonicalizedAlert: Validated alert records.

        Raises:
            CanonicalDataLoadError: If the file is missing, malformed, has an
                invalid JSON root, or contains invalid alert records.
        """

        data = _read_json(path)
        if not isinstance(data, list):
            raise CanonicalDataLoadError(
                f"Canonical alerts file must contain a JSON array: {path}"
            )

        for index, record in enumerate(data):
            if not isinstance(record, Mapping):
                raise CanonicalDataLoadError(
                    f"Canonical alert at index {index} must be a JSON object"
                )
            try:
                yield CanonicalizedAlert.model_validate(record)
            except ValueError as exc:
                raise CanonicalDataLoadError(
                    f"Canonical alert at index {index} is invalid: {exc}"
                ) from exc

    def load_alerts(self, path: Path | str) -> list[CanonicalizedAlert]:
        """Load validated canonicalized alerts from a JSON array file.

        Args:
            path (Path | str): File path containing canonicalized alerts.

        Returns:
            list[CanonicalizedAlert]: Validated canonical alert records.

        Raises:
            CanonicalDataLoadError: If the file cannot be loaded or validated.
        """

        return list(self.iter_alerts(path))

    def load_alerts_for_date_range(
        self,
        path: Path | str,
        date_range: AlertDateRange,
    ) -> list[CanonicalizedAlert]:
        """Load canonicalized alerts filtered by an absolute date range.

        Args:
            path (Path | str): File path containing canonicalized alerts.
            date_range (AlertDateRange): Inclusive absolute date range.

        Returns:
            list[CanonicalizedAlert]: Validated and filtered alert records.

        Raises:
            CanonicalDataLoadError: If the file cannot be loaded or validated.
        """

        return filter_alerts_by_date_range(
            alerts=self.load_alerts(path),
            date_range=date_range,
        )

    def load_client_profile(
        self,
        path: Path | str,
    ) -> CanonicalizedClientProfile:
        """Load a validated canonicalized client profile from a JSON object.

        Args:
            path (Path | str): File path containing the canonical client profile.

        Returns:
            CanonicalizedClientProfile: Validated client profile.

        Raises:
            CanonicalDataLoadError: If the file cannot be loaded or validated.
        """

        data = _read_json(path)
        if not isinstance(data, Mapping):
            raise CanonicalDataLoadError(
                f"Canonical client profile file must contain a JSON object: {path}"
            )

        try:
            return CanonicalizedClientProfile.model_validate(data)
        except ValueError as exc:
            raise CanonicalDataLoadError(
                f"Canonical client profile is invalid: {exc}"
            ) from exc


def _read_json(path: Path | str) -> object:
    """Read and decode a JSON file.

    Args:
        path (Path | str): JSON file path.

    Returns:
        object: Decoded JSON value.

    Raises:
        CanonicalDataLoadError: If the file is missing, unreadable, or malformed.
    """

    input_path = Path(path)
    try:
        with input_path.open(encoding="utf-8") as input_file:
            return json.load(input_file)
    except FileNotFoundError as exc:
        raise CanonicalDataLoadError(f"Canonical data file not found: {path}") from exc
    except OSError as exc:
        raise CanonicalDataLoadError(
            f"Unable to read canonical data file {path}: {exc}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise CanonicalDataLoadError(
            f"Canonical data file is not valid JSON {path}: {exc.msg}"
        ) from exc


__all__ = [
    "CanonicalDataLoadError",
    "CanonicalDataLoader",
]
