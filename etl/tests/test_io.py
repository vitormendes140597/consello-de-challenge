"""Tests for ETL JSON IO helpers."""

import json

import pytest
from pydantic import ValidationError

from etl.common.io import AlertDataLoader, JsonRecordStore
from etl.common.schemas import EnrichedAlert


def test_alert_data_loader_load_raw_alerts_validates_json_array(tmp_path) -> None:
    """Verify raw alerts are loaded and validated from a JSON array."""

    input_path = tmp_path / "alerts.json"
    input_path.write_text(
        json.dumps(
            [
                {
                    "id": "a01",
                    "received_at": "2026-08-11T09:00:00+00:00",
                    "subject": "Solstice reports earnings",
                    "body": "Solstice Robotics reported demand growth.",
                }
            ]
        ),
        encoding="utf-8",
    )
    loader = AlertDataLoader()

    alerts = loader.load_raw_alerts(input_path)

    assert len(alerts) == 1
    assert alerts[0].id == "a01"


def test_alert_data_loader_load_raw_alerts_rejects_missing_source_fields(
    tmp_path,
) -> None:
    """Verify invalid raw alerts fail validation at load time."""

    input_path = tmp_path / "alerts.json"
    input_path.write_text(
        json.dumps(
            [
                {
                    "id": "a01",
                    "received_at": "2026-08-11T09:00:00+00:00",
                    "subject": "Solstice reports earnings",
                }
            ]
        ),
        encoding="utf-8",
    )
    loader = AlertDataLoader()

    with pytest.raises(ValidationError):
        loader.load_raw_alerts(input_path)


def test_alert_data_loader_load_enriched_alerts_validates_json_array(tmp_path) -> None:
    """Verify enriched alerts are loaded and validated from a JSON array."""

    input_path = tmp_path / "enriched_alerts.json"
    input_path.write_text(
        json.dumps(
            [
                {
                    "id": "a01",
                    "received_at": "2026-08-11T09:00:00+00:00",
                    "subject": "Solstice reports earnings",
                    "body": "Solstice Robotics reported demand growth.",
                    "companies": [
                        {
                            "name": "Solstice Robotics",
                            "ticker": "SLRB",
                            "rationale": "The source names Solstice Robotics.",
                        }
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    loader = AlertDataLoader()

    alerts = loader.load_enriched_alerts(input_path)

    assert len(alerts) == 1
    assert alerts[0].id == "a01"
    assert alerts[0].companies[0].ticker == "SLRB"


def test_alert_data_loader_load_client_profile_context_requires_json_object(
    tmp_path,
) -> None:
    """Verify client profile context is loaded as a JSON object."""

    input_path = tmp_path / "client_profile.json"
    input_path.write_text(
        json.dumps({"focal_companies": ["Solstice Robotics"]}),
        encoding="utf-8",
    )
    loader = AlertDataLoader()

    context = loader.load_client_profile_context(input_path)

    assert context == {"focal_companies": ["Solstice Robotics"]}


def test_json_record_store_creates_missing_file_from_mapping_records(tmp_path) -> None:
    """Verify the JSON record store creates a missing JSON array file."""

    output_path = tmp_path / "processed" / "records.json"
    store = JsonRecordStore(path=output_path)

    merged = store.merge_records(
        [
            {
                "id": "a01",
                "subject": "Solstice reports earnings",
            }
        ]
    )

    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert merged == [{"id": "a01", "subject": "Solstice reports earnings"}]
    assert written == merged


def test_json_record_store_replaces_matching_ids_and_preserves_others(
    tmp_path,
) -> None:
    """Verify merge-by-id replaces matches, preserves others, and appends new ids."""

    output_path = tmp_path / "records.json"
    output_path.write_text(
        json.dumps(
            [
                {"id": "a01", "subject": "Old alert"},
                {"id": "a02", "subject": "Preserved alert"},
                {"subject": "Record without id"},
            ]
        ),
        encoding="utf-8",
    )
    store = JsonRecordStore(path=output_path)

    merged = store.merge_records(
        [
            {"id": "a01", "subject": "Updated alert"},
            {"id": "a03", "subject": "New alert"},
        ]
    )

    assert merged == [
        {"id": "a01", "subject": "Updated alert"},
        {"id": "a02", "subject": "Preserved alert"},
        {"subject": "Record without id"},
        {"id": "a03", "subject": "New alert"},
    ]


def test_json_record_store_serializes_pydantic_records(tmp_path) -> None:
    """Verify the JSON record store accepts Pydantic model records."""

    output_path = tmp_path / "records.json"
    store = JsonRecordStore(path=output_path)
    alert = EnrichedAlert(
        id="a01",
        received_at="2026-08-11T09:00:00+00:00",
        subject="Solstice reports earnings",
        body="Solstice Robotics reported demand growth.",
    )

    merged = store.merge_records([alert])

    assert merged[0]["id"] == "a01"
    assert merged[0]["companies"] == []


def test_json_record_store_uses_configurable_id_field(tmp_path) -> None:
    """Verify the JSON record store can merge on a custom id field."""

    output_path = tmp_path / "records.json"
    output_path.write_text(
        json.dumps([{"key": "a01", "subject": "Old alert"}]),
        encoding="utf-8",
    )
    store = JsonRecordStore(path=output_path, id_field="key")

    merged = store.merge_records([{"key": "a01", "subject": "Updated alert"}])

    assert merged == [{"key": "a01", "subject": "Updated alert"}]
