"""LangChain tool definitions for alert relevance data and ranking."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field

from ai_alert_scorer.config import AlertRelevanceConfig
from ai_alert_scorer.date_ranges import (
    AlertDateRange,
    AlertDateRangeError,
    build_alert_date_range,
)
from ai_alert_scorer.io import CanonicalDataLoader, CanonicalDataLoadError
from ai_alert_scorer.schemas import CanonicalizedAlert, CanonicalizedClientProfile
from ai_alert_scorer.scoring import SUMMARY_MIN_SCORE, rank_alerts_for_client


class ReadCanonicalAlertsArgs(BaseModel):
    """Arguments for reading canonical alerts.

    Attributes:
        start_timestamp (str | None): ISO timezone-aware inclusive start.
        end_timestamp (str | None): ISO timezone-aware inclusive end.
    """

    start_timestamp: str | None = Field(
        default=None,
        description="Inclusive ISO timezone-aware start timestamp.",
    )
    end_timestamp: str | None = Field(
        default=None,
        description="Inclusive ISO timezone-aware end timestamp.",
    )


class RankAlertsArgs(BaseModel):
    """Arguments for ranking canonical alerts for the configured client.

    Attributes:
        client (dict): Canonicalized client profile returned by
            ``read_canonical_client``.
        alerts (list[dict]): Canonicalized alerts returned by
            ``read_canonical_alerts``.
        top_n (int | None): Optional maximum ranked result count.
        start_timestamp (str | None): Inclusive ISO timezone-aware start.
        end_timestamp (str | None): Inclusive ISO timezone-aware end.
    """

    client: dict = Field(description="Canonicalized client profile.")
    alerts: list[dict] = Field(description="Candidate canonicalized alerts.")
    top_n: int | None = Field(default=None, ge=1)
    start_timestamp: str | None = Field(default=None)
    end_timestamp: str | None = Field(default=None)


@dataclass(frozen=True)
class AlertToolset:
    """Container for alert relevance LangChain tools.

    Attributes:
        tools (list[BaseTool]): Tools bound to the chat model.
        tool_by_name (dict[str, BaseTool]): Tool lookup for local execution.
    """

    tools: list[BaseTool]
    tool_by_name: dict[str, BaseTool]


def build_alert_toolset(
    config: AlertRelevanceConfig,
    loader: CanonicalDataLoader | None = None,
    clock: Callable[[], datetime] | None = None,
) -> AlertToolset:
    """Build LangChain tools for canonical data and deterministic ranking.

    Args:
        config (AlertRelevanceConfig): Runtime file and ranking configuration.
        loader (CanonicalDataLoader | None): Optional loader override for tests.
        clock (Callable[[], datetime] | None): Optional clock override used as
            the recency anchor when ``config.as_of`` is unset.

    Returns:
        AlertToolset: Tool list and name lookup.
    """

    data_loader = loader or CanonicalDataLoader()

    def read_canonical_client() -> str:
        """Read the configured canonicalized client profile."""

        try:
            client = data_loader.load_client_profile(
                config.canonical_client_profile_path
            )
        except CanonicalDataLoadError as exc:
            return _json_error(str(exc))
        return _json_success({"client": client.model_dump()})

    def read_canonical_alerts(
        start_timestamp: str | None = None,
        end_timestamp: str | None = None,
    ) -> str:
        """Read configured canonical alerts filtered by absolute timestamps."""

        try:
            date_range = _build_required_date_range(
                start_timestamp=start_timestamp,
                end_timestamp=end_timestamp,
            )
            alerts = data_loader.load_alerts_for_date_range(
                path=config.canonical_alerts_path,
                date_range=date_range,
            )
        except (CanonicalDataLoadError, AlertDateRangeError) as exc:
            return _json_error(str(exc))

        payload = {
            "alerts": [alert.model_dump() for alert in alerts],
            "count": len(alerts),
            "date_range": date_range.model_payload(),
        }
        return _json_success(payload)

    def rank_alerts_for_client_tool(
        client: dict,
        alerts: list[dict],
        top_n: int | None = None,
        start_timestamp: str | None = None,
        end_timestamp: str | None = None,
    ) -> str:
        """Rank canonical alerts against one configured client profile."""

        try:
            date_range = _build_required_date_range(
                start_timestamp=start_timestamp,
                end_timestamp=end_timestamp,
            )
            parsed_client = CanonicalizedClientProfile.model_validate(client)
            parsed_alerts = [
                CanonicalizedAlert.model_validate(alert) for alert in alerts
            ]
            ranked = rank_alerts_for_client(
                alerts=parsed_alerts,
                client=parsed_client,
                date_range=date_range,
                top_n=top_n or config.top_n,
                scored_at=_scoring_anchor(config, clock),
            )
        except (TypeError, ValueError, AlertDateRangeError) as exc:
            return _json_error(str(exc))

        return _json_success(
            {
                "top_n": top_n or config.top_n,
                "minimum_summary_score": SUMMARY_MIN_SCORE,
                "ranked_alerts": [result.model_dump() for result in ranked],
                "summary_alerts": [
                    result.model_dump()
                    for result in ranked
                    if result.final_score >= SUMMARY_MIN_SCORE
                ],
                "rank_evidence_only_alerts": [
                    result.model_dump()
                    for result in ranked
                    if result.final_score < SUMMARY_MIN_SCORE
                ],
            }
        )

    tools = [
        StructuredTool.from_function(
            func=read_canonical_client,
            name="read_canonical_client",
            description=(
                "Load and validate the configured canonicalized client profile. "
                "Use this before ranking alerts."
            ),
        ),
        StructuredTool.from_function(
            func=read_canonical_alerts,
            name="read_canonical_alerts",
            description=(
                "Load and validate canonicalized alerts filtered by inclusive "
                "absolute ISO timestamps. Always pass start_timestamp and "
                "end_timestamp; never call this tool without a date range."
            ),
            args_schema=ReadCanonicalAlertsArgs,
        ),
        StructuredTool.from_function(
            func=rank_alerts_for_client_tool,
            name="rank_alerts_for_client",
            description=(
                "Deterministically rank candidate canonical alerts for exactly "
                "one canonicalized client profile. Use returned scores and "
                "evidence; do not invent ranking evidence. Treat alerts below "
                "minimum_summary_score as rank evidence only."
            ),
            args_schema=RankAlertsArgs,
        ),
    ]
    return AlertToolset(
        tools=tools,
        tool_by_name={tool.name: tool for tool in tools},
    )


def _build_required_date_range(
    start_timestamp: str | None,
    end_timestamp: str | None,
) -> AlertDateRange:
    if not start_timestamp or not end_timestamp:
        raise AlertDateRangeError("start_timestamp and end_timestamp are required")
    return build_alert_date_range(start_timestamp, end_timestamp)


def _scoring_anchor(
    config: AlertRelevanceConfig,
    clock: Callable[[], datetime] | None,
) -> datetime:
    if config.as_of is not None:
        return config.as_of
    if clock is not None:
        return clock()
    return datetime.now(UTC)


def _json_success(payload: dict[str, object]) -> str:
    return json.dumps({"ok": True, **payload}, default=str)


def _json_error(message: str) -> str:
    return json.dumps({"ok": False, "error": message})


def decode_tool_payload(content: str) -> dict[str, object]:
    """Decode a JSON payload returned by an alert relevance tool.

    Args:
        content (str): Tool return content.

    Returns:
        dict[str, object]: Decoded payload, or an error payload when decoding
        fails.
    """

    try:
        value = json.loads(content)
    except json.JSONDecodeError:
        return {"ok": False, "error": "Tool returned non-JSON content"}
    if not isinstance(value, dict):
        return {"ok": False, "error": "Tool returned a non-object JSON payload"}
    return value


def tool_names(tools: Sequence[BaseTool]) -> list[str]:
    """Return stable names for a sequence of tools.

    Args:
        tools (Sequence[BaseTool]): LangChain tools.

    Returns:
        list[str]: Tool names in input order.
    """

    return [tool.name for tool in tools]


__all__ = [
    "AlertToolset",
    "RankAlertsArgs",
    "ReadCanonicalAlertsArgs",
    "build_alert_toolset",
    "decode_tool_payload",
    "tool_names",
]
