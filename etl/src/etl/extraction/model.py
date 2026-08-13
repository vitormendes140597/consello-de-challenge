"""LangChain/OpenAI extraction orchestration for alert metadata."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from etl.common.schemas import AlertMetadata, RawAlert
from etl.extraction.prompts import build_synthesis_prompt


class StructuredMetadataModel(Protocol):
    """Model runnable that returns structured alert metadata."""

    def invoke(self, prompt: str) -> AlertMetadata | Mapping[str, object]:
        """Invoke the model with one extraction prompt.

        Args:
            prompt (str): Model-facing prompt for one raw alert.

        Returns:
            AlertMetadata | Mapping[str, object]: Structured metadata returned
            by the model.
        """


class StructuredOutputModel(Protocol):
    """Chat model that can be bound to a structured output schema."""

    def with_structured_output(
        self,
        schema: type[AlertMetadata],
    ) -> StructuredMetadataModel:
        """Bind the model to a Pydantic structured output schema.

        Args:
            schema (type[AlertMetadata]): Pydantic schema that defines the
                expected model output.

        Returns:
            StructuredMetadataModel: Runnable that validates output against the
            provided schema.
        """


def build_metadata_extractor(
    model: StructuredOutputModel,
) -> StructuredMetadataModel:
    """Bind a chat model to the alert metadata structured output schema.

    Args:
        model (StructuredOutputModel): Chat model that supports LangChain
            structured output binding.

    Returns:
        StructuredMetadataModel: Runnable extractor for ``AlertMetadata``.
    """

    return model.with_structured_output(AlertMetadata)


def extract_alert_metadata(
    alert: RawAlert,
    model: StructuredOutputModel,
    context_hints: Mapping[str, object] | None = None,
) -> AlertMetadata:
    """Extract structured metadata for one raw alert.

    Args:
        alert (RawAlert): Source alert containing subject and body text.
        model (StructuredOutputModel): Chat model used for structured
            extraction.
        context_hints (Mapping[str, object] | None): Optional client profile
            context values to include in the extraction prompt.

    Returns:
        AlertMetadata: Validated first-pass metadata extracted from the alert.

    Raises:
        pydantic.ValidationError: If a mapping response cannot be validated as
            ``AlertMetadata``.
    """

    prompt = build_synthesis_prompt(
        subject=alert.subject,
        body=alert.body,
        context_hints=context_hints,
    )
    result = build_metadata_extractor(model).invoke(prompt)

    if isinstance(result, AlertMetadata):
        return result
    return AlertMetadata.model_validate(result)


__all__ = [
    "StructuredMetadataModel",
    "StructuredOutputModel",
    "build_metadata_extractor",
    "extract_alert_metadata",
]
