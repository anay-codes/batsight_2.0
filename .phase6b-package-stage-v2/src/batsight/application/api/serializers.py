"""Application API value normalization helpers."""

from datetime import datetime, timezone


def utc_datetime(value: datetime) -> datetime:
    """SQLite returns naive timestamps; interpret persisted values as UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
