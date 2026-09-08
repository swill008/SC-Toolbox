"""Duration formatting helpers.

A single total number of seconds can be presented several ways.  The user
picks a preferred *format* in the tool's settings; the launcher main menu and
the tool headline both render the same total through these helpers so they
always agree.

Formats
-------
``hours``     -> "2,931.4 hrs"          (total hours played)
``days``      -> "122.1 days"
``calendar``  -> "4mo 1w 3d 5h"         (actual elapsed time, human units)

The calendar breakdown uses fixed, documented unit sizes so the result is
deterministic and reproducible:

    1 month = 30 days, 1 week = 7 days, 1 day = 24 h, 1 h = 60 min.
"""
from __future__ import annotations

# Fixed unit sizes (seconds) for the calendar breakdown.
_MINUTE = 60
_HOUR = 60 * _MINUTE
_DAY = 24 * _HOUR
_WEEK = 7 * _DAY
_MONTH = 30 * _DAY

VALID_FORMATS = ("hours", "days", "calendar")

FORMAT_LABELS = {
    "hours": "Total Hours",
    "days": "Total Days",
    "calendar": "Actual Time",
}


def _grp(n: float, decimals: int = 0) -> str:
    """Thousands-grouped number, e.g. 2931.4 -> '2,931.4'."""
    if decimals:
        return f"{n:,.{decimals}f}"
    return f"{int(round(n)):,}"


def fmt_hours(seconds: float, decimals: int = 1) -> str:
    """Total hours, e.g. '2,931.4 hrs'."""
    return f"{_grp(seconds / _HOUR, decimals)} hrs"


def fmt_days(seconds: float, decimals: int = 1) -> str:
    """Total days, e.g. '122.1 days'."""
    return f"{_grp(seconds / _DAY, decimals)} days"


def calendar_parts(seconds: float) -> list[tuple[int, str]]:
    """Break *seconds* into (value, unit) pairs: months, weeks, days, hours,
    minutes.  Zero-valued leading units are dropped; trailing zeros too."""
    s = int(max(0, seconds))
    months, s = divmod(s, _MONTH)
    weeks, s = divmod(s, _WEEK)
    days, s = divmod(s, _DAY)
    hours, s = divmod(s, _HOUR)
    minutes, _s = divmod(s, _MINUTE)
    return [
        (months, "mo"),
        (weeks, "w"),
        (days, "d"),
        (hours, "h"),
        (minutes, "m"),
    ]


def fmt_calendar(seconds: float, max_units: int = 4) -> str:
    """Compact calendar breakdown, e.g. '4mo 1w 3d 5h'.

    Shows the *max_units* most-significant non-zero units (trimming leading
    zeros).  Always returns at least one unit (falls back to minutes/'0m')."""
    parts = calendar_parts(seconds)
    # Drop leading zero units.
    while len(parts) > 1 and parts[0][0] == 0:
        parts.pop(0)
    chunks = [f"{v}{u}" for v, u in parts if v > 0][:max_units]
    if not chunks:
        return "0m"
    return " ".join(chunks)


def fmt_calendar_long(seconds: float, max_units: int = 4) -> str:
    """Verbose calendar breakdown, e.g. '4 months, 1 week, 3 days, 5 hours'."""
    names = {
        "mo": ("month", "months"),
        "w": ("week", "weeks"),
        "d": ("day", "days"),
        "h": ("hour", "hours"),
        "m": ("minute", "minutes"),
    }
    parts = calendar_parts(seconds)
    while len(parts) > 1 and parts[0][0] == 0:
        parts.pop(0)
    chunks = []
    for v, u in parts:
        if v <= 0:
            continue
        singular, plural = names[u]
        chunks.append(f"{v} {singular if v == 1 else plural}")
        if len(chunks) >= max_units:
            break
    if not chunks:
        return "0 minutes"
    return ", ".join(chunks)


def fmt_hms(seconds: float) -> str:
    """Clock-style H:MM:SS for a single session, e.g. '47:52:30'."""
    s = int(max(0, seconds))
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    return f"{h}:{m:02d}:{s:02d}"


def fmt_short(seconds: float) -> str:
    """Compact session length, e.g. '2h 14m', '47m', '38s'."""
    s = int(max(0, seconds))
    if s < 60:
        return f"{s}s"
    h, rem = divmod(s, 3600)
    m, _ = divmod(rem, 60)
    if h and m:
        return f"{h}h {m}m"
    if h:
        return f"{h}h"
    return f"{m}m"


def format_total(seconds: float, fmt: str) -> str:
    """Render the headline total in the user's preferred *fmt*."""
    if fmt == "hours":
        return fmt_hours(seconds)
    if fmt == "days":
        return fmt_days(seconds)
    if fmt == "calendar":
        return fmt_calendar(seconds)
    return fmt_hours(seconds)


def format_badge(seconds: float, fmt: str) -> str:
    """Render the compact badge shown on the launcher main menu."""
    if fmt == "hours":
        return f"{_grp(seconds / _HOUR)} h"
    if fmt == "days":
        return f"{_grp(seconds / _DAY)} d"
    if fmt == "calendar":
        return fmt_calendar(seconds, max_units=3)
    return f"{_grp(seconds / _HOUR)} h"
