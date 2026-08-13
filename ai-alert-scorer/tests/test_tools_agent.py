"""Tests for tools and explicit alert relevance orchestration."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from langchain_core.messages import AIMessage, BaseMessage

from ai_alert_scorer.agent import (
    AlertRelevanceSession,
    build_chat_model,
    is_alert_request,
    resolve_request_top_n,
)
from ai_alert_scorer.config import AlertRelevanceConfig, OpenAIModelConfig
from ai_alert_scorer.tools import build_alert_toolset, decode_tool_payload, tool_names


def _write_fixture_files(tmp_path: Path) -> tuple[Path, Path]:
    """Write canonical client and alert fixture files.

    Args:
        tmp_path (Path): Temporary directory.

    Returns:
        tuple[Path, Path]: Alerts path and client path.
    """

    alerts_path = tmp_path / "alerts.json"
    client_path = tmp_path / "client.json"
    alerts_path.write_text(
        json.dumps(
            [
                _alert_record(
                    alert_id="a01",
                    received_at="2026-08-11T09:00:00Z",
                    subject="Solstice Robotics raises revenue guidance",
                    canonical_company="solstice_robotics",
                ),
                _alert_record(
                    alert_id="a02",
                    received_at="2026-08-10T09:00:00Z",
                    subject="Generic market commentary",
                    canonical_company="unrelated_company",
                ),
            ]
        ),
        encoding="utf-8",
    )
    client_path.write_text(json.dumps(_client_record()), encoding="utf-8")
    return alerts_path, client_path


def _config(tmp_path: Path) -> AlertRelevanceConfig:
    """Build runtime config pointing at fixture files.

    Args:
        tmp_path (Path): Temporary directory.

    Returns:
        AlertRelevanceConfig: Test configuration.
    """

    alerts_path, client_path = _write_fixture_files(tmp_path)
    return AlertRelevanceConfig(
        canonical_alerts_path=alerts_path,
        canonical_client_profile_path=client_path,
        top_n=1,
    )


def _summary_threshold_config(tmp_path: Path) -> AlertRelevanceConfig:
    """Build config with one summary alert and one rank-evidence-only alert.

    Args:
        tmp_path (Path): Temporary directory.

    Returns:
        AlertRelevanceConfig: Test configuration with ``top_n`` set to two.
    """

    alerts_path = tmp_path / "threshold-alerts.json"
    client_path = tmp_path / "threshold-client.json"
    alerts_path.write_text(
        json.dumps(
            [
                _alert_record(
                    alert_id="high",
                    received_at="2026-08-11T18:00:00Z",
                    subject="Solstice Robotics raises revenue guidance",
                    canonical_company="solstice_robotics",
                ),
                {
                    "id": "low",
                    "received_at": "2026-08-11T23:00:00Z",
                    "subject": "Generic market commentary",
                    "body": "Broad market commentary without client overlap.",
                    "companies": [],
                    "sectors": [],
                    "geo_markets": [],
                    "key_markets": [],
                    "commodities": [],
                    "regulators": [],
                    "macro_sensitivities": [],
                    "themes": [],
                },
            ]
        ),
        encoding="utf-8",
    )
    client_path.write_text(json.dumps(_client_record()), encoding="utf-8")
    return AlertRelevanceConfig(
        canonical_alerts_path=alerts_path,
        canonical_client_profile_path=client_path,
        top_n=2,
    )


def _absolute_boundary_config(tmp_path: Path) -> AlertRelevanceConfig:
    """Build config with alerts on and around an absolute date range.

    Args:
        tmp_path (Path): Temporary directory.

    Returns:
        AlertRelevanceConfig: Test configuration with date-boundary alerts.
    """

    alerts_path = tmp_path / "boundary-alerts.json"
    client_path = tmp_path / "boundary-client.json"
    alerts_path.write_text(
        json.dumps(
            [
                _alert_record(
                    alert_id="before-start",
                    received_at="2026-04-30T23:59:59Z",
                    subject="Before range",
                    canonical_company="solstice_robotics",
                ),
                _alert_record(
                    alert_id="start-boundary",
                    received_at="2026-05-01T00:00:00Z",
                    subject="Start boundary",
                    canonical_company="solstice_robotics",
                ),
                _alert_record(
                    alert_id="end-boundary",
                    received_at="2026-07-01T23:59:59.999999Z",
                    subject="End boundary",
                    canonical_company="solstice_robotics",
                ),
                _alert_record(
                    alert_id="after-end",
                    received_at="2026-07-02T00:00:00Z",
                    subject="After range",
                    canonical_company="solstice_robotics",
                ),
            ]
        ),
        encoding="utf-8",
    )
    client_path.write_text(json.dumps(_client_record()), encoding="utf-8")
    return AlertRelevanceConfig(
        canonical_alerts_path=alerts_path,
        canonical_client_profile_path=client_path,
        top_n=5,
    )


def _alert_record(
    alert_id: str,
    received_at: str,
    subject: str,
    canonical_company: str,
) -> dict[str, object]:
    """Build a canonical alert JSON record.

    Args:
        alert_id (str): Alert identifier.
        received_at (str): ISO received-at timestamp.
        subject (str): Alert subject.
        canonical_company (str): Canonical company ID.

    Returns:
        dict[str, object]: Alert JSON record.
    """

    return {
        "id": alert_id,
        "received_at": received_at,
        "subject": subject,
        "body": "Solstice Robotics (SLRB) reported demand from warehouse automation.",
        "companies": [
            {
                "name": canonical_company.replace("_", " "),
                "ticker": "SLRB" if canonical_company == "solstice_robotics" else None,
                "canonical": canonical_company,
                "rationale": "Company appears in the alert.",
            }
        ],
        "sectors": [],
        "geo_markets": [],
        "key_markets": [
            {
                "name": "warehouse automation",
                "canonical": "warehouse_automation",
                "rationale": "Warehouse automation appears in the alert.",
            }
        ],
        "commodities": [],
        "regulators": [],
        "macro_sensitivities": [],
        "themes": [],
    }


def _client_record() -> dict[str, object]:
    """Build a canonical client profile JSON record.

    Returns:
        dict[str, object]: Client profile record.
    """

    return {
        "client_name": "Solstice Robotics",
        "ticker": "SLRB",
        "sector": "industrial_robotics",
        "focal_companies": ["solstice_robotics"],
        "competitors": ["kestrel_automation"],
        "suppliers": ["quanta_sensing"],
        "customers": ["northline_logistics"],
        "geo_markets": ["united_states"],
        "key_markets": ["warehouse_automation"],
        "commodities": ["semiconductor_chips"],
        "regulators": ["cfius"],
        "macro_sensitivities": ["interest_rates"],
        "themes": ["ai_driven_automation"],
    }


def test_alert_toolset_exposes_expected_langchain_tools(tmp_path: Path) -> None:
    """Verify canonical data and ranking tools are exposed by name."""

    toolset = build_alert_toolset(_config(tmp_path))

    assert tool_names(toolset.tools) == [
        "read_canonical_client",
        "read_canonical_alerts",
        "rank_alerts_for_client",
    ]


def test_build_chat_model_uses_openai_responses_api(monkeypatch) -> None:
    """Verify production model configuration uses Responses API state support."""

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    model = build_chat_model(OpenAIModelConfig(model="gpt-test"))

    assert model.use_responses_api is True
    assert model.use_previous_response_id is True
    assert model.output_version == "responses/v1"


def test_alert_request_detects_since_days_ago() -> None:
    """Verify ``since N days ago`` is routed through the alert pipeline."""

    assert is_alert_request("what are the most relevant news since 5 days ago")


def test_alert_request_detects_absolute_date_range_followup() -> None:
    """Verify date-range follow-ups are routed through the alert pipeline."""

    assert is_alert_request(
        "how about between 2026-05-01 and 2026-07-01, show the top 2"
    )


def test_resolve_request_top_n_uses_prompt_override() -> None:
    """Verify per-request ``top N`` overrides the configured default."""

    assert resolve_request_top_n("show the top 2", default_top_n=5) == 2


def test_read_canonical_client_tool_returns_validated_profile(tmp_path: Path) -> None:
    """Verify the client tool returns the configured profile payload."""

    toolset = build_alert_toolset(_config(tmp_path))

    payload = decode_tool_payload(
        toolset.tool_by_name["read_canonical_client"].invoke({})
    )

    assert payload["ok"] is True
    assert payload["client"]["client_name"] == "Solstice Robotics"


def test_read_canonical_alerts_tool_filters_absolute_range(tmp_path: Path) -> None:
    """Verify the alerts tool filters alerts by absolute timestamps."""

    toolset = build_alert_toolset(_config(tmp_path))

    payload = decode_tool_payload(
        toolset.tool_by_name["read_canonical_alerts"].invoke(
            {
                "start_timestamp": "2026-08-11T00:00:00Z",
                "end_timestamp": "2026-08-11T23:59:59Z",
            }
        )
    )

    assert payload["ok"] is True
    assert payload["count"] == 1
    assert payload["alerts"][0]["id"] == "a01"
    assert payload["date_range"]["start"] == "2026-08-11T00:00:00+00:00"


def test_read_canonical_alerts_tool_rejects_missing_range(tmp_path: Path) -> None:
    """Verify the alerts tool never loads every alert without a date range."""

    toolset = build_alert_toolset(_config(tmp_path))

    payload = decode_tool_payload(
        toolset.tool_by_name["read_canonical_alerts"].invoke({})
    )

    assert payload["ok"] is False
    assert "start_timestamp" in payload["error"]


def test_tool_error_payload_is_actionable(tmp_path: Path) -> None:
    """Verify tool load failures are returned as structured errors."""

    config = _config(tmp_path)
    broken_config = AlertRelevanceConfig(
        canonical_alerts_path=config.canonical_alerts_path,
        canonical_client_profile_path=tmp_path / "missing.json",
        top_n=1,
    )
    toolset = build_alert_toolset(broken_config)

    payload = decode_tool_payload(
        toolset.tool_by_name["read_canonical_client"].invoke({})
    )

    assert payload["ok"] is False
    assert "not found" in payload["error"]


def test_rank_alerts_tool_returns_structured_top_results(tmp_path: Path) -> None:
    """Verify ranking tool returns deterministic structured ranked results."""

    toolset = build_alert_toolset(_config(tmp_path))
    client = decode_tool_payload(
        toolset.tool_by_name["read_canonical_client"].invoke({})
    )["client"]
    alerts = decode_tool_payload(
        toolset.tool_by_name["read_canonical_alerts"].invoke(
            {
                "start_timestamp": "2026-08-11T00:00:00Z",
                "end_timestamp": "2026-08-11T23:59:59Z",
            }
        )
    )["alerts"]

    payload = decode_tool_payload(
        toolset.tool_by_name["rank_alerts_for_client"].invoke(
            {
                "client": client,
                "alerts": alerts,
                "top_n": 1,
                "start_timestamp": "2026-08-11T00:00:00Z",
                "end_timestamp": "2026-08-11T23:59:59Z",
            }
        )
    )

    assert payload["ok"] is True
    assert payload["top_n"] == 1
    assert payload["minimum_summary_score"] == 30.0
    assert payload["ranked_alerts"][0]["rank"] == 1
    assert payload["ranked_alerts"][0]["alert_id"] == "a01"
    assert payload["ranked_alerts"][0]["evidence"]
    assert payload["summary_alerts"][0]["alert_id"] == "a01"


@dataclass
class FakeAnswerModel:
    """Fake model that answers from the explicit ranked context."""

    content: str = (
        "Using the default last 3 days window, top alert: Solstice "
        "Robotics raises revenue guidance."
    )
    calls: list[dict[str, object]] = field(default_factory=list)

    def invoke(self, messages: list[BaseMessage], **kwargs: object) -> AIMessage:
        """Return a final answer and record model input.

        Args:
            messages (list[BaseMessage]): Conversation messages.
            **kwargs (object): Invocation kwargs.

        Returns:
            AIMessage: Fake assistant message.
        """

        self.calls.append({"messages": list(messages), "kwargs": kwargs})
        return AIMessage(
            content=self.content,
            response_metadata={"id": "resp-final"},
        )


def test_session_chitchats_without_loading_or_ranking(tmp_path: Path) -> None:
    """Verify non-alert turns are answered without running the alert pipeline."""

    model = FakeAnswerModel(content="Hi. I can help when you want alerts.")
    session = AlertRelevanceSession(config=_config(tmp_path), model=model)

    result = session.run_turn("hi")

    assert result.assistant_message == "Hi. I can help when you want alerts."
    assert result.tool_events == []
    assert result.ranked_alerts == []
    assert result.date_range is None
    assert len(model.calls) == 1
    assert model.calls[0]["messages"][-1].content == "hi"


def test_session_runs_explicit_pipeline_with_default_range(tmp_path: Path) -> None:
    """Verify the session filters, ranks, and sends only ranked context."""

    model = FakeAnswerModel()
    session = AlertRelevanceSession(
        config=_config(tmp_path),
        model=model,
        clock=lambda: datetime(2026, 8, 13, 12, 0, tzinfo=UTC),
    )

    result = session.run_turn("top alerts for Solstice Robotics")

    assert result.used_default_date_range is True
    assert result.date_range is not None
    assert result.date_range.label == "last 3 days (default)"
    assert [event.name for event in result.tool_events] == [
        "read_canonical_client",
        "read_canonical_alerts",
        "rank_alerts_for_client",
    ]
    assert [alert.alert_id for alert in result.ranked_alerts] == ["a01"]
    context = json.loads(model.calls[0]["messages"][-1].content)
    assert context["used_default_date_range"] is True
    assert context["ranked_alerts"][0]["alert_id"] == "a01"
    assert "Generic market commentary" not in model.calls[0]["messages"][-1].content


def test_session_keeps_low_score_alerts_out_of_summary_context(
    tmp_path: Path,
) -> None:
    """Verify sub-30 alerts remain rank evidence but not summary material."""

    model = FakeAnswerModel()
    session = AlertRelevanceSession(
        config=_summary_threshold_config(tmp_path),
        model=model,
        clock=lambda: datetime(2026, 8, 13, 12, 0, tzinfo=UTC),
    )

    result = session.run_turn("top alerts for Solstice Robotics")

    assert [alert.alert_id for alert in result.ranked_alerts] == ["high", "low"]
    assert result.ranked_alerts[1].final_score < 30
    context = json.loads(model.calls[0]["messages"][-1].content)
    assert context["minimum_summary_score"] == 30.0
    assert [alert["alert_id"] for alert in context["ranked_alerts"]] == [
        "high",
        "low",
    ]
    assert [alert["alert_id"] for alert in context["summary_alerts"]] == ["high"]
    assert [alert["alert_id"] for alert in context["rank_evidence_only_alerts"]] == [
        "low"
    ]


def test_session_uses_explicit_date_only_range(tmp_path: Path) -> None:
    """Verify date-only user ranges are not replaced by the default window."""

    model = FakeAnswerModel()
    session = AlertRelevanceSession(
        config=_config(tmp_path),
        model=model,
        clock=lambda: datetime(2026, 8, 13, 12, 0, tzinfo=UTC),
    )

    result = session.run_turn(
        "give me the news between 2026-08-05 and 2026-08-09"
    )

    assert result.used_default_date_range is False
    assert result.date_range is not None
    assert result.date_range.label == "explicit date range"
    assert result.date_range.start.isoformat() == "2026-08-05T00:00:00+00:00"
    assert (
        result.date_range.end.isoformat()
        == "2026-08-09T23:59:59.999999+00:00"
    )
    assert result.ranked_alerts == []
    assert result.tool_events[1].message == "loaded 0 alerts for explicit date range"
    context = json.loads(model.calls[0]["messages"][-1].content)
    assert context["used_default_date_range"] is False
    assert context["date_range"]["label"] == "explicit date range"


def test_session_uses_absolute_boundaries_and_requested_top_n(tmp_path: Path) -> None:
    """Verify explicit date ranges include full boundary dates and top-N."""

    model = FakeAnswerModel()
    session = AlertRelevanceSession(
        config=_absolute_boundary_config(tmp_path),
        model=model,
        clock=lambda: datetime(2026, 8, 13, 12, 0, tzinfo=UTC),
    )

    result = session.run_turn(
        "how about between 2026-05-01 and 2026-07-01, show the top 2"
    )

    assert result.used_default_date_range is False
    assert result.date_range is not None
    assert result.date_range.start.isoformat() == "2026-05-01T00:00:00+00:00"
    assert (
        result.date_range.end.isoformat()
        == "2026-07-01T23:59:59.999999+00:00"
    )
    assert [alert.alert_id for alert in result.ranked_alerts] == [
        "end-boundary",
        "start-boundary",
    ]
    assert result.tool_events[1].message == "loaded 2 alerts for explicit date range"
    context = json.loads(model.calls[0]["messages"][-1].content)
    assert context["top_n"] == 2
    assert [alert["alert_id"] for alert in context["ranked_alerts"]] == [
        "end-boundary",
        "start-boundary",
    ]


def test_session_uses_relative_days_ago_range(tmp_path: Path) -> None:
    """Verify ``from N days ago`` requests use a rolling lookback range."""

    model = FakeAnswerModel()
    session = AlertRelevanceSession(
        config=_config(tmp_path),
        model=model,
        clock=lambda: datetime(2026, 8, 13, 15, 12, tzinfo=UTC),
    )

    result = session.run_turn("tell me the most relevant client news from 5 days ago")

    assert result.used_default_date_range is False
    assert result.date_range is not None
    assert result.date_range.label == "from 5 days ago"
    assert result.date_range.start.isoformat() == "2026-08-08T15:12:00+00:00"
    assert result.date_range.end.isoformat() == "2026-08-13T15:12:00+00:00"
    assert len(result.ranked_alerts) == 1
    assert result.ranked_alerts[0].alert_id == "a01"
    assert result.tool_events[1].message == "loaded 2 alerts from 5 days ago"
    context = json.loads(model.calls[0]["messages"][-1].content)
    assert context["used_default_date_range"] is False
    assert context["date_range"]["label"] == "from 5 days ago"


def test_session_uses_as_of_anchor_for_today(tmp_path: Path) -> None:
    """Verify configured as-of anchors drive relative date resolution."""

    model = FakeAnswerModel()
    base_config = _config(tmp_path)
    config = AlertRelevanceConfig(
        canonical_alerts_path=base_config.canonical_alerts_path,
        canonical_client_profile_path=base_config.canonical_client_profile_path,
        top_n=base_config.top_n,
        as_of=datetime(2026, 8, 11, 12, 0, tzinfo=UTC),
    )
    session = AlertRelevanceSession(
        config=config,
        model=model,
        clock=lambda: datetime(2026, 8, 13, 15, 12, tzinfo=UTC),
    )

    result = session.run_turn("top alerts today")

    assert result.used_default_date_range is False
    assert result.date_range is not None
    assert result.date_range.label == "today"
    assert result.date_range.start.isoformat() == "2026-08-11T00:00:00+00:00"
    assert (
        result.date_range.end.isoformat()
        == "2026-08-11T23:59:59.999999+00:00"
    )
    assert [alert.alert_id for alert in result.ranked_alerts] == ["a01"]
    context = json.loads(model.calls[0]["messages"][-1].content)
    assert context["date_range"]["label"] == "today"


def test_session_asks_for_one_client_before_model_or_loading(tmp_path: Path) -> None:
    """Verify obvious multi-client requests are clarified before model calls."""

    model = FakeAnswerModel()
    session = AlertRelevanceSession(config=_config(tmp_path), model=model)

    result = session.run_turn("top alerts for Solstice Robotics and Kestrel")

    assert result.asked_for_client_clarification is True
    assert "one client" in result.assistant_message
    assert model.calls == []
