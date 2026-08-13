"""OpenAI chat model construction shared by ETL model callers."""

from __future__ import annotations

from langchain_openai import ChatOpenAI

from etl.common.config import OpenAIModelConfig


def create_openai_model(
    config: OpenAIModelConfig,
) -> ChatOpenAI:
    """Create a LangChain OpenAI chat model from ETL configuration.

    Args:
        config (OpenAIModelConfig): Model configuration loaded from the ETL
            configuration layer.

    Returns:
        ChatOpenAI: Configured LangChain OpenAI chat model.
    """

    kwargs: dict[str, object] = {"model": config.model}
    if config.temperature is not None:
        kwargs["temperature"] = config.temperature
    if config.reasoning:
        kwargs["reasoning"] = dict(config.reasoning)

    return ChatOpenAI(**kwargs)


__all__ = [
    "create_openai_model",
]
