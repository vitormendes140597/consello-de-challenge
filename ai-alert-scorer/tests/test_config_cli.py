"""Tests for alert relevance configuration and CLI argument handling."""

from pathlib import Path

import pytest

from ai_alert_scorer import config as scorer_config
from ai_alert_scorer.app import cli
from ai_alert_scorer.config import (
    DEFAULT_CANONICAL_ALERTS_PATH,
    DEFAULT_CANONICAL_CLIENT_PROFILE_PATH,
    DEFAULT_TOP_N,
    build_config,
)


def test_build_config_uses_default_values() -> None:
    """Verify omitted runtime settings resolve to scorer defaults."""

    config = build_config()

    assert config.canonical_alerts_path == DEFAULT_CANONICAL_ALERTS_PATH
    assert config.canonical_client_profile_path == DEFAULT_CANONICAL_CLIENT_PROFILE_PATH
    assert config.top_n == DEFAULT_TOP_N


def test_build_config_accepts_custom_values() -> None:
    """Verify explicit runtime settings are normalized."""

    config = build_config(
        canonical_alerts_path="processed/alerts.json",
        canonical_client_profile_path=Path("processed/client.json"),
        top_n="3",
        as_of="2026-08-11",
    )

    assert config.canonical_alerts_path == Path("processed/alerts.json")
    assert config.canonical_client_profile_path == Path("processed/client.json")
    assert config.top_n == 3
    assert config.as_of is not None
    assert config.as_of.isoformat() == "2026-08-11T12:00:00+00:00"


@pytest.mark.parametrize("top_n", ["0", "-1", "many"])
def test_build_config_rejects_invalid_top_n(top_n: str) -> None:
    """Verify the default result count must be a positive integer."""

    with pytest.raises(ValueError, match="top_n"):
        build_config(top_n=top_n)


def test_build_config_rejects_invalid_as_of() -> None:
    """Verify relative-time anchors must be valid ISO dates or datetimes."""

    with pytest.raises(ValueError, match="as_of"):
        build_config(as_of="August 11")


def test_parse_args_accepts_chat_options() -> None:
    """Verify CLI parsing accepts initial chat configuration options."""

    args = cli.parse_args(
        [
            "--canonical-alerts-path",
            "processed/alerts.json",
            "--canonical-client-profile-path",
            "processed/client.json",
            "--top-n",
            "4",
            "--as-of",
            "2026-08-11T09:30:00Z",
        ]
    )

    assert args.canonical_alerts_path == "processed/alerts.json"
    assert args.canonical_client_profile_path == "processed/client.json"
    assert args.top_n == "4"
    assert args.as_of == "2026-08-11T09:30:00Z"


def test_build_config_from_args_returns_runtime_config() -> None:
    """Verify parsed CLI arguments are converted into runtime config."""

    args = cli.parse_args(
        [
            "--canonical-alerts-path",
            "processed/alerts.json",
            "--canonical-client-profile-path",
            "processed/client.json",
            "--top-n",
            "2",
            "--as-of",
            "2026-08-11",
        ]
    )

    config = cli.build_config_from_args(args)

    assert config.canonical_alerts_path == Path("processed/alerts.json")
    assert config.canonical_client_profile_path == Path("processed/client.json")
    assert config.top_n == 2
    assert config.as_of is not None
    assert config.as_of.isoformat() == "2026-08-11T12:00:00+00:00"


def test_openai_model_config_requires_model_env(monkeypatch) -> None:
    """Verify the alert relevance model name must be configured."""

    monkeypatch.setattr(scorer_config, "load_dotenv", lambda dotenv_path=None: None)
    monkeypatch.delenv(scorer_config.ALERT_RELEVANCE_MODEL_ENV, raising=False)

    with pytest.raises(ValueError, match=scorer_config.ALERT_RELEVANCE_MODEL_ENV):
        scorer_config.load_openai_model_config()


def test_openai_model_config_loads_optional_values(monkeypatch) -> None:
    """Verify alert relevance model config reads optional model settings."""

    monkeypatch.setattr(scorer_config, "load_dotenv", lambda dotenv_path=None: None)
    monkeypatch.setenv(scorer_config.ALERT_RELEVANCE_MODEL_ENV, "gpt-test")
    monkeypatch.setenv(scorer_config.ALERT_RELEVANCE_TEMPERATURE_ENV, "0.1")
    monkeypatch.setenv(scorer_config.ALERT_RELEVANCE_REASONING_EFFORT_ENV, "medium")
    monkeypatch.setenv(scorer_config.ALERT_RELEVANCE_REASONING_SUMMARY_ENV, "auto")

    config = scorer_config.load_openai_model_config()

    assert config.model == "gpt-test"
    assert config.temperature == 0.1
    assert config.reasoning == {"effort": "medium", "summary": "auto"}


def test_openai_model_config_rejects_invalid_temperature(monkeypatch) -> None:
    """Verify the optional temperature must be a float."""

    monkeypatch.setattr(scorer_config, "load_dotenv", lambda dotenv_path=None: None)
    monkeypatch.setenv(scorer_config.ALERT_RELEVANCE_MODEL_ENV, "gpt-test")
    monkeypatch.setenv(scorer_config.ALERT_RELEVANCE_TEMPERATURE_ENV, "low")

    with pytest.raises(ValueError, match=scorer_config.ALERT_RELEVANCE_TEMPERATURE_ENV):
        scorer_config.load_openai_model_config()
