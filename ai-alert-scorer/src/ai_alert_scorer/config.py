"""Runtime configuration for the alert relevance chat application."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from ai_alert_scorer.date_ranges import AlertDateRangeError, parse_as_of_datetime

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CANONICAL_ALERTS_PATH = (
    REPOSITORY_ROOT / "etl" / "data" / "processed" / "canonicalized_alerts.json"
)
DEFAULT_CANONICAL_CLIENT_PROFILE_PATH = (
    REPOSITORY_ROOT
    / "etl"
    / "data"
    / "processed"
    / "canonicalized_client_profile.json"
)
DEFAULT_TOP_N = 5
ALERT_RELEVANCE_MODEL_ENV = "ALERT_RELEVANCE_MODEL"
ALERT_RELEVANCE_TEMPERATURE_ENV = "ALERT_RELEVANCE_TEMPERATURE"
ALERT_RELEVANCE_REASONING_EFFORT_ENV = "ALERT_RELEVANCE_REASONING_EFFORT"
ALERT_RELEVANCE_REASONING_SUMMARY_ENV = "ALERT_RELEVANCE_REASONING_SUMMARY"


@dataclass(frozen=True)
class AlertRelevanceConfig:
    """File and CLI configuration for one alert relevance chat session.

    Attributes:
        canonical_alerts_path (Path): JSON array of canonicalized alert records.
        canonical_client_profile_path (Path): JSON object containing the
            canonicalized client profile.
        top_n (int): Default maximum number of ranked alerts to return.
        as_of (datetime | None): Optional timezone-aware relative-time anchor.
    """

    canonical_alerts_path: Path = DEFAULT_CANONICAL_ALERTS_PATH
    canonical_client_profile_path: Path = DEFAULT_CANONICAL_CLIENT_PROFILE_PATH
    top_n: int = DEFAULT_TOP_N
    as_of: datetime | None = None


@dataclass(frozen=True)
class OpenAIModelConfig:
    """OpenAI chat model configuration for alert relevance conversations.

    Attributes:
        model (str): OpenAI model name or deployment name.
        temperature (float | None): Optional sampling temperature.
        reasoning (Mapping[str, str] | None): Optional OpenAI reasoning
            parameters, such as ``{"effort": "medium", "summary": "auto"}``.
    """

    model: str
    temperature: float | None = None
    reasoning: Mapping[str, str] | None = None


def build_config(
    canonical_alerts_path: Path | str | None = None,
    canonical_client_profile_path: Path | str | None = None,
    top_n: int | str | None = None,
    as_of: str | None = None,
) -> AlertRelevanceConfig:
    """Create alert relevance runtime configuration.

    Args:
        canonical_alerts_path (Path | str | None): Optional canonical alerts
            JSON path. Uses the repository default when omitted.
        canonical_client_profile_path (Path | str | None): Optional canonical
            client profile JSON path. Uses the repository default when omitted.
        top_n (int | str | None): Optional default top-N result count.
        as_of (str | None): Optional ISO date or timezone-aware ISO datetime
            used to anchor relative time phrases.

    Returns:
        AlertRelevanceConfig: Runtime configuration with normalized paths.

    Raises:
        ValueError: If ``top_n`` or ``as_of`` is invalid.
    """

    parsed_top_n = _parse_top_n(top_n)
    parsed_as_of = _parse_as_of(as_of)
    return AlertRelevanceConfig(
        canonical_alerts_path=(
            Path(canonical_alerts_path)
            if canonical_alerts_path is not None
            else DEFAULT_CANONICAL_ALERTS_PATH
        ),
        canonical_client_profile_path=(
            Path(canonical_client_profile_path)
            if canonical_client_profile_path is not None
            else DEFAULT_CANONICAL_CLIENT_PROFILE_PATH
        ),
        top_n=parsed_top_n,
        as_of=parsed_as_of,
    )


def load_openai_model_config(
    env_file: Path | str | None = None,
) -> OpenAIModelConfig:
    """Load alert relevance OpenAI model settings from environment variables.

    Args:
        env_file (Path | str | None): Optional dotenv file loaded before
            reading environment variables.

    Returns:
        OpenAIModelConfig: Model and optional generation settings.

    Raises:
        ValueError: If the required model environment variable is missing or an
            optional numeric value is invalid.
    """

    load_dotenv(dotenv_path=env_file)
    return OpenAIModelConfig(
        model=_read_required_env(ALERT_RELEVANCE_MODEL_ENV),
        temperature=_read_optional_float_env(ALERT_RELEVANCE_TEMPERATURE_ENV),
        reasoning=_read_openai_reasoning(
            effort_env=ALERT_RELEVANCE_REASONING_EFFORT_ENV,
            summary_env=ALERT_RELEVANCE_REASONING_SUMMARY_ENV,
        ),
    )


def _parse_top_n(top_n: int | str | None) -> int:
    """Parse and validate the default result count.

    Args:
        top_n (int | str | None): Optional value from CLI or caller.

    Returns:
        int: Positive result count.

    Raises:
        ValueError: If ``top_n`` is not a positive integer.
    """

    if top_n is None:
        return DEFAULT_TOP_N
    try:
        value = int(top_n)
    except ValueError as exc:
        raise ValueError(f"top_n must be a positive integer: {top_n!r}") from exc
    if value < 1:
        raise ValueError(f"top_n must be a positive integer: {top_n!r}")
    return value


def _parse_as_of(as_of: str | None) -> datetime | None:
    """Parse an optional relative-time anchor.

    Args:
        as_of (str | None): ISO date or timezone-aware ISO datetime.

    Returns:
        datetime | None: Parsed anchor, or ``None`` when omitted.

    Raises:
        ValueError: If ``as_of`` is invalid.
    """

    if as_of is None:
        return None
    try:
        return parse_as_of_datetime(as_of)
    except AlertDateRangeError as exc:
        raise ValueError(str(exc)) from exc


def _read_openai_reasoning(
    effort_env: str,
    summary_env: str,
) -> Mapping[str, str] | None:
    """Read optional OpenAI reasoning settings from environment variables.

    Args:
        effort_env (str): Environment variable containing reasoning effort.
        summary_env (str): Environment variable containing reasoning summary.

    Returns:
        Mapping[str, str] | None: Reasoning settings, or ``None`` when absent.
    """

    reasoning: dict[str, str] = {}
    effort = os.getenv(effort_env)
    summary = os.getenv(summary_env)
    if effort:
        reasoning["effort"] = effort
    if summary:
        reasoning["summary"] = summary
    return reasoning or None


def _read_required_env(name: str) -> str:
    """Read a required environment variable.

    Args:
        name (str): Environment variable name.

    Returns:
        str: Non-empty environment variable value.

    Raises:
        ValueError: If the environment variable is missing or empty.
    """

    value = os.getenv(name)
    if value:
        return value
    raise ValueError(f"Missing required environment variable: {name}")


def _read_optional_float_env(name: str) -> float | None:
    """Read an optional float environment variable.

    Args:
        name (str): Environment variable name.

    Returns:
        float | None: Parsed value, or ``None`` when unset.

    Raises:
        ValueError: If the environment variable is present but not a float.
    """

    value = os.getenv(name)
    if not value:
        return None
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(
            f"Environment variable {name} must be a float: {value!r}"
        ) from exc


__all__ = [
    "ALERT_RELEVANCE_MODEL_ENV",
    "ALERT_RELEVANCE_REASONING_EFFORT_ENV",
    "ALERT_RELEVANCE_REASONING_SUMMARY_ENV",
    "ALERT_RELEVANCE_TEMPERATURE_ENV",
    "AlertRelevanceConfig",
    "DEFAULT_CANONICAL_ALERTS_PATH",
    "DEFAULT_CANONICAL_CLIENT_PROFILE_PATH",
    "DEFAULT_TOP_N",
    "OpenAIModelConfig",
    "build_config",
    "load_openai_model_config",
]
