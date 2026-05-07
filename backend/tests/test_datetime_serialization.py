from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys
import types


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.admin.push_logs import AdminPushLogOut
from app.admin.window_metrics import AdminWindowMetricOut
from app.api_model import ApiModel
from app.groups import GroupDetail
from app.time_utils import normalize_datetimes


class ExampleSessionOut(ApiModel):
    id: str
    created_at: datetime
    last_updated: datetime


def test_api_model_serializes_naive_datetimes_with_z() -> None:
    payload = ExampleSessionOut(
        id="s1",
        created_at=datetime(2026, 5, 7, 7, 20, 0),
        last_updated=datetime(2026, 5, 7, 7, 21, 0),
    )

    serialized = payload.model_dump_json()

    assert '"created_at":"2026-05-07T07:20:00Z"' in serialized
    assert '"last_updated":"2026-05-07T07:21:00Z"' in serialized
    assert "2026-05-07T07:20:00\"" not in serialized


def test_admin_datetime_response_models_serialize_with_z() -> None:
    push_log = AdminPushLogOut(
        id="p1",
        session_id="s1",
        push_channel="web",
        delivery_status="delivered",
        triggered_at=datetime(2026, 5, 7, 7, 20, 0),
    )
    metric = AdminWindowMetricOut(
        id="wm1",
        session_id="s1",
        user_id="u1",
        window_start=datetime(2026, 5, 7, 7, 20, 0),
        window_end=datetime(2026, 5, 7, 7, 21, 0),
    )

    assert '"triggered_at":"2026-05-07T07:20:00Z"' in push_log.model_dump_json()
    metric_json = metric.model_dump_json()
    assert '"window_start":"2026-05-07T07:20:00Z"' in metric_json
    assert '"window_end":"2026-05-07T07:21:00Z"' in metric_json


def test_group_detail_nested_datetime_serializes_with_z_after_normalization() -> None:
    detail = GroupDetail(
        group=normalize_datetimes({"id": "g1", "created_at": datetime(2026, 5, 7, 7, 20, 0)}),
        member_count=0,
        members=[],
    )

    assert '"created_at":"2026-05-07T07:20:00Z"' in detail.model_dump_json()


def test_transcript_ws_payload_serializes_datetimes_with_z(monkeypatch) -> None:
    redis_module = types.ModuleType("redis")
    redis_asyncio_module = types.ModuleType("redis.asyncio")

    class Redis:
        pass

    redis_asyncio_module.Redis = Redis
    redis_module.asyncio = redis_asyncio_module
    monkeypatch.setitem(sys.modules, "redis", redis_module)
    monkeypatch.setitem(sys.modules, "redis.asyncio", redis_asyncio_module)

    from app.transcript_realtime import _row_to_ws_payload

    payload = _row_to_ws_payload(
        {
            "transcript_id": "tr1",
            "group_id": "g1",
            "session_id": "s1",
            "start": datetime(2026, 5, 7, 7, 20, 0),
            "end": datetime(2026, 5, 7, 7, 21, 0),
            "created_at": datetime(2026, 5, 7, 7, 22, 0),
        }
    )

    assert payload["start"] == "2026-05-07T07:20:00Z"
    assert payload["end"] == "2026-05-07T07:21:00Z"
    assert payload["created_at"] == "2026-05-07T07:22:00Z"
