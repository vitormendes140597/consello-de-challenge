"""Absolute date-range parsing and alert filtering."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from datetime import tzinfo as TzInfo

from ai_alert_scorer.schemas import CanonicalizedAlert

ISO_TIMESTAMP_PATTERN = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ][0-9:.]+(?:Z|[+-]\d{2}:\d{2})"
)
ISO_DATE_PATTERN = re.compile(r"(?<!\d)\d{4}-\d{2}-\d{2}(?![T\d])")
TODAY_PATTERN = re.compile(r"\btoday\b", re.IGNORECASE)
YESTERDAY_PATTERN = re.compile(r"\byesterday\b", re.IGNORECASE)
DAYS_AGO_PATTERN = re.compile(r"\b(\d+)\s+days?\s+ago\b", re.IGNORECASE)
FROM_DAYS_AGO_PATTERN = re.compile(
    r"\b(?:from|since)\s+(\d+)\s+days?\s+ago\b", re.IGNORECASE
)
LAST_N_DAYS_PATTERN = re.compile(r"\b(last|past)\s+(\d+)\s+days?\b", re.IGNORECASE)
PAST_WEEK_PATTERN = re.compile(r"\bpast\s+week\b", re.IGNORECASE)
DEFAULT_LOOKBACK_DAYS = 3
PAST_WEEK_DAYS = 7


class AlertDateRangeError(ValueError):
    """Raised when an alert date range cannot be parsed or applied."""


@dataclass(frozen=True)
class AlertDateRange:
    """Inclusive absolute date range for alert filtering.

    Attributes:
        start (datetime): Inclusive timezone-aware start timestamp.
        end (datetime): Inclusive timezone-aware end timestamp.
        label (str): Short user-facing description of the range.
    """

    start: datetime
    end: datetime
    label: str

    def model_payload(self) -> dict[str, str]:
        """Return a JSON-friendly representation of the date range.

        Returns:
            dict[str, str]: Range label and ISO timestamps.
        """

        return {
            "label": self.label,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
        }


@dataclass(frozen=True)
class DateRangeResolution:
    """Date range selected for one chat request.

    Attributes:
        date_range (AlertDateRange): Resolved inclusive alert range.
        used_default (bool): Whether the default three-day range was used.
    """

    date_range: AlertDateRange
    used_default: bool


def build_alert_date_range(
    start_timestamp: str,
    end_timestamp: str,
    label: str = "explicit range",
) -> AlertDateRange:
    """Build an inclusive alert date range from absolute timestamps.

    Args:
        start_timestamp (str): ISO timezone-aware inclusive start timestamp.
        end_timestamp (str): ISO timezone-aware inclusive end timestamp.
        label (str): User-facing label for the range.

    Returns:
        AlertDateRange: Parsed inclusive range.

    Raises:
        AlertDateRangeError: If a timestamp is invalid, lacks a timezone, or
            the start is after the end.
    """

    start = parse_absolute_timestamp(start_timestamp, "start_timestamp")
    end = parse_absolute_timestamp(end_timestamp, "end_timestamp")
    if start > end:
        raise AlertDateRangeError("start_timestamp must be before end_timestamp")
    return AlertDateRange(start=start, end=end, label=label)


def default_alert_date_range(
    now: datetime | None = None,
    days: int = DEFAULT_LOOKBACK_DAYS,
) -> AlertDateRange:
    """Build the default rolling lookback range ending at ``now``.

    Args:
        now (datetime | None): Optional clock override for tests.
        days (int): Number of rolling days to include.

    Returns:
        AlertDateRange: Inclusive default date range.

    Raises:
        AlertDateRangeError: If ``days`` is not positive or ``now`` is naive.
    """

    if days < 1:
        raise AlertDateRangeError("days must be a positive integer")
    end = now or datetime.now(UTC)
    if end.tzinfo is None or end.utcoffset() is None:
        raise AlertDateRangeError("now must include a timezone")
    return AlertDateRange(
        start=end - timedelta(days=days),
        end=end,
        label=f"last {days} days (default)",
    )


def resolve_request_date_range(
    user_input: str,
    now: datetime | None = None,
) -> DateRangeResolution:
    """Resolve explicit or relative dates from text, or fall back to default.

    Args:
        user_input (str): User request that may contain ISO dates,
            timezone-aware timestamps, or supported relative time phrases.
        now (datetime | None): Optional clock override for tests.

    Returns:
        DateRangeResolution: Chosen date range and default flag.

    Raises:
        AlertDateRangeError: If two explicit timestamps are present but invalid.
    """

    timestamps = ISO_TIMESTAMP_PATTERN.findall(user_input)
    if len(timestamps) >= 2:
        return DateRangeResolution(
            date_range=build_alert_date_range(
                start_timestamp=timestamps[0],
                end_timestamp=timestamps[1],
            ),
            used_default=False,
        )
    dates = ISO_DATE_PATTERN.findall(user_input)
    if len(dates) >= 2:
        return DateRangeResolution(
            date_range=build_alert_date_range(
                start_timestamp=f"{dates[0]}T00:00:00+00:00",
                end_timestamp=f"{dates[1]}T23:59:59.999999+00:00",
                label="explicit date range",
            ),
            used_default=False,
        )
    if len(dates) == 1:
        parsed_date = parse_iso_date(dates[0], "date")
        return DateRangeResolution(
            date_range=calendar_day_date_range(parsed_date, "explicit date"),
            used_default=False,
        )

    relative_date_range = resolve_relative_date_range(user_input, now=now)
    if relative_date_range is not None:
        return DateRangeResolution(
            date_range=relative_date_range,
            used_default=False,
        )
    return DateRangeResolution(
        date_range=default_alert_date_range(now=now),
        used_default=True,
    )


def filter_alerts_by_date_range(
    alerts: list[CanonicalizedAlert],
    date_range: AlertDateRange,
) -> list[CanonicalizedAlert]:
    """Filter alerts by inclusive ``received_at`` timestamp bounds.

    Args:
        alerts (list[CanonicalizedAlert]): Candidate alerts.
        date_range (AlertDateRange): Inclusive absolute date range.

    Returns:
        list[CanonicalizedAlert]: Alerts received inside the range.

    Raises:
        AlertDateRangeError: If an alert timestamp is invalid or naive.
    """

    filtered_alerts: list[CanonicalizedAlert] = []
    for alert in alerts:
        received_at = parse_absolute_timestamp(alert.received_at, "received_at")
        if date_range.start <= received_at <= date_range.end:
            filtered_alerts.append(alert)
    return filtered_alerts


def parse_absolute_timestamp(value: str, field_name: str) -> datetime:
    """Parse one ISO timezone-aware timestamp.

    Args:
        value (str): ISO timestamp, for example ``2026-08-11T00:00:00Z``.
        field_name (str): Name used in validation error messages.

    Returns:
        datetime: Parsed timezone-aware timestamp.

    Raises:
        AlertDateRangeError: If ``value`` is invalid or lacks a timezone.
    """

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AlertDateRangeError(
            f"{field_name} must be an ISO timezone-aware timestamp: {value!r}"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AlertDateRangeError(f"{field_name} must include a timezone")
    return parsed


def parse_as_of_datetime(value: str) -> datetime:
    """Parse a CLI ``--as-of`` value.

    Args:
        value (str): ISO date or timezone-aware ISO datetime.

    Returns:
        datetime: Timezone-aware anchor datetime.

    Raises:
        AlertDateRangeError: If ``value`` is not an ISO date or aware
            datetime.
    """

    if ISO_DATE_PATTERN.fullmatch(value):
        return datetime.combine(parse_iso_date(value, "as_of"), time(12), tzinfo=UTC)
    return parse_absolute_timestamp(value, "as_of")


def parse_iso_date(value: str, field_name: str) -> date:
    """Parse one ISO date.

    Args:
        value (str): Date in ``YYYY-MM-DD`` format.
        field_name (str): Name used in validation error messages.

    Returns:
        date: Parsed date.

    Raises:
        AlertDateRangeError: If ``value`` is not a valid ISO date.
    """

    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise AlertDateRangeError(
            f"{field_name} must be an ISO date: {value!r}"
        ) from exc


def resolve_relative_date_range(
    user_input: str,
    now: datetime | None = None,
) -> AlertDateRange | None:
    """Resolve supported relative date phrases from user text.

    Args:
        user_input (str): User request text.
        now (datetime | None): Optional timezone-aware relative-time anchor.

    Returns:
        AlertDateRange | None: Resolved relative date range when a supported
        phrase is present, otherwise ``None``.

    Raises:
        AlertDateRangeError: If ``now`` is naive or a parsed day count is
            invalid.
    """

    anchor = now or datetime.now(UTC)
    if anchor.tzinfo is None or anchor.utcoffset() is None:
        raise AlertDateRangeError("now must include a timezone")

    from_days_ago = FROM_DAYS_AGO_PATTERN.search(user_input)
    if from_days_ago:
        days = _parse_positive_day_count(from_days_ago.group(1))
        return rolling_lookback_date_range(
            anchor=anchor,
            days=days,
            label=f"from {days} day{'s' if days != 1 else ''} ago",
        )

    last_n_days = LAST_N_DAYS_PATTERN.search(user_input)
    if last_n_days:
        label_prefix = last_n_days.group(1).lower()
        days = _parse_positive_day_count(last_n_days.group(2))
        return rolling_calendar_days_date_range(
            anchor=anchor,
            days=days,
            label=f"{label_prefix} {days} day{'s' if days != 1 else ''}",
        )

    if PAST_WEEK_PATTERN.search(user_input):
        return rolling_calendar_days_date_range(
            anchor=anchor,
            days=PAST_WEEK_DAYS,
            label="past week",
        )

    if YESTERDAY_PATTERN.search(user_input):
        return calendar_day_date_range(
            (anchor - timedelta(days=1)).date(),
            label="yesterday",
            tzinfo=anchor.tzinfo,
        )

    if TODAY_PATTERN.search(user_input):
        return calendar_day_date_range(
            anchor.date(),
            label="today",
            tzinfo=anchor.tzinfo,
        )

    days_ago = DAYS_AGO_PATTERN.search(user_input)
    if days_ago:
        days = _parse_positive_day_count(days_ago.group(1))
        return calendar_day_date_range(
            (anchor - timedelta(days=days)).date(),
            label=f"{days} day{'s' if days != 1 else ''} ago",
            tzinfo=anchor.tzinfo,
        )

    return None


def rolling_lookback_date_range(
    anchor: datetime,
    days: int,
    label: str,
) -> AlertDateRange:
    """Build a rolling lookback range ending at the anchor timestamp.

    Args:
        anchor (datetime): Timezone-aware relative-time anchor.
        days (int): Number of 24-hour periods to include before the anchor.
        label (str): User-facing label for the range.

    Returns:
        AlertDateRange: Inclusive rolling lookback range.

    Raises:
        AlertDateRangeError: If ``days`` is not positive or ``anchor`` is naive.
    """

    if days < 1:
        raise AlertDateRangeError("days must be a positive integer")
    if anchor.tzinfo is None or anchor.utcoffset() is None:
        raise AlertDateRangeError("anchor must include a timezone")
    return AlertDateRange(
        start=anchor - timedelta(days=days),
        end=anchor,
        label=label,
    )


def rolling_calendar_days_date_range(
    anchor: datetime,
    days: int,
    label: str,
) -> AlertDateRange:
    """Build a range covering calendar days through the anchor date.

    Args:
        anchor (datetime): Timezone-aware relative-time anchor.
        days (int): Number of calendar days to include.
        label (str): User-facing label for the range.

    Returns:
        AlertDateRange: Inclusive full-day calendar range.

    Raises:
        AlertDateRangeError: If ``days`` is not positive or ``anchor`` is naive.
    """

    if days < 1:
        raise AlertDateRangeError("days must be a positive integer")
    if anchor.tzinfo is None or anchor.utcoffset() is None:
        raise AlertDateRangeError("anchor must include a timezone")
    start_date = anchor.date() - timedelta(days=days - 1)
    start = datetime.combine(start_date, time.min, tzinfo=anchor.tzinfo)
    end = datetime.combine(anchor.date(), time.max, tzinfo=anchor.tzinfo)
    return AlertDateRange(start=start, end=end, label=label)


def calendar_day_date_range(
    target_date: date,
    label: str,
    tzinfo: TzInfo = UTC,
) -> AlertDateRange:
    """Build a range covering one full calendar day.

    Args:
        target_date (date): Calendar date to include.
        label (str): User-facing label for the range.
        tzinfo (object): Timezone used for day boundaries.

    Returns:
        AlertDateRange: Inclusive full-day date range.
    """

    return AlertDateRange(
        start=datetime.combine(target_date, time.min, tzinfo=tzinfo),
        end=datetime.combine(target_date, time.max, tzinfo=tzinfo),
        label=label,
    )


def _parse_positive_day_count(value: str) -> int:
    days = int(value)
    if days < 1:
        raise AlertDateRangeError("days must be a positive integer")
    return days


__all__ = [
    "AlertDateRange",
    "AlertDateRangeError",
    "DateRangeResolution",
    "build_alert_date_range",
    "calendar_day_date_range",
    "default_alert_date_range",
    "filter_alerts_by_date_range",
    "parse_as_of_datetime",
    "parse_absolute_timestamp",
    "parse_iso_date",
    "resolve_request_date_range",
    "resolve_relative_date_range",
    "rolling_lookback_date_range",
    "rolling_calendar_days_date_range",
]
