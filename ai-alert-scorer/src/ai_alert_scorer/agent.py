"""Model orchestration for the alert relevance chat session."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    ChatMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_openai import ChatOpenAI

from ai_alert_scorer.config import (
    AlertRelevanceConfig,
    OpenAIModelConfig,
    load_openai_model_config,
)
from ai_alert_scorer.date_ranges import (
    AlertDateRange,
    AlertDateRangeError,
    resolve_request_date_range,
)
from ai_alert_scorer.io import CanonicalDataLoader, CanonicalDataLoadError
from ai_alert_scorer.schemas import RankedAlertResult
from ai_alert_scorer.scoring import SUMMARY_MIN_SCORE, rank_alerts_for_client

EXIT_COMMANDS = frozenset({"exit", "quit", "q", ":q", "/exit"})
SYSTEM_INSTRUCTIONS = (
    "You are an alert relevance assistant for one configured client. Answer "
    "normal conversational turns directly. Only answer alert-ranking, news, "
    "briefing, or summary requests from ranked alert results provided by the "
    "application."
)
DEVELOPER_INSTRUCTIONS = (
    "Identify the user's intent before answering. If the user is greeting you, "
    "making small talk, asking about capabilities, or otherwise not clearly "
    "requesting alerts, keep the conversation normal and do not imply alerts "
    "were loaded. For clear alert-ranking, client-news, briefing, or summary "
    "requests, the application will load the client, filter alerts by an "
    "absolute date range, and rank the filtered alerts before you answer. Do "
    "not invent scores, ranks, alert IDs, or evidence. Use summary_alerts, not "
    "ranked_alerts, for the final summary. Alerts with final_score below "
    "minimum_summary_score are rank evidence only and must not be summarized as "
    "key alerts. If no summary_alerts are provided, state that no alerts met "
    "the 30-point summary threshold for the applied date range. If no ranked "
    "alerts are provided, state that no alerts were found for the applied date "
    "range. If the default date range was used, explicitly say it used the "
    "last 3 days by default."
)
ALERT_REQUEST_PATTERNS = (
    re.compile(r"\balerts?\b", re.IGNORECASE),
    re.compile(r"\bclient\s+news\b", re.IGNORECASE),
    re.compile(r"\bmedia\s+alerts?\b", re.IGNORECASE),
    re.compile(r"\brank(?:ed|ing)?\b.+\b(news|alerts?|updates?)\b", re.IGNORECASE),
    re.compile(r"\b(news|updates?|headlines?)\b.+\brank(?:ed|ing)?\b", re.IGNORECASE),
    re.compile(
        r"\b(?:top|best|most\s+relevant|show|list|get|give\s+me|summari[sz]e|summary|brief|briefing)\b"
        r".+\b(news|updates?|headlines?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(news|updates?|headlines?)\b.+\b(today|yesterday|last\s+\d+\s+days|past\s+week|from|since|between)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:anything|what(?:'s|\s+is))\b.+\b(?:important|relevant|noteworthy)\b"
        r".+\b(?:today|yesterday|recent|latest|last|past)\b",
        re.IGNORECASE,
    ),
)
DATE_RANGE_FOLLOWUP_PATTERN = re.compile(
    r"\b\d{4}-\d{2}-\d{2}\b.+\b(?:and|to|through|thru|until)\b.+"
    r"\b\d{4}-\d{2}-\d{2}\b",
    re.IGNORECASE,
)
TOP_N_PATTERN = re.compile(r"\btop\s+(\d+)\b", re.IGNORECASE)
MULTI_CLIENT_PATTERNS = (
    re.compile(r"\bmultiple\s+clients\b", re.IGNORECASE),
    re.compile(r"\bcompare\b.+\bclients?\b", re.IGNORECASE),
    re.compile(r"\bfor\s+.+\s+(?:and|vs\.?|versus)\s+.+", re.IGNORECASE),
)


class ChatModel(Protocol):
    """Minimal chat model protocol used by the session orchestrator."""

    def invoke(
        self,
        messages: Sequence[BaseMessage],
        **kwargs: object,
    ) -> AIMessage:
        """Invoke a chat model.

        Args:
            messages (Sequence[BaseMessage]): Conversation messages.
            **kwargs (object): Provider-specific invocation parameters.

        Returns:
            AIMessage: Assistant model response.
        """


@dataclass(frozen=True)
class ToolEvent:
    """Information about one local pipeline step.

    Attributes:
        name (str): Step name.
        ok (bool): Whether the step succeeded.
        message (str): Short status or error message.
    """

    name: str
    ok: bool
    message: str


@dataclass(frozen=True)
class ChatTurnResult:
    """Result from one user turn.

    Attributes:
        assistant_message (str): Assistant text to render.
        tool_events (list[ToolEvent]): Local load/rank status events.
        ranked_alerts (list[RankedAlertResult]): Ranked results sent to the
            model.
        date_range (AlertDateRange | None): Applied alert date range.
        used_default_date_range (bool): Whether the default three-day lookback
            was used.
        asked_for_client_clarification (bool): Whether the turn was stopped by
            one-client validation.
    """

    assistant_message: str
    tool_events: list[ToolEvent] = field(default_factory=list)
    ranked_alerts: list[RankedAlertResult] = field(default_factory=list)
    date_range: AlertDateRange | None = None
    used_default_date_range: bool = False
    asked_for_client_clarification: bool = False


class AlertRelevanceSession:
    """Stateful alert relevance chat session with an explicit PoC pipeline."""

    def __init__(
        self,
        config: AlertRelevanceConfig,
        model_config: OpenAIModelConfig | None = None,
        model: ChatModel | None = None,
        loader: CanonicalDataLoader | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        """Initialize a chat session.

        Args:
            config (AlertRelevanceConfig): Runtime configuration.
            model_config (OpenAIModelConfig | None): Optional OpenAI model
                settings. Loaded from environment when no model is injected.
            model (ChatModel | None): Optional fake or preconfigured model.
            loader (CanonicalDataLoader | None): Optional loader override.
            clock (Callable[[], datetime] | None): Optional clock override.

        Raises:
            ValueError: If model settings cannot be loaded.
        """

        self._config = config
        self._loader = loader or CanonicalDataLoader()
        self._clock = clock or (lambda: datetime.now(UTC))
        if model is None:
            model_settings = model_config or load_openai_model_config()
            model = build_chat_model(model_settings)
        self._model = model
        self._messages: list[BaseMessage] = [
            SystemMessage(content=SYSTEM_INSTRUCTIONS),
            ChatMessage(role="developer", content=DEVELOPER_INSTRUCTIONS),
        ]
        self._previous_response_id: str | None = None

    @property
    def messages(self) -> list[BaseMessage]:
        """Return a copy of current conversation messages.

        Returns:
            list[BaseMessage]: Conversation messages.
        """

        return list(self._messages)

    def run_turn(self, user_input: str) -> ChatTurnResult:
        """Run one user turn through the local pipeline and response model.

        Args:
            user_input (str): User prompt.

        Returns:
            ChatTurnResult: Assistant text and renderable artifacts.
        """

        if not is_alert_request(user_input):
            human_message = HumanMessage(content=user_input)
            self._messages.append(human_message)
            ai_message = self._invoke_model(self._messages)
            self._messages.append(ai_message)
            self._remember_response_id(ai_message)
            return ChatTurnResult(assistant_message=_message_text(ai_message))

        if requires_client_clarification(user_input):
            message = (
                "I can rank alerts for one client at a time. Which single "
                "client should I use for this request?"
            )
            return ChatTurnResult(
                assistant_message=message,
                asked_for_client_clarification=True,
            )

        human_message = HumanMessage(content=user_input)
        self._messages.append(human_message)

        try:
            time_anchor = self._relative_time_anchor()
            resolution = resolve_request_date_range(
                user_input,
                now=time_anchor,
            )
            top_n = resolve_request_top_n(user_input, self._config.top_n)
            client = self._loader.load_client_profile(
                self._config.canonical_client_profile_path
            )
            alerts = self._loader.load_alerts_for_date_range(
                path=self._config.canonical_alerts_path,
                date_range=resolution.date_range,
            )
            ranked_alerts = rank_alerts_for_client(
                alerts=alerts,
                client=client,
                date_range=resolution.date_range,
                top_n=top_n,
                scored_at=time_anchor,
            )
        except (AlertDateRangeError, CanonicalDataLoadError, ValueError) as exc:
            return ChatTurnResult(assistant_message=str(exc))

        tool_events = [
            ToolEvent(
                name="read_canonical_client",
                ok=True,
                message=f"loaded client {client.client_name or 'profile'}",
            ),
            ToolEvent(
                name="read_canonical_alerts",
                ok=True,
                message=_loaded_alerts_message(len(alerts), resolution.date_range),
            ),
            ToolEvent(
                name="rank_alerts_for_client",
                ok=True,
                message=f"ranked {len(ranked_alerts)} alerts",
            ),
        ]

        context_message = ChatMessage(
            role="developer",
            content=_response_context(
                date_range=resolution.date_range,
                used_default=resolution.used_default,
                top_n=top_n,
                ranked_alerts=ranked_alerts,
            ),
        )
        ai_message = self._invoke_model([*self._messages, context_message])
        self._messages.append(context_message)
        self._messages.append(ai_message)
        self._remember_response_id(ai_message)

        return ChatTurnResult(
            assistant_message=_message_text(ai_message),
            tool_events=tool_events,
            ranked_alerts=ranked_alerts,
            date_range=resolution.date_range,
            used_default_date_range=resolution.used_default,
        )

    def _invoke_model(self, messages: Sequence[BaseMessage]) -> AIMessage:
        kwargs: dict[str, object] = {}
        if self._previous_response_id:
            kwargs["previous_response_id"] = self._previous_response_id
        return self._model.invoke(messages, **kwargs)

    def _relative_time_anchor(self) -> datetime:
        if self._config.as_of is not None:
            return self._config.as_of
        return self._clock()

    def _remember_response_id(self, message: AIMessage) -> None:
        response_id = message.response_metadata.get("id")
        if isinstance(response_id, str) and response_id:
            self._previous_response_id = response_id


def build_chat_model(model_config: OpenAIModelConfig) -> ChatOpenAI:
    """Build a LangChain OpenAI chat model for alert relevance.

    Args:
        model_config (OpenAIModelConfig): OpenAI model settings.

    Returns:
        ChatOpenAI: Responses API chat model.
    """

    return ChatOpenAI(
        model=model_config.model,
        temperature=model_config.temperature,
        reasoning=model_config.reasoning,
        use_responses_api=True,
        output_version="responses/v1",
        use_previous_response_id=True,
    )


def requires_client_clarification(user_input: str) -> bool:
    """Detect obvious multi-client requests before ranking.

    Args:
        user_input (str): User prompt.

    Returns:
        bool: ``True`` when the prompt should be clarified before tool use.
    """

    return any(pattern.search(user_input) for pattern in MULTI_CLIENT_PATTERNS)


def is_alert_request(user_input: str) -> bool:
    """Detect clear requests to retrieve, rank, or summarize alerts.

    Args:
        user_input (str): User prompt.

    Returns:
        bool: ``True`` when the local alert-ranking pipeline should run.
    """

    normalized = user_input.strip()
    if not normalized:
        return False
    return (
        any(pattern.search(normalized) for pattern in ALERT_REQUEST_PATTERNS)
        or DATE_RANGE_FOLLOWUP_PATTERN.search(normalized) is not None
    )


def resolve_request_top_n(user_input: str, default_top_n: int) -> int:
    """Resolve an optional ``top N`` override from a user request.

    Args:
        user_input (str): User prompt.
        default_top_n (int): Configured fallback result count.

    Returns:
        int: Requested or default top-N count.

    Raises:
        ValueError: If the requested or default top-N count is not positive.
    """

    match = TOP_N_PATTERN.search(user_input)
    value = int(match.group(1)) if match else default_top_n
    if value < 1:
        raise ValueError("top_n must be a positive integer")
    return value


def is_exit_command(user_input: str) -> bool:
    """Return whether a prompt exits the interactive session.

    Args:
        user_input (str): User prompt.

    Returns:
        bool: ``True`` for supported exit commands.
    """

    return user_input.strip().lower() in EXIT_COMMANDS


def _response_context(
    date_range: AlertDateRange,
    used_default: bool,
    top_n: int,
    ranked_alerts: list[RankedAlertResult],
) -> str:
    payload = {
        "instruction": (
            "Answer final summaries from summary_alerts only. ranked_alerts "
            "are rank evidence and may include alerts below the summary "
            "threshold. Mention the default last-3-days window if "
            "used_default_date_range is true."
        ),
        "top_n": top_n,
        "minimum_summary_score": SUMMARY_MIN_SCORE,
        "date_range": date_range.model_payload(),
        "used_default_date_range": used_default,
        "ranked_alerts": [result.model_dump() for result in ranked_alerts],
        "summary_alerts": [
            result.model_dump()
            for result in ranked_alerts
            if result.final_score >= SUMMARY_MIN_SCORE
        ],
        "rank_evidence_only_alerts": [
            result.model_dump()
            for result in ranked_alerts
            if result.final_score < SUMMARY_MIN_SCORE
        ],
    }
    return json.dumps(payload, default=str)


def _loaded_alerts_message(alert_count: int, date_range: AlertDateRange) -> str:
    if date_range.label.startswith("from "):
        return f"loaded {alert_count} alerts {date_range.label}"
    return f"loaded {alert_count} alerts for {date_range.label}"


def _message_text(message: AIMessage) -> str:
    if isinstance(message.content, str):
        return message.content
    parts: list[str] = []
    for block in message.content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and isinstance(block.get("text"), str):
            parts.append(block["text"])
    return "\n".join(parts)


__all__ = [
    "AlertRelevanceSession",
    "ChatModel",
    "ChatTurnResult",
    "DEVELOPER_INSTRUCTIONS",
    "EXIT_COMMANDS",
    "SYSTEM_INSTRUCTIONS",
    "ToolEvent",
    "build_chat_model",
    "is_alert_request",
    "is_exit_command",
    "resolve_request_top_n",
    "requires_client_clarification",
]
