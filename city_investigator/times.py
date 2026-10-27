"""Parse the city's timestamps into timezone-aware UTC datetimes.

311 and DOB times are New York local time without an offset. FloodNet times are UTC.
Mixing them up shifts flood matches by four or five hours.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from city_investigator.config import TIMEZONE

LOCAL = ZoneInfo(TIMEZONE)
FORMATS = ("%m/%d/%Y %H:%M:%S", "%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y")


def parse(value: object, source_tz: str = "local") -> datetime | None:
    """Parse ISO or MM/DD/YYYY text; source_tz is "local" (New York) or "utc"."""
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    parsed: datetime | None = None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        for fmt in FORMATS:
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc if source_tz == "utc" else LOCAL)
    return parsed.astimezone(timezone.utc)


def local_day_start(day: date) -> datetime:
    return datetime.combine(day, time.min, LOCAL).astimezone(timezone.utc)


def local_day_end(day: date) -> datetime:
    return datetime.combine(day, time.max, LOCAL).astimezone(timezone.utc)


def to_local(moment: datetime) -> datetime:
    return moment.astimezone(LOCAL)


def now() -> datetime:
    return datetime.now(timezone.utc)
