from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def utc_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def utc_iso(value: Any) -> Any:
    if isinstance(value, datetime):
        dt = utc_datetime(value)
        if dt is None:
            return None
        return dt.isoformat().replace("+00:00", "Z")
    return value


def normalize_datetimes(value: Any) -> Any:
    if isinstance(value, datetime):
        return utc_datetime(value)
    if isinstance(value, dict):
        return {key: normalize_datetimes(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_datetimes(item) for item in value]
    if isinstance(value, tuple):
        return tuple(normalize_datetimes(item) for item in value)
    return value
