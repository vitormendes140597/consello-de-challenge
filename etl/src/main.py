"""Compatibility entrypoint for running the alert extraction ETL."""

from __future__ import annotations

from collections.abc import Sequence

from etl.app.cli import main as cli_main


def run(argv: Sequence[str] | None = None) -> int:
    """Run the alert extraction ETL command.

    Args:
        argv (Sequence[str] | None): Optional command-line tokens. Uses
            ``sys.argv`` when omitted.

    Returns:
        int: Process exit code from the ETL CLI.
    """

    return cli_main(argv)


if __name__ == "__main__":
    raise SystemExit(run())
