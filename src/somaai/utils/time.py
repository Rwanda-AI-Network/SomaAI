"""Time utilities."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

KIGALI_TZ = ZoneInfo("Africa/Kigali")


def utc_now() -> datetime:
    """Get current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


def kigali_now() -> datetime:
    """Get current Kigali time (Africa/Kigali)."""
    return datetime.now(KIGALI_TZ)


def to_kigali(dt: datetime) -> datetime:
    """Convert a datetime to Kigali time.

    Expects a timezone-aware datetime.
    """
    if dt.tzinfo is None:
        raise ValueError("Datetime must be timezone-aware")
    return dt.astimezone(KIGALI_TZ)


def format_timestamp(dt: datetime) -> str:
    """Format a datetime as ISO-8601 string."""
    if dt.tzinfo is None:
        raise ValueError("Datetime must be timezone-aware")
    return dt.isoformat()
