"""Cron due-evaluation for ``automedia cron run --due``.

The unattended contract is ``automedia cron run --due`` — an external systemd
timer (or crond) calls it hourly, and it must dispatch exactly the schedule
entries that are due at that instant.  This module owns the "is it due?" rule.

Why not :mod:`croniter`?  ``croniter`` is not a declared dependency of
AutoMedia (it is imported opportunistically by the cron *display* tools), so a
core unattended contract must not silently depend on it.  This is a
dependency-free evaluator for the standard 5-field syntax.
"""

from __future__ import annotations

from datetime import datetime, timedelta

#: Inclusive ``(low, high)`` bounds for minute, hour, day-of-month, month, day-of-week.
_FIELD_BOUNDS: tuple[tuple[int, int], ...] = (
    (0, 59),  # minute
    (0, 23),  # hour
    (1, 31),  # day of month
    (1, 12),  # month
    (0, 7),  # day of week (0 and 7 are both Sunday)
)

#: Default look-back window, in minutes.  Matches the shipped systemd timer's
#: ``RandomizedDelaySec=300``: a job scheduled for 08:00 is still due when the
#: unit starts at 08:04.
DEFAULT_GRACE_MINUTES = 5


class InvalidCronExpressionError(ValueError):
    """Raised for a field that cannot be parsed as cron syntax."""


def is_schedule_due(
    expression: str,
    now: datetime,
    *,
    grace_minutes: int = DEFAULT_GRACE_MINUTES,
) -> bool:
    """Return whether *expression* fired inside the ``[now - grace, now]`` window.

    A malformed expression returns ``False`` instead of raising so one corrupt
    schedule entry cannot abort the whole due batch.
    """
    if not isinstance(expression, str):
        return False
    fields = expression.split()
    if len(fields) != 5:
        return False

    try:
        return any(
            _matches_minute(fields, now - timedelta(minutes=offset))
            for offset in range(max(grace_minutes, 0) + 1)
        )
    except (ValueError, TypeError):
        return False


def _matches_minute(fields: list[str], moment: datetime) -> bool:
    minute, hour, day_of_month, month, day_of_week = fields

    if not _matches_field(minute, moment.minute, *_FIELD_BOUNDS[0]):
        return False
    if not _matches_field(hour, moment.hour, *_FIELD_BOUNDS[1]):
        return False
    if not _matches_field(month, moment.month, *_FIELD_BOUNDS[3]):
        return False

    dom_ok = _matches_field(day_of_month, moment.day, *_FIELD_BOUNDS[2])
    dow_ok = _matches_day_of_week(day_of_week, moment)

    # Standard cron quirk: when both day fields are restricted, either may match.
    if not _is_unrestricted(day_of_month) and not _is_unrestricted(day_of_week):
        return dom_ok or dow_ok
    return dom_ok and dow_ok


def _matches_day_of_week(field: str, moment: datetime) -> bool:
    # ``datetime.isoweekday()`` is 1=Monday..7=Sunday; cron uses 0 or 7 for Sunday.
    cron_dow = moment.isoweekday() % 7
    if _matches_field(field, cron_dow, *_FIELD_BOUNDS[4]):
        return True
    return cron_dow == 0 and _matches_field(field, 7, *_FIELD_BOUNDS[4])


def _is_unrestricted(field: str) -> bool:
    return field.strip() == "*"


def _matches_field(field: str, value: int, low: int, high: int) -> bool:
    return any(
        _matches_part(part.strip(), value, low, high) for part in field.split(",") if part.strip()
    )


def _matches_part(part: str, value: int, low: int, high: int) -> bool:
    """Match one comma-separated term (``*``, ``n``, ``a-b``, optionally ``/step``)."""
    if not part:
        raise InvalidCronExpressionError("empty cron field term")

    step = 1
    if "/" in part:
        part, _, step_text = part.partition("/")
        step = int(step_text)
        if step <= 0:
            raise InvalidCronExpressionError(f"invalid cron step {step!r}")

    if part == "*":
        start, end = low, high
    elif "-" in part:
        start_text, _, end_text = part.partition("-")
        start, end = int(start_text), int(end_text)
    else:
        start = end = int(part)

    if not low <= start <= end <= high:
        raise InvalidCronExpressionError(f"cron range {start}-{end} outside {low}-{high}")

    return start <= value <= end and (value - start) % step == 0
