"""Tests for the compatibility main module."""

from __future__ import annotations

from collections.abc import Sequence

import main as etl_main


def test_run_delegates_to_cli_main(monkeypatch) -> None:
    """Verify the top-level main module delegates to the ETL CLI."""

    captured_args = {}

    def fake_cli_main(argv: Sequence[str] | None = None) -> int:
        captured_args["argv"] = argv
        return 0

    monkeypatch.setattr(etl_main, "cli_main", fake_cli_main)

    exit_code = etl_main.run(["--input-path", "raw/alerts.json"])

    assert exit_code == 0
    assert captured_args == {"argv": ["--input-path", "raw/alerts.json"]}
