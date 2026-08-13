"""Tests for canonical alert relevance JSON loading."""

import json

import pytest

from ai_alert_scorer.date_ranges import build_alert_date_range
from ai_alert_scorer.io import CanonicalDataLoader, CanonicalDataLoadError


def _valid_alert_record() -> dict[str, object]:
    """Build a valid canonicalized alert record for tests.

    Returns:
        dict[str, object]: Canonicalized alert JSON record.
    """

    return {
        "id": "a01",
        "received_at": "2026-08-11T09:00:00+00:00",
        "subject": "Solstice Robotics Beats Q2 Estimates",
        "body": "Solstice Robotics (SLRB) reported strong demand.",
        "companies": [
            {
                "name": "solstice robotics",
                "ticker": "slrb",
                "canonical": "solstice_robotics",
                "rationale": "The alert clearly names Solstice Robotics.",
            }
        ],
        "sectors": [],
        "geo_markets": [],
        "key_markets": [
            {
                "name": "warehouse automation",
                "canonical": "warehouse_automation",
                "rationale": "The alert cites warehouse automation demand.",
            }
        ],
        "commodities": [],
        "regulators": [],
        "macro_sensitivities": [],
        "themes": [],
    }


def _valid_client_profile_record() -> dict[str, object]:
    """Build a valid canonicalized client profile record for tests.

    Returns:
        dict[str, object]: Canonicalized client profile JSON object.
    """

    return {
        "client_name": "Solstice Robotics",
        "ticker": "SLRB",
        "sector": "industrial_automation",
        "focal_companies": ["solstice_robotics"],
        "competitors": ["kestrel_automation"],
        "suppliers": ["quanta_sensing"],
        "customers": ["northline_logistics"],
        "geo_markets": ["united_states"],
        "key_markets": ["warehouse_automation"],
        "commodities": ["semiconductor_chips"],
        "regulators": ["cfius"],
        "macro_sensitivities": ["interest_rates"],
        "themes": ["ai_driven_automation"],
    }


def test_load_alerts_validates_json_array(tmp_path) -> None:
    """Verify canonicalized alerts are loaded from a JSON array."""

    input_path = tmp_path / "canonicalized_alerts.json"
    input_path.write_text(json.dumps([_valid_alert_record()]), encoding="utf-8")
    loader = CanonicalDataLoader()

    alerts = loader.load_alerts(input_path)

    assert len(alerts) == 1
    assert alerts[0].id == "a01"
    assert alerts[0].companies[0].canonical == "solstice_robotics"
    assert alerts[0].key_markets[0].canonical == "warehouse_automation"


def test_load_alerts_for_date_range_filters_records(tmp_path) -> None:
    """Verify the loader returns only alerts in the requested range."""

    input_path = tmp_path / "canonicalized_alerts.json"
    older = _valid_alert_record()
    older["id"] = "older"
    older["received_at"] = "2026-08-10T09:00:00Z"
    current = _valid_alert_record()
    current["id"] = "current"
    input_path.write_text(json.dumps([older, current]), encoding="utf-8")
    loader = CanonicalDataLoader()
    date_range = build_alert_date_range(
        "2026-08-11T00:00:00Z",
        "2026-08-11T23:59:59Z",
    )

    alerts = loader.load_alerts_for_date_range(input_path, date_range)

    assert [alert.id for alert in alerts] == ["current"]


def test_load_client_profile_validates_json_object(tmp_path) -> None:
    """Verify canonicalized client profile is loaded from a JSON object."""

    input_path = tmp_path / "canonicalized_client_profile.json"
    input_path.write_text(
        json.dumps(_valid_client_profile_record()),
        encoding="utf-8",
    )
    loader = CanonicalDataLoader()

    profile = loader.load_client_profile(input_path)

    assert profile.client_name == "Solstice Robotics"
    assert profile.ticker == "SLRB"
    assert profile.focal_companies == ["solstice_robotics"]


def test_load_alerts_rejects_missing_file(tmp_path) -> None:
    """Verify missing canonical alert files produce actionable errors."""

    loader = CanonicalDataLoader()

    with pytest.raises(CanonicalDataLoadError, match="not found"):
        loader.load_alerts(tmp_path / "missing.json")


def test_load_client_profile_rejects_missing_file(tmp_path) -> None:
    """Verify missing canonical profile files produce actionable errors."""

    loader = CanonicalDataLoader()

    with pytest.raises(CanonicalDataLoadError, match="not found"):
        loader.load_client_profile(tmp_path / "missing.json")


def test_load_alerts_rejects_malformed_json(tmp_path) -> None:
    """Verify malformed canonical alert JSON produces actionable errors."""

    input_path = tmp_path / "canonicalized_alerts.json"
    input_path.write_text("{", encoding="utf-8")
    loader = CanonicalDataLoader()

    with pytest.raises(CanonicalDataLoadError, match="not valid JSON"):
        loader.load_alerts(input_path)


def test_load_client_profile_rejects_malformed_json(tmp_path) -> None:
    """Verify malformed canonical profile JSON produces actionable errors."""

    input_path = tmp_path / "canonicalized_client_profile.json"
    input_path.write_text("{", encoding="utf-8")
    loader = CanonicalDataLoader()

    with pytest.raises(CanonicalDataLoadError, match="not valid JSON"):
        loader.load_client_profile(input_path)


def test_load_alerts_requires_json_array(tmp_path) -> None:
    """Verify canonicalized alerts must be stored as a JSON array."""

    input_path = tmp_path / "canonicalized_alerts.json"
    input_path.write_text(json.dumps({"id": "a01"}), encoding="utf-8")
    loader = CanonicalDataLoader()

    with pytest.raises(CanonicalDataLoadError, match="JSON array"):
        loader.load_alerts(input_path)


def test_load_client_profile_requires_json_object(tmp_path) -> None:
    """Verify canonicalized client profile must be stored as a JSON object."""

    input_path = tmp_path / "canonicalized_client_profile.json"
    input_path.write_text(
        json.dumps([_valid_client_profile_record()]),
        encoding="utf-8",
    )
    loader = CanonicalDataLoader()

    with pytest.raises(CanonicalDataLoadError, match="JSON object"):
        loader.load_client_profile(input_path)


def test_load_alerts_rejects_invalid_record(tmp_path) -> None:
    """Verify invalid canonical alert records fail validation."""

    record = _valid_alert_record()
    del record["subject"]
    input_path = tmp_path / "canonicalized_alerts.json"
    input_path.write_text(json.dumps([record]), encoding="utf-8")
    loader = CanonicalDataLoader()

    with pytest.raises(CanonicalDataLoadError, match="index 0"):
        loader.load_alerts(input_path)


def test_load_client_profile_rejects_invalid_profile(tmp_path) -> None:
    """Verify invalid canonical profile records fail validation."""

    profile = _valid_client_profile_record()
    profile["focal_companies"] = "solstice_robotics"
    input_path = tmp_path / "canonicalized_client_profile.json"
    input_path.write_text(json.dumps(profile), encoding="utf-8")
    loader = CanonicalDataLoader()

    with pytest.raises(CanonicalDataLoadError, match="client profile is invalid"):
        loader.load_client_profile(input_path)
