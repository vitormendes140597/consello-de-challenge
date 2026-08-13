"""Command-line entrypoint for alert relevance chat."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from rich.console import Console
from rich.panel import Panel

from ai_alert_scorer.agent import AlertRelevanceSession
from ai_alert_scorer.app.presentation import RichChatRenderer, run_interactive_chat
from ai_alert_scorer.config import AlertRelevanceConfig, build_config


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for the alert relevance chat CLI.

    Args:
        argv (Sequence[str] | None): Optional command-line tokens. Uses
            ``sys.argv`` when omitted.

    Returns:
        argparse.Namespace: Parsed command-line options.
    """

    parser = argparse.ArgumentParser(description="Run the alert relevance chat CLI.")
    parser.add_argument(
        "--canonical-alerts-path",
        help="Path to canonicalized alerts JSON array.",
    )
    parser.add_argument(
        "--canonical-client-profile-path",
        help="Path to canonicalized client profile JSON object.",
    )
    parser.add_argument(
        "--top-n",
        default=None,
        help="Default number of ranked alerts to return.",
    )
    parser.add_argument(
        "--as-of",
        default=None,
        help=(
            "ISO date or timezone-aware ISO datetime used to anchor relative "
            "time phrases."
        ),
    )
    return parser.parse_args(sys.argv[1:] if argv is None else argv)


def build_config_from_args(args: argparse.Namespace) -> AlertRelevanceConfig:
    """Build runtime configuration from parsed CLI arguments.

    Args:
        args (argparse.Namespace): Parsed CLI arguments.

    Returns:
        AlertRelevanceConfig: Runtime configuration.

    Raises:
        ValueError: If a parsed option is invalid.
    """

    config = build_config(
        canonical_alerts_path=args.canonical_alerts_path,
        canonical_client_profile_path=args.canonical_client_profile_path,
        top_n=args.top_n,
        as_of=args.as_of,
    )
    return config


def main(argv: Sequence[str] | None = None) -> int:
    """Run the alert relevance chat command.

    Args:
        argv (Sequence[str] | None): Optional command-line tokens. Uses
            ``sys.argv`` when omitted.

    Returns:
        int: Process exit code.
    """

    console = Console()
    args = parse_args(argv)
    try:
        config = build_config_from_args(args)
        session = AlertRelevanceSession(config=config)
    except ValueError as exc:
        console.print(Panel(str(exc), title="Configuration Error", style="red"))
        return 2

    return run_interactive_chat(
        config=config,
        session=session,
        renderer=RichChatRenderer(console),
    )


if __name__ == "__main__":
    raise SystemExit(main())
