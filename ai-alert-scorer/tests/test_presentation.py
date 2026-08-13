"""Tests for Rich chat presentation."""

from __future__ import annotations

from dataclasses import dataclass

from rich.console import Console

from ai_alert_scorer.agent import ChatTurnResult, ToolEvent
from ai_alert_scorer.app.presentation import RichChatRenderer, run_interactive_chat
from ai_alert_scorer.config import AlertRelevanceConfig
from ai_alert_scorer.date_ranges import build_alert_date_range
from ai_alert_scorer.schemas import RankedAlertResult


def _ranked_alert() -> RankedAlertResult:
    """Build one ranked alert for rendering tests.

    Returns:
        RankedAlertResult: Ranked alert result.
    """

    return RankedAlertResult(
        rank=1,
        alert_id="a01",
        received_at="2026-08-11T09:00:00+00:00",
        subject="Solstice Robotics raises guidance",
        final_score=88.25,
        matched_canonical_ids=["solstice_robotics"],
        evidence=[
            (
                "relationship_proximity.direct_client_canonical +45.00 pts: "
                "matches client focal company: solstice_robotics"
            ),
            "direct client match",
            "key market overlap",
            "combination bonus",
            "recency +8.75 pts",
        ],
    )


def test_renderer_prints_ranked_alert_table() -> None:
    """Verify ranked results render as a Rich table."""

    console = Console(record=True, width=140)
    renderer = RichChatRenderer(console)

    renderer.render_ranked_alerts([_ranked_alert()])

    output = console.export_text()
    assert "Ranked Alerts" in output
    assert "88.25" in output
    assert "2026-08-11 09:00 UTC" in output
    assert "Solstice Robotics raises" in output
    assert "guidance" in output
    assert "relationship proximity / direct client canonical +45.00 pts" in output
    assert "matches client focal company: solstice robotics" in output
    assert "- direct client match" in output
    assert "recency +8.75 pts" in output


def test_renderer_prints_tool_events_and_assistant_message() -> None:
    """Verify a chat turn renders tool status and assistant text."""

    console = Console(record=True, width=140)
    renderer = RichChatRenderer(console)

    renderer.render_turn(
        ChatTurnResult(
            assistant_message="Final answer",
            tool_events=[
                ToolEvent(
                    name="read_canonical_alerts",
                    ok=True,
                    message="loaded 1 alerts",
                )
            ],
            ranked_alerts=[_ranked_alert()],
            date_range=build_alert_date_range(
                "2026-08-11T00:00:00Z",
                "2026-08-11T23:59:59Z",
            ),
        )
    )

    output = console.export_text()
    assert "read_canonical_alerts: loaded 1 alerts" in output
    assert "Date range: explicit range" in output
    assert "Final answer" in output
    assert "Ranked Alerts" in output


@dataclass
class NoCallSession:
    """Session stub that should not be called for exit commands."""

    calls: int = 0

    def run_turn(self, user_input: str) -> ChatTurnResult:
        """Record a run call.

        Args:
            user_input (str): User prompt.

        Returns:
            ChatTurnResult: Stub response.
        """

        self.calls += 1
        return ChatTurnResult(assistant_message="unused")


def test_interactive_loop_exits_without_model_call() -> None:
    """Verify supported exit commands end the chat loop."""

    console = Console(record=True, width=120)
    renderer = RichChatRenderer(console)
    session = NoCallSession()

    exit_code = run_interactive_chat(
        config=AlertRelevanceConfig(),
        session=session,
        renderer=renderer,
        input_provider=lambda: "exit",
    )

    output = console.export_text()
    assert exit_code == 0
    assert session.calls == 0
    assert "Session ended." in output
