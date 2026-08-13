"""Rich terminal presentation for alert relevance chat."""

from __future__ import annotations

import re
from collections.abc import Callable

from rich import box
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from ai_alert_scorer.agent import AlertRelevanceSession, ChatTurnResult
from ai_alert_scorer.config import AlertRelevanceConfig
from ai_alert_scorer.date_ranges import AlertDateRangeError, parse_absolute_timestamp
from ai_alert_scorer.schemas import RankedAlertResult


class RichChatRenderer:
    """Render alert relevance chat state with Rich."""

    def __init__(self, console: Console | None = None) -> None:
        """Initialize the renderer.

        Args:
            console (Console | None): Optional Rich console.
        """

        self.console = console or Console()

    def render_welcome(self, config: AlertRelevanceConfig) -> None:
        """Render the session startup panel.

        Args:
            config (AlertRelevanceConfig): Runtime configuration.
        """

        as_of_line = (
            f"\nAs of: {config.as_of.isoformat()}" if config.as_of is not None else ""
        )
        self.console.print(
            Panel(
                (
                    "Ready for alert relevance questions.\n"
                    f"Canonical alerts: {config.canonical_alerts_path}\n"
                    "Canonical client profile: "
                    f"{config.canonical_client_profile_path}\n"
                    f"Top N: {config.top_n}\n"
                    "Default date range: last 3 days"
                    f"{as_of_line}"
                ),
                title="Alert Relevance Chat",
            )
        )

    def ask_user(self) -> str:
        """Prompt for one user input line.

        Returns:
            str: User-entered prompt.
        """

        return Prompt.ask("[bold cyan]You[/bold cyan]", console=self.console)

    def render_turn(self, result: ChatTurnResult) -> None:
        """Render one completed chat turn.

        Args:
            result (ChatTurnResult): Turn result.
        """

        for event in result.tool_events:
            style = "green" if event.ok else "red"
            self.console.print(
                Text(f"{event.name}: {event.message}", style=style),
            )
        if result.date_range is not None:
            self.console.print(
                Text(
                    "Date range: "
                    f"{result.date_range.label} "
                    f"({result.date_range.start.isoformat()} to "
                    f"{result.date_range.end.isoformat()})",
                    style="cyan",
                )
            )
        if result.ranked_alerts:
            self.render_ranked_alerts(result.ranked_alerts)
        self.render_assistant(result.assistant_message)

    def render_assistant(self, message: str) -> None:
        """Render assistant text.

        Args:
            message (str): Assistant message.
        """

        self.console.print(
            Panel(Markdown(message or "_No response._"), title="Assistant")
        )

    def render_error(self, message: str) -> None:
        """Render an error panel.

        Args:
            message (str): Error message.
        """

        self.console.print(Panel(message, title="Error", style="red"))

    def render_goodbye(self) -> None:
        """Render session exit text."""

        self.console.print(Text("Session ended.", style="dim"))

    def render_ranked_alerts(self, ranked_alerts: list[RankedAlertResult]) -> None:
        """Render ranked alert results as a Rich table.

        Args:
            ranked_alerts (list[RankedAlertResult]): Ranked alert results.
        """

        table = Table(
            title="Ranked Alerts",
            box=box.SIMPLE_HEAVY,
            expand=True,
            header_style="bold white",
            border_style="bright_white",
            show_lines=True,
        )
        table.add_column("Rank", justify="right", width=4, no_wrap=True)
        table.add_column("Score", justify="right", width=7, no_wrap=True)
        table.add_column("Received", width=20, no_wrap=True)
        table.add_column("Subject", ratio=2, overflow="fold", min_width=24)
        table.add_column("Key Evidence", ratio=4, overflow="fold", min_width=44)
        for result in ranked_alerts:
            table.add_row(
                str(result.rank),
                f"{result.final_score:.2f}",
                _format_received_at(result.received_at),
                result.subject,
                _format_evidence(result.evidence),
            )
        self.console.print(table)


def run_interactive_chat(
    config: AlertRelevanceConfig,
    session: AlertRelevanceSession,
    renderer: RichChatRenderer,
    input_provider: Callable[[], str] | None = None,
) -> int:
    """Run the Rich interactive chat loop.

    Args:
        config (AlertRelevanceConfig): Runtime configuration.
        session (AlertRelevanceSession): Stateful chat session.
        renderer (RichChatRenderer): Rich renderer.
        input_provider (Callable[[], str] | None): Optional input override for
            tests.

    Returns:
        int: Process-style exit code.
    """

    from ai_alert_scorer.agent import is_exit_command

    ask = input_provider or renderer.ask_user
    renderer.render_welcome(config)
    while True:
        try:
            user_input = ask()
        except (EOFError, KeyboardInterrupt):
            renderer.render_goodbye()
            return 0

        if is_exit_command(user_input):
            renderer.render_goodbye()
            return 0
        if not user_input.strip():
            continue

        try:
            result = session.run_turn(user_input)
        except ValueError as exc:
            renderer.render_error(str(exc))
            continue
        renderer.render_turn(result)


def _format_received_at(value: str) -> str:
    try:
        received_at = parse_absolute_timestamp(value, "received_at")
    except AlertDateRangeError:
        return value
    return received_at.strftime("%Y-%m-%d %H:%M %Z").strip()


def _format_evidence(evidence: list[str]) -> str:
    return "\n".join(_format_evidence_item(item) for item in evidence)


def _format_evidence_item(item: str) -> str:
    heading, separator, detail = item.partition(":")
    if not separator:
        return f"- {item}"
    readable_heading = re.sub(r"(?<!\d)\.(?!\d)", " / ", heading).replace("_", " ")
    readable_detail = detail.strip().replace("_", " ")
    return f"- {readable_heading}: {readable_detail}"


__all__ = [
    "RichChatRenderer",
    "run_interactive_chat",
]
