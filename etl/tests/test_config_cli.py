"""Tests for ETL configuration and CLI argument handling."""

import json
from pathlib import Path

import pytest

from etl.app import cli
from etl.common import config as etl_config
from etl.common.config import (
    DEFAULT_CANONICAL_CATALOG_PATH,
    DEFAULT_CANONICAL_EMBEDDING_INDEX_PATH,
    DEFAULT_CANONICALIZATION_INPUT_PATH,
    DEFAULT_CANONICALIZED_ALERT_OUTPUT_PATH,
    DEFAULT_CANONICALIZED_PROFILE_OUTPUT_PATH,
    DEFAULT_CLIENT_PROFILE_PATH,
    DEFAULT_INPUT_PATH,
    DEFAULT_OUTPUT_PATH,
    DEFAULT_STANDARD_DATA_EMBEDDING_MODEL,
    build_canonicalization_config,
    build_config,
)


def test_build_config_uses_default_paths() -> None:
    """Verify omitted config paths resolve to ETL defaults."""

    config = build_config()

    assert config.input_path == DEFAULT_INPUT_PATH
    assert config.client_profile_path == DEFAULT_CLIENT_PROFILE_PATH
    assert config.output_path == DEFAULT_OUTPUT_PATH


def test_build_config_accepts_custom_paths() -> None:
    """Verify custom config paths are converted to Path objects."""

    config = build_config(
        input_path="raw/custom.json",
        client_profile_path="raw/client_profile.json",
        output_path=Path("processed/custom.json"),
    )

    assert config.input_path == Path("raw/custom.json")
    assert config.client_profile_path == Path("raw/client_profile.json")
    assert config.output_path == Path("processed/custom.json")


def test_build_canonicalization_config_uses_default_paths() -> None:
    """Verify canonicalization config defaults use separate output files."""

    config = build_canonicalization_config()

    assert config.input_path == DEFAULT_CANONICALIZATION_INPUT_PATH
    assert config.client_profile_path == DEFAULT_CLIENT_PROFILE_PATH
    assert config.catalog_path == DEFAULT_CANONICAL_CATALOG_PATH
    assert config.embedding_index_path == DEFAULT_CANONICAL_EMBEDDING_INDEX_PATH
    assert config.alert_output_path == DEFAULT_CANONICALIZED_ALERT_OUTPUT_PATH
    assert config.profile_output_path == DEFAULT_CANONICALIZED_PROFILE_OUTPUT_PATH
    assert config.alert_output_path != DEFAULT_OUTPUT_PATH


def test_build_canonicalization_config_accepts_custom_paths() -> None:
    """Verify canonicalization config accepts explicit paths."""

    config = build_canonicalization_config(
        input_path="processed/enriched.json",
        client_profile_path="raw/client_profile.json",
        catalog_path="config/catalog.json",
        embedding_index_path="processed/embeddings.json",
        alert_output_path="processed/canonical_alerts.json",
        profile_output_path="processed/canonical_profile.json",
    )

    assert config.input_path == Path("processed/enriched.json")
    assert config.client_profile_path == Path("raw/client_profile.json")
    assert config.catalog_path == Path("config/catalog.json")
    assert config.embedding_index_path == Path("processed/embeddings.json")
    assert config.alert_output_path == Path("processed/canonical_alerts.json")
    assert config.profile_output_path == Path("processed/canonical_profile.json")


def test_data_extractor_model_config_requires_env(
    monkeypatch,
) -> None:
    """Verify extractor model name must be provided."""

    monkeypatch.setattr(etl_config, "load_dotenv", lambda dotenv_path=None: None)
    monkeypatch.setenv(etl_config.DATA_EXTRACTOR_TEMPERATURE_ENV, "0.1")
    monkeypatch.delenv(etl_config.DATA_EXTRACTOR_MODEL_ENV, raising=False)

    with pytest.raises(ValueError, match=etl_config.DATA_EXTRACTOR_MODEL_ENV):
        etl_config.load_data_extractor_model_config()


def test_data_extractor_model_config_omits_missing_optional_values(
    monkeypatch,
) -> None:
    """Verify missing optional extractor model settings are omitted."""

    monkeypatch.setattr(etl_config, "load_dotenv", lambda dotenv_path=None: None)
    monkeypatch.setenv(etl_config.DATA_EXTRACTOR_MODEL_ENV, "custom-extractor")
    monkeypatch.delenv(etl_config.DATA_EXTRACTOR_TEMPERATURE_ENV, raising=False)
    monkeypatch.delenv(
        etl_config.DATA_EXTRACTOR_REASONING_EFFORT_ENV,
        raising=False,
    )
    monkeypatch.delenv(
        etl_config.DATA_EXTRACTOR_REASONING_SUMMARY_ENV,
        raising=False,
    )

    config = etl_config.load_data_extractor_model_config()

    assert config.model == "custom-extractor"
    assert config.temperature is None
    assert config.reasoning is None


def test_data_extractor_model_config_rejects_invalid_temperature(
    monkeypatch,
) -> None:
    """Verify configured extractor temperature must be a float."""

    monkeypatch.setattr(etl_config, "load_dotenv", lambda dotenv_path=None: None)
    monkeypatch.setenv(etl_config.DATA_EXTRACTOR_MODEL_ENV, "custom-extractor")
    monkeypatch.setenv(etl_config.DATA_EXTRACTOR_TEMPERATURE_ENV, "low")

    with pytest.raises(ValueError, match=etl_config.DATA_EXTRACTOR_TEMPERATURE_ENV):
        etl_config.load_data_extractor_model_config()


def test_model_env_names_are_distinct() -> None:
    """Verify extractor and standardization model env names are separate."""

    assert etl_config.DATA_EXTRACTOR_MODEL_ENV != etl_config.STANDARD_DATA_MODEL_ENV
    assert (
        etl_config.DATA_EXTRACTOR_TEMPERATURE_ENV
        != etl_config.STANDARD_DATA_TEMPERATURE_ENV
    )
    assert (
        etl_config.DATA_EXTRACTOR_REASONING_EFFORT_ENV
        != etl_config.STANDARD_DATA_REASONING_EFFORT_ENV
    )


def test_data_extractor_model_config_loads_reasoning(monkeypatch) -> None:
    """Verify extractor model config includes optional OpenAI reasoning."""

    monkeypatch.setattr(etl_config, "load_dotenv", lambda dotenv_path=None: None)
    monkeypatch.setenv(etl_config.DATA_EXTRACTOR_MODEL_ENV, "custom-extractor")
    monkeypatch.setenv(etl_config.DATA_EXTRACTOR_TEMPERATURE_ENV, "0.1")
    monkeypatch.setenv(etl_config.DATA_EXTRACTOR_REASONING_EFFORT_ENV, "medium")
    monkeypatch.setenv(etl_config.DATA_EXTRACTOR_REASONING_SUMMARY_ENV, "auto")

    config = etl_config.load_data_extractor_model_config()

    assert config.model == "custom-extractor"
    assert config.temperature == 0.1
    assert config.reasoning == {"effort": "medium", "summary": "auto"}


def test_standard_data_model_config_uses_separate_env(monkeypatch) -> None:
    """Verify standard data model settings use separate environment names."""

    monkeypatch.setattr(etl_config, "load_dotenv", lambda dotenv_path=None: None)
    monkeypatch.setenv(etl_config.STANDARD_DATA_MODEL_ENV, "custom-standard")
    monkeypatch.setenv(etl_config.STANDARD_DATA_TEMPERATURE_ENV, "0.2")
    monkeypatch.setenv(etl_config.STANDARD_DATA_REASONING_EFFORT_ENV, "low")

    config = etl_config.load_standard_data_model_config()

    assert config.model == "custom-standard"
    assert config.temperature == 0.2
    assert config.reasoning == {"effort": "low"}


def test_standard_data_embedding_config_uses_default_model(monkeypatch) -> None:
    """Verify embedding config defaults to the canonicalization embedding model."""

    monkeypatch.setattr(etl_config, "load_dotenv", lambda dotenv_path=None: None)
    monkeypatch.delenv(etl_config.STANDARD_DATA_EMBEDDING_MODEL_ENV, raising=False)

    config = etl_config.load_standard_data_embedding_config()

    assert config.model == DEFAULT_STANDARD_DATA_EMBEDDING_MODEL


def test_standard_data_embedding_config_uses_env(monkeypatch) -> None:
    """Verify embedding config can be overridden independently."""

    monkeypatch.setattr(etl_config, "load_dotenv", lambda dotenv_path=None: None)
    monkeypatch.setenv(
        etl_config.STANDARD_DATA_EMBEDDING_MODEL_ENV,
        "custom-embedding",
    )

    config = etl_config.load_standard_data_embedding_config()

    assert config.model == "custom-embedding"


def test_parse_args_accepts_path_overrides() -> None:
    """Verify CLI parsing accepts file path overrides."""

    args = cli.parse_args(
        [
            "--input-path",
            "raw/alerts.json",
            "--client-profile-path",
            "raw/client_profile.json",
            "--output-path",
            "processed/enriched.json",
        ]
    )

    assert args.input_path == "raw/alerts.json"
    assert args.client_profile_path == "raw/client_profile.json"
    assert args.output_path == "processed/enriched.json"
    assert args.command == "run"


def test_parse_args_accepts_canonicalize_command() -> None:
    """Verify CLI parsing accepts canonicalization path overrides."""

    args = cli.parse_args(
        [
            "canonicalize",
            "--input-path",
            "processed/enriched.json",
            "--client-profile-path",
            "raw/client_profile.json",
            "--catalog-path",
            "config/catalog.json",
            "--embedding-index-path",
            "processed/embeddings.json",
            "--output-path",
            "processed/canonical_alerts.json",
            "--profile-output-path",
            "processed/canonical_profile.json",
        ]
    )

    assert args.command == "canonicalize"
    assert args.input_path == "processed/enriched.json"
    assert args.client_profile_path == "raw/client_profile.json"
    assert args.catalog_path == "config/catalog.json"
    assert args.embedding_index_path == "processed/embeddings.json"
    assert args.alert_output_path == "processed/canonical_alerts.json"
    assert args.profile_output_path == "processed/canonical_profile.json"


def test_parse_args_accepts_prompt_command() -> None:
    """Verify CLI parsing accepts prompt generation options."""

    args = cli.parse_args(
        [
            "prompt",
            "--input-path",
            "raw/alerts.json",
            "--client-profile-path",
            "raw/client_profile.json",
            "--alert-id",
            "a02",
        ]
    )

    assert args.command == "prompt"
    assert args.input_path == "raw/alerts.json"
    assert args.client_profile_path == "raw/client_profile.json"
    assert args.alert_id == "a02"


def test_main_builds_config_from_cli_args(monkeypatch) -> None:
    """Verify CLI main passes parsed paths into config construction."""

    captured_args = {}
    config = object()
    model_config = object()
    model = object()

    def fake_build_config(
        input_path: str | None = None,
        client_profile_path: str | None = None,
        output_path: str | None = None,
    ) -> object:
        captured_args["input_path"] = input_path
        captured_args["client_profile_path"] = client_profile_path
        captured_args["output_path"] = output_path
        return config

    def fake_load_data_extractor_model_config() -> object:
        captured_args["loaded_model_config"] = True
        return model_config

    def fake_create_openai_model(config_arg: object) -> object:
        captured_args["model_config"] = config_arg
        return model

    def fake_run_alert_extraction_etl(
        config: object,
        model: object,
    ) -> list[object]:
        captured_args["etl_config"] = config
        captured_args["model"] = model
        return []

    monkeypatch.setattr(cli, "build_config", fake_build_config)
    monkeypatch.setattr(
        cli,
        "load_data_extractor_model_config",
        fake_load_data_extractor_model_config,
    )
    monkeypatch.setattr(cli, "create_openai_model", fake_create_openai_model)
    monkeypatch.setattr(
        cli,
        "run_alert_extraction_etl",
        fake_run_alert_extraction_etl,
    )

    exit_code = cli.main(
        [
            "--input-path",
            "raw/alerts.json",
            "--client-profile-path",
            "raw/client_profile.json",
            "--output-path",
            "processed/enriched.json",
        ]
    )

    assert exit_code == 0
    assert captured_args == {
        "input_path": "raw/alerts.json",
        "client_profile_path": "raw/client_profile.json",
        "output_path": "processed/enriched.json",
        "loaded_model_config": True,
        "model_config": model_config,
        "etl_config": config,
        "model": model,
    }


def test_main_canonicalize_command_runs_canonicalization_flow(monkeypatch) -> None:
    """Verify canonicalize command builds config and runs its processing flow."""

    captured_args = {}
    config = object()

    def fake_build_canonicalization_config(
        input_path: str | None = None,
        client_profile_path: str | None = None,
        catalog_path: str | None = None,
        embedding_index_path: str | None = None,
        alert_output_path: str | None = None,
        profile_output_path: str | None = None,
    ) -> object:
        captured_args["input_path"] = input_path
        captured_args["client_profile_path"] = client_profile_path
        captured_args["catalog_path"] = catalog_path
        captured_args["embedding_index_path"] = embedding_index_path
        captured_args["alert_output_path"] = alert_output_path
        captured_args["profile_output_path"] = profile_output_path
        return config

    def fake_run_canonicalization_from_config(config_arg: object) -> object:
        captured_args["canonicalization_config"] = config_arg
        return object()

    def fail_load_data_extractor_model_config() -> object:
        raise AssertionError("canonicalize command should not load extractor model")

    monkeypatch.setattr(
        cli,
        "build_canonicalization_config",
        fake_build_canonicalization_config,
    )
    monkeypatch.setattr(
        cli,
        "run_canonicalization_from_config",
        fake_run_canonicalization_from_config,
    )
    monkeypatch.setattr(
        cli,
        "load_data_extractor_model_config",
        fail_load_data_extractor_model_config,
    )

    exit_code = cli.main(
        [
            "canonicalize",
            "--input-path",
            "processed/enriched.json",
            "--client-profile-path",
            "raw/client_profile.json",
            "--catalog-path",
            "config/catalog.json",
            "--embedding-index-path",
            "processed/embeddings.json",
            "--output-path",
            "processed/canonical_alerts.json",
            "--profile-output-path",
            "processed/canonical_profile.json",
        ]
    )

    assert exit_code == 0
    assert captured_args == {
        "input_path": "processed/enriched.json",
        "client_profile_path": "raw/client_profile.json",
        "catalog_path": "config/catalog.json",
        "embedding_index_path": "processed/embeddings.json",
        "alert_output_path": "processed/canonical_alerts.json",
        "profile_output_path": "processed/canonical_profile.json",
        "canonicalization_config": config,
    }


def test_run_canonicalization_from_config_loads_standard_data_settings(
    monkeypatch,
) -> None:
    """Verify canonicalization uses standard data and embedding model configs."""

    captured_args = {}
    config = build_canonicalization_config(
        input_path="processed/enriched.json",
        client_profile_path="raw/client_profile.json",
        catalog_path="config/catalog.json",
        embedding_index_path="processed/embeddings.json",
        alert_output_path="processed/canonical_alerts.json",
        profile_output_path="processed/canonical_profile.json",
    )
    catalog = object()
    model_config = object()
    model = object()
    embedding_config = etl_config.OpenAIEmbeddingConfig(model="embedding-model")

    class FakeOpenAITextEmbeddingClient:
        """Fake embedding client constructor used by the CLI."""

        def __init__(self, model: str) -> None:
            """Record the embedding model name.

            Args:
                model (str): Embedding model name.
            """

            captured_args["embedding_model"] = model

    class FakeCanonicalCandidateGenerator:
        """Fake candidate generator constructor used by the CLI."""

        def __init__(
            self,
            catalog: object,
            embedding_client: object,
            embedding_index_path: Path,
        ) -> None:
            """Record canonicalization dependencies.

            Args:
                catalog (object): Loaded catalog object.
                embedding_client (object): Embedding client object.
                embedding_index_path (Path): Local index/cache path.
            """

            captured_args["candidate_catalog"] = catalog
            captured_args["candidate_embedding_client"] = embedding_client
            captured_args["embedding_index_path"] = embedding_index_path

    def fake_load_canonical_catalog(path: Path) -> object:
        captured_args["catalog_path"] = path
        return catalog

    def fake_load_standard_data_model_config() -> object:
        captured_args["standard_model_loaded"] = True
        return model_config

    def fake_create_openai_model(config_arg: object) -> object:
        captured_args["model_config"] = config_arg
        return model

    def fake_load_standard_data_embedding_config() -> object:
        captured_args["embedding_config_loaded"] = True
        return embedding_config

    def fake_run_canonicalization_processing(**kwargs: object) -> object:
        captured_args["processing_kwargs"] = kwargs
        return object()

    monkeypatch.setattr(cli, "load_canonical_catalog", fake_load_canonical_catalog)
    monkeypatch.setattr(
        cli,
        "load_standard_data_model_config",
        fake_load_standard_data_model_config,
    )
    monkeypatch.setattr(cli, "create_openai_model", fake_create_openai_model)
    monkeypatch.setattr(
        cli,
        "load_standard_data_embedding_config",
        fake_load_standard_data_embedding_config,
    )
    monkeypatch.setattr(cli, "OpenAITextEmbeddingClient", FakeOpenAITextEmbeddingClient)
    monkeypatch.setattr(
        cli,
        "CanonicalCandidateGenerator",
        FakeCanonicalCandidateGenerator,
    )
    monkeypatch.setattr(
        cli,
        "run_canonicalization_processing",
        fake_run_canonicalization_processing,
    )

    cli.run_canonicalization_from_config(config)

    candidate_generator = captured_args["processing_kwargs"]["candidate_generator"]
    assert captured_args["catalog_path"] == Path("config/catalog.json")
    assert captured_args["standard_model_loaded"] is True
    assert captured_args["model_config"] is model_config
    assert captured_args["embedding_config_loaded"] is True
    assert captured_args["embedding_model"] == "embedding-model"
    assert captured_args["candidate_catalog"] is catalog
    assert captured_args["candidate_embedding_client"] is not None
    assert captured_args["embedding_index_path"] == Path("processed/embeddings.json")
    assert candidate_generator is not None
    assert captured_args["processing_kwargs"]["catalog"] is catalog
    assert captured_args["processing_kwargs"]["model"] is model
    assert captured_args["processing_kwargs"]["input_path"] == Path(
        "processed/enriched.json"
    )
    assert captured_args["processing_kwargs"]["alert_output_path"] == Path(
        "processed/canonical_alerts.json"
    )


def test_main_prompt_command_prints_selected_alert_prompt(
    tmp_path,
    capsys,
    monkeypatch,
) -> None:
    """Verify prompt command prints the generated prompt without creating a model."""

    alerts_path = tmp_path / "alerts.json"
    client_profile_path = tmp_path / "client_profile.json"
    alerts_path.write_text(
        json.dumps(
            [
                {
                    "id": "a01",
                    "received_at": "2026-08-11T09:00:00+00:00",
                    "subject": "First alert",
                    "body": "First body.",
                },
                {
                    "id": "a02",
                    "received_at": "2026-08-12T09:00:00+00:00",
                    "subject": "Target expands in Germany & Mexico",
                    "body": "Solstice Robotics opened a warehouse automation plant.",
                },
            ]
        ),
        encoding="utf-8",
    )
    client_profile_path.write_text(
        json.dumps({"geo_markets": ["Germany", "Mexico"]}),
        encoding="utf-8",
    )

    def fail_load_data_extractor_model_config() -> object:
        raise AssertionError("prompt command should not load model configuration")

    monkeypatch.setattr(
        cli,
        "load_data_extractor_model_config",
        fail_load_data_extractor_model_config,
    )

    exit_code = cli.main(
        [
            "prompt",
            "--input-path",
            str(alerts_path),
            "--client-profile-path",
            str(client_profile_path),
            "--alert-id",
            "a02",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Target expands in Germany &amp; Mexico" in captured.out
    assert "Solstice Robotics opened a warehouse automation plant." in captured.out
    assert "- geo_markets: Germany, Mexico" in captured.out
    assert "First alert" not in captured.out


def test_build_prompt_from_config_rejects_missing_alert_id(tmp_path) -> None:
    """Verify prompt generation fails clearly when an alert id is unknown."""

    alerts_path = tmp_path / "alerts.json"
    client_profile_path = tmp_path / "client_profile.json"
    alerts_path.write_text(
        json.dumps(
            [
                {
                    "id": "a01",
                    "received_at": "2026-08-11T09:00:00+00:00",
                    "subject": "First alert",
                    "body": "First body.",
                }
            ]
        ),
        encoding="utf-8",
    )
    client_profile_path.write_text("{}", encoding="utf-8")
    config = build_config(
        input_path=alerts_path,
        client_profile_path=client_profile_path,
    )

    with pytest.raises(ValueError, match="missing"):
        cli.build_prompt_from_config(config=config, alert_id="missing")
