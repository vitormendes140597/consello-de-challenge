"""Command-line entrypoint for the alert extraction ETL."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from etl.canonicalization.candidates import (
    CanonicalCandidateGenerator,
    OpenAITextEmbeddingClient,
)
from etl.canonicalization.catalog import load_canonical_catalog
from etl.canonicalization.processing import run_canonicalization_processing
from etl.common.config import (
    CanonicalizationConfig,
    ETLConfig,
    build_canonicalization_config,
    build_config,
    load_data_extractor_model_config,
    load_standard_data_embedding_config,
    load_standard_data_model_config,
)
from etl.common.io import AlertDataLoader, StorageBackend
from etl.common.openai import create_openai_model
from etl.common.schemas import RawAlert
from etl.extraction.processing import run_alert_extraction_etl
from etl.extraction.prompts import build_synthesis_prompt

DEFAULT_COMMAND = "run"
PROMPT_COMMAND = "prompt"
CANONICALIZE_COMMAND = "canonicalize"
COMMANDS = {DEFAULT_COMMAND, PROMPT_COMMAND, CANONICALIZE_COMMAND}


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for ETL actions.

    Args:
        argv (Sequence[str] | None): Optional command-line tokens. Uses
            ``sys.argv`` when omitted.

    Returns:
        argparse.Namespace: Parsed ETL command and option values.
    """

    parser = _build_parser()
    raw_args = list(sys.argv[1:] if argv is None else argv)
    return parser.parse_args(_normalize_argv(raw_args))


def build_prompt_from_config(
    config: ETLConfig,
    alert_id: str | None = None,
) -> str:
    """Build the extraction prompt for one configured alert.

    Args:
        config (ETLConfig): File path configuration for raw alerts and client
            profile context.
        alert_id (str | None): Optional alert id to select from the raw alert
            input. Uses the first alert when omitted.

    Returns:
        str: Complete model-facing synthesis prompt for the selected alert.

    Raises:
        OSError: If input files cannot be read.
        json.JSONDecodeError: If an input file is not valid JSON.
        ValueError: If either input JSON root has the wrong shape, the raw alert
            dataset is empty, or ``alert_id`` does not exist.
        pydantic.ValidationError: If raw alerts fail validation.
    """

    storage = StorageBackend()
    loader = AlertDataLoader(storage=storage)
    alerts = loader.load_raw_alerts(config.input_path)
    context_hints = loader.load_client_profile_context(config.client_profile_path)
    alert = _select_alert(alerts=alerts, alert_id=alert_id)

    return build_synthesis_prompt(
        subject=alert.subject,
        body=alert.body,
        context_hints=context_hints,
    )


def _build_parser() -> argparse.ArgumentParser:
    """Build the alert extraction ETL argument parser.

    Returns:
        argparse.ArgumentParser: Configured parser for run and prompt commands.
    """

    parser = argparse.ArgumentParser(description="Run the alert extraction ETL.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser(
        DEFAULT_COMMAND,
        help="Run alert extraction and write enriched alerts.",
    )
    _add_path_arguments(run_parser, include_output=True)

    prompt_parser = subparsers.add_parser(
        PROMPT_COMMAND,
        help="Print the generated extraction prompt for one alert.",
    )
    _add_path_arguments(prompt_parser, include_output=False)
    prompt_parser.add_argument(
        "--alert-id",
        help="Raw alert id to generate a prompt for. Uses the first alert if omitted.",
    )

    canonicalize_parser = subparsers.add_parser(
        CANONICALIZE_COMMAND,
        help="Canonicalize enriched alerts and the customer profile.",
    )
    _add_canonicalization_path_arguments(canonicalize_parser)

    return parser


def _add_path_arguments(
    parser: argparse.ArgumentParser,
    include_output: bool,
) -> None:
    """Add shared ETL file path options to a parser.

    Args:
        parser (argparse.ArgumentParser): Parser receiving path options.
        include_output (bool): Whether to include the enriched output path
            option used by the run command.

    Returns:
        None: This function mutates ``parser``.
    """

    parser.add_argument("--input-path", help="Path to the raw alerts JSON file.")
    parser.add_argument(
        "--client-profile-path",
        help="Path to the client profile context JSON file.",
    )
    if include_output:
        parser.add_argument(
            "--output-path",
            help="Path for the enriched alerts JSON file.",
        )


def _add_canonicalization_path_arguments(parser: argparse.ArgumentParser) -> None:
    """Add canonicalization file path options to a parser.

    Args:
        parser (argparse.ArgumentParser): Parser receiving canonicalization
            path options.

    Returns:
        None: This function mutates ``parser``.
    """

    parser.add_argument(
        "--input-path",
        help="Path to the enriched alerts JSON input file.",
    )
    parser.add_argument(
        "--client-profile-path",
        help="Path to the client profile JSON file.",
    )
    parser.add_argument(
        "--catalog-path",
        help="Path to the canonical catalog JSON file.",
    )
    parser.add_argument(
        "--embedding-index-path",
        help="Path to the local catalog embedding index/cache JSON file.",
    )
    parser.add_argument(
        "--output-path",
        dest="alert_output_path",
        help="Path for the canonicalized alerts JSON file.",
    )
    parser.add_argument(
        "--profile-output-path",
        help="Path for the canonicalized customer profile JSON file.",
    )


def _normalize_argv(argv: list[str]) -> list[str]:
    """Normalize legacy no-subcommand invocations to the run command.

    Args:
        argv (list[str]): Command-line tokens excluding the executable name.

    Returns:
        list[str]: Tokens safe to pass to the subcommand parser.
    """

    if not argv or argv[0] in COMMANDS or argv[0] in {"-h", "--help"}:
        return argv
    return [DEFAULT_COMMAND, *argv]


def run_canonicalization_from_config(
    config: CanonicalizationConfig,
) -> object:
    """Run canonicalization from configured paths and OpenAI settings.

    Args:
        config (CanonicalizationConfig): Canonicalization file path
            configuration.

    Returns:
        object: Processing result returned by the canonicalization pipeline.

    Raises:
        OSError: If configured files cannot be read or written.
        json.JSONDecodeError: If configured JSON files are malformed.
        ValueError: If configuration, loaded data, candidate generation, or
            model responses are invalid.
        pydantic.ValidationError: If schemas fail validation.
    """

    catalog = load_canonical_catalog(config.catalog_path)
    model_config = load_standard_data_model_config()
    model = create_openai_model(model_config)
    embedding_config = load_standard_data_embedding_config()
    embedding_client = OpenAITextEmbeddingClient(model=embedding_config.model)
    candidate_generator = CanonicalCandidateGenerator(
        catalog=catalog,
        embedding_client=embedding_client,
        embedding_index_path=config.embedding_index_path,
    )
    return run_canonicalization_processing(
        input_path=config.input_path,
        client_profile_path=config.client_profile_path,
        alert_output_path=config.alert_output_path,
        profile_output_path=config.profile_output_path,
        catalog=catalog,
        model=model,
        candidate_generator=candidate_generator,
    )


def _select_alert(
    alerts: Sequence[RawAlert],
    alert_id: str | None,
) -> RawAlert:
    """Select one raw alert for prompt generation.

    Args:
        alerts (Sequence[RawAlert]): Loaded raw alerts.
        alert_id (str | None): Optional alert id to match.

    Returns:
        RawAlert: Selected alert record.

    Raises:
        ValueError: If there are no alerts or the requested id is not present.
    """

    if not alerts:
        raise ValueError("Raw alert dataset is empty.")
    if alert_id is None:
        return alerts[0]

    for alert in alerts:
        if alert.id == alert_id:
            return alert

    raise ValueError(f"No raw alert found with id: {alert_id}")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the alert extraction ETL command.

    Args:
        argv (Sequence[str] | None): Optional command-line tokens. Uses
            ``sys.argv`` when omitted.

    Returns:
        int: Process exit code. Returns ``0`` after successful ETL processing.
    """

    args = parse_args(argv)
    if args.command == PROMPT_COMMAND:
        config = build_config(
            input_path=args.input_path,
            client_profile_path=args.client_profile_path,
        )
        prompt = build_prompt_from_config(config=config, alert_id=args.alert_id)
        sys.stdout.write(prompt)
        sys.stdout.write("\n")
        return 0

    if args.command == CANONICALIZE_COMMAND:
        config = build_canonicalization_config(
            input_path=args.input_path,
            client_profile_path=args.client_profile_path,
            catalog_path=args.catalog_path,
            embedding_index_path=args.embedding_index_path,
            alert_output_path=args.alert_output_path,
            profile_output_path=args.profile_output_path,
        )
        run_canonicalization_from_config(config)
        return 0

    config = build_config(
        input_path=args.input_path,
        client_profile_path=args.client_profile_path,
        output_path=args.output_path,
    )
    model_config = load_data_extractor_model_config()
    model = create_openai_model(model_config)
    run_alert_extraction_etl(config=config, model=model)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
