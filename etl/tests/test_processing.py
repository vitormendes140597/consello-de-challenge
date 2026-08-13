"""Tests for alert extraction ETL processing orchestration."""

from __future__ import annotations

import json
from collections.abc import Mapping

import pytest
from pydantic import ValidationError

from etl.common.config import ETLConfig
from etl.common.schemas import AlertMetadata, RawAlert
from etl.extraction.processing import enrich_alert, run_alert_extraction_etl


def test_enrich_alert_preserves_source_fields_and_normalizes_metadata() -> None:
    """Verify one alert is enriched with preserved source and normalized metadata."""

    alert = RawAlert(
        id="a01",
        received_at="2026-08-11T09:00:00+00:00",
        subject="Solstice reports earnings",
        body="Solstice Robotics reported warehouse automation demand.",
    )
    model = FakeStructuredOutputModel(
        [
            AlertMetadata(
                companies=[
                    {
                        "name": "Solstice Robotics",
                        "ticker": "SLRB",
                        "rationale": "The alert names Solstice Robotics.",
                    },
                    {
                        "name": "solstice robotics",
                        "ticker": "slrb",
                        "rationale": "Duplicate mention.",
                    },
                ],
                key_markets=[
                    {
                        "name": "Warehouse Automation",
                        "rationale": "The body cites warehouse automation demand.",
                    },
                    {
                        "name": "warehouse automation",
                        "rationale": "Duplicate market.",
                    },
                ],
            )
        ]
    )

    enriched = enrich_alert(
        alert=alert,
        model=model,
        context_hints={"focal_companies": ["Solstice Robotics"]},
    )

    assert enriched.id == alert.id
    assert enriched.received_at == alert.received_at
    assert enriched.subject == alert.subject
    assert enriched.body == alert.body
    assert [company.name for company in enriched.companies] == ["solstice robotics"]
    assert enriched.companies[0].ticker == "slrb"
    assert [item.name for item in enriched.key_markets] == ["warehouse automation"]
    assert "Solstice Robotics" in model.prompts[0]


def test_run_alert_extraction_etl_writes_one_output_per_input(tmp_path) -> None:
    """Verify the ETL loads, enriches, and writes an output array."""

    input_path = tmp_path / "raw" / "alerts.json"
    client_profile_path = tmp_path / "raw" / "client_profile.json"
    output_path = tmp_path / "processed" / "enriched_alerts.json"
    input_path.parent.mkdir(parents=True)
    input_path.write_text(
        json.dumps(
            [
                {
                    "id": "a01",
                    "received_at": "2026-08-11T09:00:00+00:00",
                    "subject": "Solstice reports earnings",
                    "body": "Solstice Robotics reported demand growth.",
                },
                {
                    "id": "a02",
                    "received_at": "2026-08-10T09:00:00+00:00",
                    "subject": "Solstice names CFO",
                    "body": "Solstice Robotics named a new CFO.",
                },
            ]
        ),
        encoding="utf-8",
    )
    client_profile_path.write_text(
        json.dumps({"focal_companies": ["Solstice Robotics"]}),
        encoding="utf-8",
    )
    model = FakeStructuredOutputModel(
        [
            AlertMetadata(companies=[]),
            AlertMetadata(themes=[{"name": "Leadership Change", "rationale": "CFO"}]),
        ]
    )

    enriched_alerts = run_alert_extraction_etl(
        config=ETLConfig(
            input_path=input_path,
            client_profile_path=client_profile_path,
            output_path=output_path,
        ),
        model=model,
    )

    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert len(enriched_alerts) == 2
    assert len(written) == 2
    assert written[0]["id"] == "a01"
    assert written[1]["themes"][0]["name"] == "leadership change"


def test_run_alert_extraction_etl_validates_alerts_before_model_call(tmp_path) -> None:
    """Verify invalid raw alerts stop processing before extraction is invoked."""

    input_path = tmp_path / "alerts.json"
    client_profile_path = tmp_path / "client_profile.json"
    output_path = tmp_path / "enriched_alerts.json"
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
    client_profile_path.write_text("{}", encoding="utf-8")
    model = FakeStructuredOutputModel([AlertMetadata()])

    with pytest.raises(ValidationError):
        run_alert_extraction_etl(
            config=ETLConfig(
                input_path=input_path,
                client_profile_path=client_profile_path,
                output_path=output_path,
            ),
            model=model,
        )

    assert model.prompts == []
    assert not output_path.exists()


class FakeStructuredMetadataModel:
    """Fake structured runnable that returns queued metadata responses."""

    def __init__(self, responses: list[AlertMetadata | Mapping[str, object]]) -> None:
        """Store queued fake extraction responses.

        Args:
            responses (list[AlertMetadata | Mapping[str, object]]): Responses
                returned by sequential invocations.
        """

        self.responses = responses
        self.prompts: list[str] = []

    def invoke(self, prompt: str) -> AlertMetadata | Mapping[str, object]:
        """Record the prompt and return the next queued response.

        Args:
            prompt (str): Prompt sent by the extraction pipeline.

        Returns:
            AlertMetadata | Mapping[str, object]: Next fake extraction response.
        """

        self.prompts.append(prompt)
        return self.responses.pop(0)


class FakeStructuredOutputModel:
    """Fake chat model that records structured extraction prompts."""

    def __init__(self, responses: list[AlertMetadata | Mapping[str, object]]) -> None:
        """Store fake responses for the structured runnable.

        Args:
            responses (list[AlertMetadata | Mapping[str, object]]): Responses
                returned by sequential extraction invocations.
        """

        self.structured_model = FakeStructuredMetadataModel(responses)

    @property
    def prompts(self) -> list[str]:
        """Return prompts recorded by the structured runnable.

        Returns:
            list[str]: Prompt history.
        """

        return self.structured_model.prompts

    def with_structured_output(
        self,
        schema: type[AlertMetadata],
    ) -> FakeStructuredMetadataModel:
        """Return the fake structured runnable.

        Args:
            schema (type[AlertMetadata]): Requested structured output schema.

        Returns:
            FakeStructuredMetadataModel: Runnable used by the pipeline.
        """

        return self.structured_model
