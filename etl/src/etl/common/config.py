"""Reusable configuration values for ETL processes."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_INPUT_PATH = PROJECT_ROOT / "data" / "raw" / "sample_alerts.json"
DEFAULT_CLIENT_PROFILE_PATH = PROJECT_ROOT / "data" / "raw" / "client_profile.json"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "data" / "processed" / "enriched_alerts.json"
DEFAULT_CANONICALIZATION_INPUT_PATH = DEFAULT_OUTPUT_PATH
DEFAULT_CANONICALIZED_ALERT_OUTPUT_PATH = (
    PROJECT_ROOT / "data" / "processed" / "canonicalized_alerts.json"
)
DEFAULT_CANONICALIZED_PROFILE_OUTPUT_PATH = (
    PROJECT_ROOT / "data" / "processed" / "canonicalized_client_profile.json"
)
DEFAULT_CANONICAL_CATALOG_PATH = (
    PROJECT_ROOT / "data" / "config" / "canonical_catalog.json"
)
DEFAULT_CANONICAL_EMBEDDING_INDEX_PATH = (
    PROJECT_ROOT / "data" / "processed" / "canonical_embedding_index.json"
)
DEFAULT_STANDARD_DATA_EMBEDDING_MODEL = "text-embedding-3-small"
DATA_EXTRACTOR_MODEL_ENV = "DATA_EXTRACTOR_MODEL"
DATA_EXTRACTOR_TEMPERATURE_ENV = "DATA_EXTRACTOR_TEMPERATURE"
DATA_EXTRACTOR_REASONING_EFFORT_ENV = "DATA_EXTRACTOR_REASONING_EFFORT"
DATA_EXTRACTOR_REASONING_SUMMARY_ENV = "DATA_EXTRACTOR_REASONING_SUMMARY"
STANDARD_DATA_MODEL_ENV = "STANDARD_DATA_MODEL"
STANDARD_DATA_TEMPERATURE_ENV = "STANDARD_DATA_TEMPERATURE"
STANDARD_DATA_REASONING_EFFORT_ENV = "STANDARD_DATA_REASONING_EFFORT"
STANDARD_DATA_REASONING_SUMMARY_ENV = "STANDARD_DATA_REASONING_SUMMARY"
STANDARD_DATA_EMBEDDING_MODEL_ENV = "STANDARD_DATA_EMBEDDING_MODEL"


@dataclass(frozen=True)
class ETLConfig:
    """Runtime file path configuration shared by ETL processes.

    Attributes:
        input_path (Path): Raw alerts JSON input file.
        client_profile_path (Path): Client profile JSON context file.
        output_path (Path): Enriched alerts JSON output file.
    """

    input_path: Path = DEFAULT_INPUT_PATH
    client_profile_path: Path = DEFAULT_CLIENT_PROFILE_PATH
    output_path: Path = DEFAULT_OUTPUT_PATH


@dataclass(frozen=True)
class CanonicalizationConfig:
    """Runtime file path configuration for canonicalization processing.

    Attributes:
        input_path (Path): Enriched alerts JSON input file.
        client_profile_path (Path): Client profile JSON input file.
        catalog_path (Path): Canonical catalog JSON configuration file.
        embedding_index_path (Path): Local catalog embedding index/cache path.
        alert_output_path (Path): Canonicalized alerts JSON output file.
        profile_output_path (Path): Canonicalized customer profile JSON output
            file.
    """

    input_path: Path = DEFAULT_CANONICALIZATION_INPUT_PATH
    client_profile_path: Path = DEFAULT_CLIENT_PROFILE_PATH
    catalog_path: Path = DEFAULT_CANONICAL_CATALOG_PATH
    embedding_index_path: Path = DEFAULT_CANONICAL_EMBEDDING_INDEX_PATH
    alert_output_path: Path = DEFAULT_CANONICALIZED_ALERT_OUTPUT_PATH
    profile_output_path: Path = DEFAULT_CANONICALIZED_PROFILE_OUTPUT_PATH


@dataclass(frozen=True)
class OpenAIModelConfig:
    """OpenAI chat model configuration shared by ETL model callers.

    Attributes:
        model (str): OpenAI model name or deployment name.
        temperature (float | None): Optional sampling temperature passed to the
            chat model.
        reasoning (Mapping[str, str] | None): Optional OpenAI reasoning
            parameter, such as ``{"effort": "medium", "summary": "auto"}``.
    """

    model: str
    temperature: float | None = None
    reasoning: Mapping[str, str] | None = None


@dataclass(frozen=True)
class OpenAIEmbeddingConfig:
    """OpenAI embedding model configuration.

    Attributes:
        model (str): OpenAI embedding model name used for catalog similarity
            search.
    """

    model: str = DEFAULT_STANDARD_DATA_EMBEDDING_MODEL


def build_config(
    input_path: Path | str | None = None,
    client_profile_path: Path | str | None = None,
    output_path: Path | str | None = None,
) -> ETLConfig:
    """Create an ETL file path configuration.

    Args:
        input_path (Path | str | None): Optional raw alerts JSON path. Uses the
            project default when omitted.
        client_profile_path (Path | str | None): Optional client profile JSON
            path. Uses the project default when omitted.
        output_path (Path | str | None): Optional enriched alerts JSON path.
            Uses the project default when omitted.

    Returns:
        ETLConfig: Runtime file path configuration with ``Path`` values.
    """

    return ETLConfig(
        input_path=Path(input_path) if input_path is not None else DEFAULT_INPUT_PATH,
        client_profile_path=(
            Path(client_profile_path)
            if client_profile_path is not None
            else DEFAULT_CLIENT_PROFILE_PATH
        ),
        output_path=(
            Path(output_path) if output_path is not None else DEFAULT_OUTPUT_PATH
        ),
    )


def build_canonicalization_config(
    input_path: Path | str | None = None,
    client_profile_path: Path | str | None = None,
    catalog_path: Path | str | None = None,
    embedding_index_path: Path | str | None = None,
    alert_output_path: Path | str | None = None,
    profile_output_path: Path | str | None = None,
) -> CanonicalizationConfig:
    """Create a canonicalization file path configuration.

    Args:
        input_path (Path | str | None): Optional enriched alerts input path.
            Uses the canonicalization input default when omitted.
        client_profile_path (Path | str | None): Optional client profile JSON
            path. Uses the project default when omitted.
        catalog_path (Path | str | None): Optional canonical catalog JSON path.
            Uses the project default when omitted.
        embedding_index_path (Path | str | None): Optional local embedding
            index/cache path. Uses the project default when omitted.
        alert_output_path (Path | str | None): Optional canonicalized alerts
            output path. Uses the project default when omitted.
        profile_output_path (Path | str | None): Optional canonicalized customer
            profile output path. Uses the project default when omitted.

    Returns:
        CanonicalizationConfig: Runtime canonicalization file paths.
    """

    return CanonicalizationConfig(
        input_path=(
            Path(input_path)
            if input_path is not None
            else DEFAULT_CANONICALIZATION_INPUT_PATH
        ),
        client_profile_path=(
            Path(client_profile_path)
            if client_profile_path is not None
            else DEFAULT_CLIENT_PROFILE_PATH
        ),
        catalog_path=(
            Path(catalog_path)
            if catalog_path is not None
            else DEFAULT_CANONICAL_CATALOG_PATH
        ),
        embedding_index_path=(
            Path(embedding_index_path)
            if embedding_index_path is not None
            else DEFAULT_CANONICAL_EMBEDDING_INDEX_PATH
        ),
        alert_output_path=(
            Path(alert_output_path)
            if alert_output_path is not None
            else DEFAULT_CANONICALIZED_ALERT_OUTPUT_PATH
        ),
        profile_output_path=(
            Path(profile_output_path)
            if profile_output_path is not None
            else DEFAULT_CANONICALIZED_PROFILE_OUTPUT_PATH
        ),
    )


def load_data_extractor_model_config(
    env_file: Path | str | None = None,
) -> OpenAIModelConfig:
    """Load the data extractor OpenAI model configuration.

    Args:
        env_file (Path | str | None): Optional dotenv file path loaded before
            reading environment variables.

    Returns:
        OpenAIModelConfig: Model and optional temperature and reasoning settings
        for alert metadata extraction.

    Raises:
        ValueError: If the required model environment variable is missing or an
            optional value is invalid.
    """

    return _load_openai_model_config(
        model_env=DATA_EXTRACTOR_MODEL_ENV,
        temperature_env=DATA_EXTRACTOR_TEMPERATURE_ENV,
        reasoning_effort_env=DATA_EXTRACTOR_REASONING_EFFORT_ENV,
        reasoning_summary_env=DATA_EXTRACTOR_REASONING_SUMMARY_ENV,
        env_file=env_file,
    )


def load_standard_data_model_config(
    env_file: Path | str | None = None,
) -> OpenAIModelConfig:
    """Load the standard data OpenAI model configuration.

    Args:
        env_file (Path | str | None): Optional dotenv file path loaded before
            reading environment variables.

    Returns:
        OpenAIModelConfig: Model and optional temperature and reasoning settings
        for standard data processing.

    Raises:
        ValueError: If the required model environment variable is missing or an
            optional value is invalid.
    """

    return _load_openai_model_config(
        model_env=STANDARD_DATA_MODEL_ENV,
        temperature_env=STANDARD_DATA_TEMPERATURE_ENV,
        reasoning_effort_env=STANDARD_DATA_REASONING_EFFORT_ENV,
        reasoning_summary_env=STANDARD_DATA_REASONING_SUMMARY_ENV,
        env_file=env_file,
    )


def load_standard_data_embedding_config(
    env_file: Path | str | None = None,
) -> OpenAIEmbeddingConfig:
    """Load the standard data embedding model configuration.

    Args:
        env_file (Path | str | None): Optional dotenv file path loaded before
            reading environment variables.

    Returns:
        OpenAIEmbeddingConfig: Embedding model settings for catalog similarity
        search.
    """

    load_dotenv(dotenv_path=env_file)
    return OpenAIEmbeddingConfig(
        model=os.getenv(
            STANDARD_DATA_EMBEDDING_MODEL_ENV,
            DEFAULT_STANDARD_DATA_EMBEDDING_MODEL,
        )
        or DEFAULT_STANDARD_DATA_EMBEDDING_MODEL,
    )


def _load_openai_model_config(
    model_env: str,
    temperature_env: str,
    reasoning_effort_env: str,
    reasoning_summary_env: str,
    env_file: Path | str | None,
) -> OpenAIModelConfig:
    """Load one OpenAI model configuration from environment variables.

    Args:
        model_env (str): Environment variable containing the model name.
        temperature_env (str): Optional environment variable containing a float
            temperature.
        reasoning_effort_env (str): Optional environment variable containing
            the OpenAI reasoning effort.
        reasoning_summary_env (str): Optional environment variable containing
            the OpenAI reasoning summary mode.
        env_file (Path | str | None): Optional dotenv file path loaded before
            reading environment variables.

    Returns:
        OpenAIModelConfig: Loaded model configuration.

    Raises:
        ValueError: If the required model environment variable is missing or an
            optional value is invalid.
    """

    load_dotenv(dotenv_path=env_file)
    return OpenAIModelConfig(
        model=_read_required_env(model_env),
        temperature=_read_optional_float_env(temperature_env),
        reasoning=_read_openai_reasoning(
            effort_env=reasoning_effort_env,
            summary_env=reasoning_summary_env,
        ),
    )


def _read_openai_reasoning(
    effort_env: str,
    summary_env: str,
) -> Mapping[str, str] | None:
    """Read optional OpenAI reasoning settings from environment variables.

    Args:
        effort_env (str): Environment variable containing reasoning effort.
        summary_env (str): Environment variable containing reasoning summary
            mode.

    Returns:
        Mapping[str, str] | None: OpenAI reasoning parameter values, or ``None``
        when no reasoning settings are configured.
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
        float | None: Parsed environment variable value, or ``None`` when the
        variable is missing or empty.

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
    "CanonicalizationConfig",
    "DATA_EXTRACTOR_MODEL_ENV",
    "DATA_EXTRACTOR_REASONING_EFFORT_ENV",
    "DATA_EXTRACTOR_REASONING_SUMMARY_ENV",
    "DATA_EXTRACTOR_TEMPERATURE_ENV",
    "DEFAULT_CANONICALIZATION_INPUT_PATH",
    "DEFAULT_CANONICAL_CATALOG_PATH",
    "DEFAULT_CANONICAL_EMBEDDING_INDEX_PATH",
    "DEFAULT_CANONICALIZED_ALERT_OUTPUT_PATH",
    "DEFAULT_CANONICALIZED_PROFILE_OUTPUT_PATH",
    "DEFAULT_CLIENT_PROFILE_PATH",
    "DEFAULT_INPUT_PATH",
    "DEFAULT_OUTPUT_PATH",
    "DEFAULT_STANDARD_DATA_EMBEDDING_MODEL",
    "ETLConfig",
    "OpenAIEmbeddingConfig",
    "OpenAIModelConfig",
    "STANDARD_DATA_EMBEDDING_MODEL_ENV",
    "STANDARD_DATA_MODEL_ENV",
    "STANDARD_DATA_REASONING_EFFORT_ENV",
    "STANDARD_DATA_REASONING_SUMMARY_ENV",
    "STANDARD_DATA_TEMPERATURE_ENV",
    "build_canonicalization_config",
    "build_config",
    "load_data_extractor_model_config",
    "load_standard_data_embedding_config",
    "load_standard_data_model_config",
]
