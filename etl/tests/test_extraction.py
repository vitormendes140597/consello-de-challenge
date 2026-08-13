"""Tests for LangChain/OpenAI extraction orchestration."""

from collections.abc import Mapping

from etl.common import openai as openai_model
from etl.common.config import OpenAIModelConfig
from etl.common.schemas import AlertMetadata, RawAlert
from etl.extraction import model as extraction


def test_create_openai_model_uses_provided_config(monkeypatch) -> None:
    """Verify OpenAI model construction uses explicit model settings."""

    captured_kwargs = {}

    class FakeChatOpenAI:
        """Fake ChatOpenAI constructor used to inspect configuration."""

        def __init__(self, **kwargs: object) -> None:
            captured_kwargs.update(kwargs)

    monkeypatch.setattr(openai_model, "ChatOpenAI", FakeChatOpenAI)

    openai_model.create_openai_model(
        OpenAIModelConfig(model="custom-extractor", temperature=0.1),
    )

    assert captured_kwargs == {
        "model": "custom-extractor",
        "temperature": 0.1,
    }


def test_create_openai_model_omits_missing_optional_config(monkeypatch) -> None:
    """Verify optional OpenAI model settings are omitted when not configured."""

    captured_kwargs = {}

    class FakeChatOpenAI:
        """Fake ChatOpenAI constructor used to inspect configuration."""

        def __init__(self, **kwargs: object) -> None:
            captured_kwargs.update(kwargs)

    monkeypatch.setattr(openai_model, "ChatOpenAI", FakeChatOpenAI)

    openai_model.create_openai_model(OpenAIModelConfig(model="custom-extractor"))

    assert captured_kwargs == {"model": "custom-extractor"}


def test_create_openai_model_passes_reasoning_when_configured(monkeypatch) -> None:
    """Verify OpenAI reasoning settings are passed through to ChatOpenAI."""

    captured_kwargs = {}

    class FakeChatOpenAI:
        """Fake ChatOpenAI constructor used to inspect reasoning config."""

        def __init__(self, **kwargs: object) -> None:
            captured_kwargs.update(kwargs)

    monkeypatch.setattr(openai_model, "ChatOpenAI", FakeChatOpenAI)

    openai_model.create_openai_model(
        OpenAIModelConfig(
            model="custom-extractor",
            temperature=0.1,
            reasoning={"effort": "medium", "summary": "auto"},
        ),
    )

    assert captured_kwargs == {
        "model": "custom-extractor",
        "temperature": 0.1,
        "reasoning": {"effort": "medium", "summary": "auto"},
    }


def test_extract_alert_metadata_uses_schema_and_prompt() -> None:
    """Verify extraction binds the metadata schema and invokes the synthesis prompt."""

    structured_model = FakeStructuredMetadataModel(
        AlertMetadata(
            companies=[
                {
                    "name": "solstice robotics",
                    "ticker": "slrb",
                    "rationale": "The alert names Solstice Robotics.",
                }
            ],
        )
    )
    model = FakeStructuredOutputModel(structured_model)
    alert = RawAlert(
        id="a01",
        received_at="2026-08-11T09:00:00+00:00",
        subject="Solstice reports earnings",
        body="Solstice Robotics reported warehouse automation demand.",
    )

    metadata = extraction.extract_alert_metadata(
        alert=alert,
        model=model,
        context_hints={"focal_companies": ["Solstice Robotics"]},
    )

    assert model.schema is AlertMetadata
    assert "<news>" in structured_model.prompt
    assert "Solstice reports earnings" in structured_model.prompt
    assert "<context_hints>" in structured_model.prompt
    assert metadata.companies[0].name == "solstice robotics"


def test_extract_alert_metadata_validates_mapping_response() -> None:
    """Verify mapping responses are validated into AlertMetadata."""

    structured_model = FakeStructuredMetadataModel(
        {
            "themes": [
                {
                    "name": "warehouse automation",
                    "rationale": "The alert cites warehouse automation demand.",
                }
            ]
        }
    )
    model = FakeStructuredOutputModel(structured_model)
    alert = RawAlert(
        id="a01",
        received_at="2026-08-11T09:00:00+00:00",
        subject="Solstice reports earnings",
        body="Solstice Robotics reported warehouse automation demand.",
    )

    metadata = extraction.extract_alert_metadata(alert=alert, model=model)

    assert metadata.themes[0].name == "warehouse automation"


class FakeStructuredMetadataModel:
    """Fake structured runnable that records the prompt it receives."""

    def __init__(
        self,
        response: AlertMetadata | Mapping[str, object],
    ) -> None:
        """Store the fake structured response."""

        self.response = response
        self.prompt = ""

    def invoke(self, prompt: str) -> AlertMetadata | Mapping[str, object]:
        """Record the prompt and return the fake response."""

        self.prompt = prompt
        return self.response


class FakeStructuredOutputModel:
    """Fake chat model that records the requested structured schema."""

    def __init__(self, structured_model: FakeStructuredMetadataModel) -> None:
        """Store the fake structured model returned by schema binding."""

        self.structured_model = structured_model
        self.schema: type[AlertMetadata] | None = None

    def with_structured_output(
        self,
        schema: type[AlertMetadata],
    ) -> FakeStructuredMetadataModel:
        """Record the schema and return the fake structured model."""

        self.schema = schema
        return self.structured_model
