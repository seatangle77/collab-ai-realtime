from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.time_utils import normalize_datetimes, utc_datetime, utc_iso


def test_utc_iso_marks_naive_datetime_as_utc() -> None:
    value = datetime(2026, 5, 7, 7, 20, 0)

    assert utc_iso(value) == "2026-05-07T07:20:00Z"


def test_utc_iso_keeps_aware_utc_datetime_as_z() -> None:
    value = datetime(2026, 5, 7, 7, 20, 0, tzinfo=timezone.utc)

    assert utc_iso(value) == "2026-05-07T07:20:00Z"


def test_utc_iso_converts_offset_datetime_to_utc_z() -> None:
    value = datetime(2026, 5, 7, 15, 20, 0, tzinfo=timezone(timedelta(hours=8)))

    assert utc_iso(value) == "2026-05-07T07:20:00Z"


def test_normalize_datetimes_recursively_marks_naive_values_as_utc() -> None:
    payload = {
        "created_at": datetime(2026, 5, 7, 7, 20, 0),
        "items": [
            {"window_start": datetime(2026, 5, 7, 7, 21, 0)},
            "unchanged",
        ],
    }

    normalized = normalize_datetimes(payload)

    assert utc_datetime(normalized["created_at"]) == datetime(2026, 5, 7, 7, 20, 0, tzinfo=timezone.utc)
    assert utc_iso(normalized["items"][0]["window_start"]) == "2026-05-07T07:21:00Z"
