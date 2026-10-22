"""Cron validation and next-run calculation for scheduled ETL jobs."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class CronExpressionError(ValueError):
    """Raised when an ETL cron expression or timezone is invalid."""


@dataclass(frozen=True)
class _CronField:
    values: frozenset[int]
    unrestricted: bool


_FIELD_RANGES = (
    (0, 59, "minute"),
    (0, 23, "hour"),
    (1, 31, "day of month"),
    (1, 12, "month"),
    (0, 7, "day of week"),
)


def _parse_int(value: str, minimum: int, maximum: int, label: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise CronExpressionError(f"Invalid {label}: {value!r}") from exc
    if number < minimum or number > maximum:
        raise CronExpressionError(
            f"{label.capitalize()} must be between {minimum} and {maximum}"
        )
    return number


def _parse_field(raw: str, minimum: int, maximum: int, label: str) -> _CronField:
    values: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            raise CronExpressionError(f"Empty {label} segment")
        base, slash, step_raw = part.partition("/")
        step = _parse_int(step_raw, 1, maximum - minimum + 1, f"{label} step") if slash else 1
        if base == "*":
            start, end = minimum, maximum
        elif "-" in base:
            start_raw, end_raw = base.split("-", 1)
            start = _parse_int(start_raw, minimum, maximum, label)
            end = _parse_int(end_raw, minimum, maximum, label)
            if start > end:
                raise CronExpressionError(f"Invalid descending {label} range: {base!r}")
        else:
            start = _parse_int(base, minimum, maximum, label)
            end = start
            if slash:
                end = maximum
        values.update(range(start, end + 1, step))
    if label == "day of week" and 7 in values:
        values.discard(7)
        values.add(0)
    full = set(range(minimum, maximum + 1))
    if label == "day of week":
        full.discard(7)
    return _CronField(frozenset(values), values == full)


def parse_cron(expression: str) -> tuple[_CronField, ...]:
    """Parse a standard five-field cron expression."""
    parts = str(expression or "").strip().split()
    if len(parts) != 5:
        raise CronExpressionError(
            "Cron expression must contain exactly 5 fields: minute hour day month weekday"
        )
    return tuple(
        _parse_field(raw, minimum, maximum, label)
        for raw, (minimum, maximum, label) in zip(parts, _FIELD_RANGES)
    )


def validate_timezone(timezone_name: str) -> str:
    name = str(timezone_name or "UTC").strip() or "UTC"
    try:
        ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise CronExpressionError(f"Unknown timezone: {name}") from exc
    return name


def next_cron_run(
    expression: str,
    timezone_name: str = "UTC",
    *,
    after: datetime | None = None,
) -> datetime:
    """Return the next matching instant as an aware UTC datetime."""
    minute, hour, day_of_month, month, day_of_week = parse_cron(expression)
    zone = ZoneInfo(validate_timezone(timezone_name))
    base = after or datetime.now(timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    candidate = base.astimezone(zone).replace(second=0, microsecond=0) + timedelta(minutes=1)

    # Five years covers leap-day schedules while keeping invalid searches bounded.
    max_checks = 5 * 366 * 24 * 60
    for _ in range(max_checks):
        cron_weekday = (candidate.weekday() + 1) % 7
        dom_match = candidate.day in day_of_month.values
        dow_match = cron_weekday in day_of_week.values
        if day_of_month.unrestricted or day_of_week.unrestricted:
            day_matches = dom_match and dow_match
        else:
            # Vixie cron semantics: restricted DOM and DOW fields are ORed.
            day_matches = dom_match or dow_match
        if (
            candidate.minute in minute.values
            and candidate.hour in hour.values
            and candidate.month in month.values
            and day_matches
        ):
            return candidate.astimezone(timezone.utc)
        candidate += timedelta(minutes=1)
    raise CronExpressionError("Cron expression has no matching time within five years")


def calculate_next_run(
    schedule_kind: str,
    cron_expression: str | None,
    timezone_name: str,
    *,
    enabled: bool,
    after: datetime | None = None,
) -> datetime | None:
    if not enabled or schedule_kind != "cron":
        return None
    if not cron_expression:
        raise CronExpressionError("Cron expression is required for cron schedules")
    return next_cron_run(cron_expression, timezone_name, after=after)
