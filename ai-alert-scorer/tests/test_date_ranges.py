"""Tests for absolute alert date ranges."""

from datetime import UTC, datetime

import pytest

from ai_alert_scorer.date_ranges import (
    AlertDateRangeError,
    build_alert_date_range,
    default_alert_date_range,
    filter_alerts_by_date_range,
    parse_absolute_timestamp,
    parse_as_of_datetime,
    resolve_request_date_range,
)
from ai_alert_scorer.schemas import CanonicalizedAlert


def _alert(alert_id: str, received_at: str) -> CanonicalizedAlert:
    """Build a minimal canonical alert for date-range tests.

    Args:
        alert_id (str): Alert identifier.
        received_at (str): ISO received-at timestamp.

    Returns:
        CanonicalizedAlert: Test alert record.
    """

    return CanonicalizedAlert(
        id=alert_id,
        received_at=received_at,
        subject=f"Subject {alert_id}",
        body="Body",
    )


def test_parse_absolute_timestamp_accepts_zulu_timezone() -> None:
    """Verify absolute timestamps must parse as aware datetimes."""

    parsed = parse_absolute_timestamp("2026-08-11T00:00:00Z", "start_timestamp")

    assert parsed.isoformat() == "2026-08-11T00:00:00+00:00"


def test_parse_absolute_timestamp_rejects_naive_value() -> None:
    """Verify timestamps without timezone are rejected."""

    with pytest.raises(AlertDateRangeError, match="timezone"):
        parse_absolute_timestamp("2026-08-11T00:00:00", "start_timestamp")


def test_build_alert_date_range_rejects_inverted_range() -> None:
    """Verify start must be before end."""

    with pytest.raises(AlertDateRangeError, match="before"):
        build_alert_date_range(
            "2026-08-12T00:00:00Z",
            "2026-08-11T00:00:00Z",
        )


def test_filter_alerts_includes_range_boundaries() -> None:
    """Verify alert filtering includes start and end timestamps."""

    date_range = build_alert_date_range(
        "2026-08-11T00:00:00Z",
        "2026-08-11T23:59:59Z",
    )
    alerts = [
        _alert("before", "2026-08-10T23:59:59Z"),
        _alert("start", "2026-08-11T00:00:00Z"),
        _alert("end", "2026-08-11T23:59:59Z"),
        _alert("after", "2026-08-12T00:00:00Z"),
    ]

    filtered = filter_alerts_by_date_range(alerts, date_range)

    assert [alert.id for alert in filtered] == ["start", "end"]


def test_default_alert_date_range_uses_last_three_days() -> None:
    """Verify the default window is a rolling three-day range."""

    now = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)

    date_range = default_alert_date_range(now=now)

    assert date_range.label == "last 3 days (default)"
    assert date_range.start.isoformat() == "2026-08-10T12:00:00+00:00"
    assert date_range.end == now


def test_resolve_request_date_range_uses_explicit_timestamps() -> None:
    """Verify two ISO timestamps in a request become the applied range."""

    resolution = resolve_request_date_range(
        "alerts from 2026-08-11T00:00:00Z to 2026-08-12T00:00:00Z"
    )

    assert resolution.used_default is False
    assert resolution.date_range.start.isoformat() == "2026-08-11T00:00:00+00:00"
    assert resolution.date_range.end.isoformat() == "2026-08-12T00:00:00+00:00"


def test_resolve_request_date_range_uses_explicit_dates() -> None:
    """Verify two ISO dates in a request become full UTC day boundaries."""

    resolution = resolve_request_date_range(
        "give me the news between 2026-08-05 and 2026-08-09"
    )

    assert resolution.used_default is False
    assert resolution.date_range.label == "explicit date range"
    assert resolution.date_range.start.isoformat() == "2026-08-05T00:00:00+00:00"
    assert (
        resolution.date_range.end.isoformat()
        == "2026-08-09T23:59:59.999999+00:00"
    )


def test_resolve_request_date_range_uses_single_explicit_date() -> None:
    """Verify one ISO date in a request becomes that full UTC day."""

    resolution = resolve_request_date_range("give me the news on 2026-08-08")

    assert resolution.used_default is False
    assert resolution.date_range.label == "explicit date"
    assert resolution.date_range.start.isoformat() == "2026-08-08T00:00:00+00:00"
    assert (
        resolution.date_range.end.isoformat()
        == "2026-08-08T23:59:59.999999+00:00"
    )


def test_resolve_request_date_range_uses_today_from_anchor() -> None:
    """Verify ``today`` resolves to the anchor's full calendar day."""

    now = datetime(2026, 8, 13, 15, 12, tzinfo=UTC)

    resolution = resolve_request_date_range("top alerts today", now=now)

    assert resolution.used_default is False
    assert resolution.date_range.label == "today"
    assert resolution.date_range.start.isoformat() == "2026-08-13T00:00:00+00:00"
    assert (
        resolution.date_range.end.isoformat()
        == "2026-08-13T23:59:59.999999+00:00"
    )


def test_resolve_request_date_range_uses_yesterday_from_anchor() -> None:
    """Verify ``yesterday`` resolves to the prior full calendar day."""

    now = datetime(2026, 8, 13, 15, 12, tzinfo=UTC)

    resolution = resolve_request_date_range("top alerts yesterday", now=now)

    assert resolution.used_default is False
    assert resolution.date_range.label == "yesterday"
    assert resolution.date_range.start.isoformat() == "2026-08-12T00:00:00+00:00"
    assert (
        resolution.date_range.end.isoformat()
        == "2026-08-12T23:59:59.999999+00:00"
    )


def test_resolve_request_date_range_uses_from_days_ago_as_lookback() -> None:
    """Verify ``from N days ago`` resolves to a rolling lookback range."""

    now = datetime(2026, 8, 13, 15, 12, tzinfo=UTC)

    resolution = resolve_request_date_range("client news from 5 days ago", now=now)

    assert resolution.used_default is False
    assert resolution.date_range.label == "from 5 days ago"
    assert resolution.date_range.start.isoformat() == "2026-08-08T15:12:00+00:00"
    assert resolution.date_range.end == now


def test_resolve_request_date_range_uses_since_days_ago_as_lookback() -> None:
    """Verify ``since N days ago`` resolves to a rolling lookback range."""

    now = datetime(2026, 8, 13, 15, 12, tzinfo=UTC)

    resolution = resolve_request_date_range("client news since 2 days ago", now=now)

    assert resolution.used_default is False
    assert resolution.date_range.label == "from 2 days ago"
    assert resolution.date_range.start.isoformat() == "2026-08-11T15:12:00+00:00"
    assert resolution.date_range.end == now


def test_resolve_request_date_range_uses_plain_days_ago_from_anchor() -> None:
    """Verify ``N days ago`` resolves to that full prior calendar day."""

    now = datetime(2026, 8, 13, 15, 12, tzinfo=UTC)

    resolution = resolve_request_date_range("client news 5 days ago", now=now)

    assert resolution.used_default is False
    assert resolution.date_range.label == "5 days ago"
    assert resolution.date_range.start.isoformat() == "2026-08-08T00:00:00+00:00"
    assert (
        resolution.date_range.end.isoformat()
        == "2026-08-08T23:59:59.999999+00:00"
    )


def test_resolve_request_date_range_uses_last_n_calendar_days() -> None:
    """Verify explicit ``last N days`` uses calendar days through the anchor."""

    now = datetime(2026, 8, 13, 15, 12, tzinfo=UTC)

    resolution = resolve_request_date_range("top alerts from last 3 days", now=now)

    assert resolution.used_default is False
    assert resolution.date_range.label == "last 3 days"
    assert resolution.date_range.start.isoformat() == "2026-08-11T00:00:00+00:00"
    assert (
        resolution.date_range.end.isoformat()
        == "2026-08-13T23:59:59.999999+00:00"
    )


def test_resolve_request_date_range_uses_past_week() -> None:
    """Verify ``past week`` resolves to seven calendar days."""

    now = datetime(2026, 8, 13, 15, 12, tzinfo=UTC)

    resolution = resolve_request_date_range("top alerts from the past week", now=now)

    assert resolution.used_default is False
    assert resolution.date_range.label == "past week"
    assert resolution.date_range.start.isoformat() == "2026-08-07T00:00:00+00:00"
    assert (
        resolution.date_range.end.isoformat()
        == "2026-08-13T23:59:59.999999+00:00"
    )


def test_resolve_request_date_range_defaults_when_no_timestamps() -> None:
    """Verify requests without absolute timestamps use the default range."""

    now = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)

    resolution = resolve_request_date_range("top alerts", now=now)

    assert resolution.used_default is True
    assert resolution.date_range.start.isoformat() == "2026-08-10T12:00:00+00:00"


def test_parse_as_of_datetime_accepts_iso_date() -> None:
    """Verify date-only as-of anchors parse to a stable UTC day anchor."""

    parsed = parse_as_of_datetime("2026-08-11")

    assert parsed.isoformat() == "2026-08-11T12:00:00+00:00"


def test_parse_as_of_datetime_accepts_timezone_aware_datetime() -> None:
    """Verify datetime as-of anchors preserve their explicit timezone."""

    parsed = parse_as_of_datetime("2026-08-11T09:30:00-03:00")

    assert parsed.isoformat() == "2026-08-11T09:30:00-03:00"


def test_parse_as_of_datetime_rejects_naive_datetime() -> None:
    """Verify datetime as-of anchors must include a timezone."""

    with pytest.raises(AlertDateRangeError, match="timezone"):
        parse_as_of_datetime("2026-08-11T09:30:00")
