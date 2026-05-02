from __future__ import annotations

import asyncio
import importlib
import sys
import types
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.modules.setdefault("jpush", types.ModuleType("jpush"))

push_logs = importlib.import_module("app.push_logs")


class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self._rows = rows or []

    def mappings(self) -> "_FakeResult":
        return self

    def first(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def one(self) -> dict[str, Any]:
        if len(self._rows) != 1:
            raise AssertionError(f"expected exactly one row, got {len(self._rows)}")
        return self._rows[0]

    def all(self) -> list[dict[str, Any]]:
        return self._rows


class _FakeDB:
    def __init__(self, handlers: list[tuple[str, Any]]) -> None:
        self._handlers = handlers
        self.executed: list[tuple[str, dict[str, Any] | None]] = []
        self.commits = 0

    async def execute(self, statement: Any, params: dict[str, Any] | None = None) -> _FakeResult:
        sql = str(statement)
        self.executed.append((sql, params))
        for needle, result in self._handlers:
            if needle in sql:
                rows = result(sql, params) if callable(result) else result
                return _FakeResult(rows)
        raise AssertionError(f"unexpected SQL: {sql}")

    async def commit(self) -> None:
        self.commits += 1


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def test_jpush_safe_swallows_sender_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str, str]] = []

    def _boom(device_token: str, content: str, title: str) -> None:
        calls.append((device_token, content, title))
        raise RuntimeError("jpush failed")

    monkeypatch.setattr(push_logs, "send_push_to_registration_id", _boom)

    _run(push_logs._jpush_safe("tok-1", "内容", "标题"))

    assert calls == [("tok-1", "内容", "标题")]


def test_push_notify_calls_jpush_when_target_has_device_token(monkeypatch: pytest.MonkeyPatch) -> None:
    jpush_calls: list[tuple[str, str, str]] = []
    ws_calls: list[tuple[str, str, dict[str, Any]]] = []
    triggered_at = datetime(2026, 4, 23, 12, 0, 0)
    db = _FakeDB(
        [
            ("INSERT INTO push_logs", [{"triggered_at": triggered_at}]),
            ("UPDATE push_logs SET delivery_status", []),
            ("SELECT device_token FROM users_info", [{"device_token": "dev-token-u1"}]),
        ]
    )

    async def _fake_send_to_user(session_id: str, user_id: str, message: dict[str, Any]) -> bool:
        ws_calls.append((session_id, user_id, message))
        return True

    async def _fake_jpush(device_token: str, content: str, title: str) -> None:
        jpush_calls.append((device_token, content, title))

    monkeypatch.setattr(push_logs.ws_manager, "send_to_user", _fake_send_to_user)
    monkeypatch.setattr(push_logs, "_jpush_safe", _fake_jpush)

    payload = push_logs.PushNotifyIn(target_user_id="u1", content="请主动补充理由")
    resp = _run(push_logs.push_notify("s1", payload, db))

    assert resp["delivery_status"] == "delivered"
    assert resp["ws_sent"] is True
    assert ws_calls and ws_calls[0][0:2] == ("s1", "u1")
    assert jpush_calls == [("dev-token-u1", "请主动补充理由", "AI 讨论建议")]
    assert db.commits == 2


def test_push_notify_skips_jpush_when_target_has_no_device_token(monkeypatch: pytest.MonkeyPatch) -> None:
    jpush_calls: list[tuple[str, str, str]] = []
    db = _FakeDB(
        [
            ("INSERT INTO push_logs", [{"triggered_at": datetime(2026, 4, 23, 12, 5, 0)}]),
            ("UPDATE push_logs SET delivery_status", []),
            ("SELECT device_token FROM users_info", [{"device_token": None}]),
        ]
    )

    async def _fake_send_to_user(session_id: str, user_id: str, message: dict[str, Any]) -> bool:
        return False

    async def _fake_jpush(device_token: str, content: str, title: str) -> None:
        jpush_calls.append((device_token, content, title))

    monkeypatch.setattr(push_logs.ws_manager, "send_to_user", _fake_send_to_user)
    monkeypatch.setattr(push_logs, "_jpush_safe", _fake_jpush)

    payload = push_logs.PushNotifyIn(target_user_id="u2", content="这里可以展开说说")
    resp = _run(push_logs.push_notify("s2", payload, db))

    assert resp["delivery_status"] == "failed"
    assert resp["ws_sent"] is False
    assert jpush_calls == []
    assert db.commits == 2


def test_push_notify_terminal_queue_status_returns_early_without_jpush(monkeypatch: pytest.MonkeyPatch) -> None:
    jpush_calls: list[tuple[str, str, str]] = []
    db = _FakeDB(
        [
            (
                "FROM push_queue",
                [{"status": "delivered", "content_embedding": None}],
            ),
        ]
    )

    async def _fake_jpush(device_token: str, content: str, title: str) -> None:
        jpush_calls.append((device_token, content, title))

    monkeypatch.setattr(push_logs, "_jpush_safe", _fake_jpush)

    payload = push_logs.PushNotifyIn(
        target_user_id="u3",
        content="重复内容不应再发送",
        queue_id="q1",
    )
    resp = _run(push_logs.push_notify("s3", payload, db))

    assert resp == {
        "id": None,
        "delivery_status": "delivered",
        "delivery_reason": "queue_already_final",
        "ws_sent": False,
    }
    assert jpush_calls == []
    assert db.commits == 0
    assert len(db.executed) == 1


def test_push_notify_writes_queue_id_to_push_logs_insert(monkeypatch: pytest.MonkeyPatch) -> None:
    """push_notify 携带 queue_id 时，INSERT SQL 中 queue_id 应正确写入。"""
    triggered_at = datetime(2026, 4, 23, 12, 0, 0)
    db = _FakeDB(
        [
            ("FROM push_queue", []),
            ("INSERT INTO push_logs", [{"triggered_at": triggered_at}]),
            ("UPDATE push_logs SET delivery_status", []),
            ("SELECT device_token FROM users_info", [{"device_token": None}]),
        ]
    )

    async def _fake_send_to_user(session_id: str, user_id: str, message: Any) -> bool:
        return True

    monkeypatch.setattr(push_logs.ws_manager, "send_to_user", _fake_send_to_user)

    payload = push_logs.PushNotifyIn(
        target_user_id="u_qid",
        content="带 queue_id 的推送",
        queue_id="pq_test_001",
    )
    _run(push_logs.push_notify("s_qid", payload, db))

    insert_sql, insert_params = next(
        (sql, params) for sql, params in db.executed if "INSERT INTO push_logs" in sql
    )
    assert "queue_id" in insert_sql, "INSERT SQL 应包含 queue_id 字段"
    assert insert_params is not None
    assert insert_params.get("queue_id") == "pq_test_001"


def test_push_notify_writes_null_queue_id_when_not_provided(monkeypatch: pytest.MonkeyPatch) -> None:
    """push_notify 不传 queue_id 时，INSERT SQL 中 queue_id 应为 None。"""
    triggered_at = datetime(2026, 4, 23, 12, 0, 0)
    db = _FakeDB(
        [
            ("INSERT INTO push_logs", [{"triggered_at": triggered_at}]),
            ("UPDATE push_logs SET delivery_status", []),
            ("SELECT device_token FROM users_info", [{"device_token": None}]),
        ]
    )

    async def _fake_send_to_user(session_id: str, user_id: str, message: Any) -> bool:
        return True

    monkeypatch.setattr(push_logs.ws_manager, "send_to_user", _fake_send_to_user)

    payload = push_logs.PushNotifyIn(
        target_user_id="u_no_qid",
        content="不带 queue_id 的推送",
    )
    _run(push_logs.push_notify("s_no_qid", payload, db))

    _, insert_params = next(
        (sql, params) for sql, params in db.executed if "INSERT INTO push_logs" in sql
    )
    assert insert_params is not None
    assert insert_params.get("queue_id") is None


def test_push_notify_ghost_queue_id_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    """push_notify 传入 push_queue 中不存在的 queue_id 时（孤立 queue_id），
    push_queue 状态查询返回空，应正常走投递流程，不报错。
    注意：外键约束为 ON DELETE SET NULL，插入时若 push_queue 中无对应记录
    会触发 FK 违反——此用例验证 _FakeDB 层行为，实际需在集成环境中额外确认。"""
    triggered_at = datetime(2026, 4, 23, 12, 0, 0)
    db = _FakeDB(
        [
            # push_queue 查询返回空（该 queue_id 不存在）
            ("FROM push_queue", []),
            ("INSERT INTO push_logs", [{"triggered_at": triggered_at}]),
            ("UPDATE push_logs SET delivery_status", []),
            ("SELECT device_token FROM users_info", [{"device_token": None}]),
        ]
    )

    async def _fake_send_to_user(session_id: str, user_id: str, message: Any) -> bool:
        return True

    monkeypatch.setattr(push_logs.ws_manager, "send_to_user", _fake_send_to_user)

    payload = push_logs.PushNotifyIn(
        target_user_id="u_ghost",
        content="孤立 queue_id 的推送",
        queue_id="pq_ghost_999",
    )
    resp = _run(push_logs.push_notify("s_ghost", payload, db))

    # push_queue 不存在时，跳过状态检查，正常投递
    assert resp["delivery_status"] in ("delivered", "failed")
    assert resp["ws_sent"] is True


def test_push_notify_copies_content_embedding_from_push_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    """push_notify 携带 queue_id 时，push_queue 中的 content_embedding 应写入 INSERT SQL。"""
    triggered_at = datetime(2026, 4, 23, 12, 0, 0)
    embedding = [0.1, 0.2, 0.3]
    db = _FakeDB(
        [
            ("FROM push_queue", [{"status": "pending", "content_embedding": embedding}]),
            ("INSERT INTO push_logs", [{"triggered_at": triggered_at}]),
            ("UPDATE push_logs SET delivery_status", []),
            ("SELECT device_token FROM users_info", [{"device_token": None}]),
        ]
    )

    async def _fake_send_to_user(session_id: str, user_id: str, message: Any) -> bool:
        return True

    monkeypatch.setattr(push_logs.ws_manager, "send_to_user", _fake_send_to_user)

    payload = push_logs.PushNotifyIn(
        target_user_id="u_emb",
        content="含 embedding 的推送",
        queue_id="pq_emb_001",
    )
    _run(push_logs.push_notify("s_emb", payload, db))

    _, insert_params = next(
        (sql, params) for sql, params in db.executed if "INSERT INTO push_logs" in sql
    )
    assert insert_params is not None
    assert insert_params.get("content_embedding") == embedding, (
        f"期望 content_embedding={embedding}，实际={insert_params.get('content_embedding')}"
    )


def test_push_notify_writes_null_embedding_when_no_queue_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """push_notify 不传 queue_id 时，INSERT SQL 中 content_embedding 应为 None。"""
    triggered_at = datetime(2026, 4, 23, 12, 0, 0)
    db = _FakeDB(
        [
            ("INSERT INTO push_logs", [{"triggered_at": triggered_at}]),
            ("UPDATE push_logs SET delivery_status", []),
            ("SELECT device_token FROM users_info", [{"device_token": None}]),
        ]
    )

    async def _fake_send_to_user(session_id: str, user_id: str, message: Any) -> bool:
        return True

    monkeypatch.setattr(push_logs.ws_manager, "send_to_user", _fake_send_to_user)

    payload = push_logs.PushNotifyIn(
        target_user_id="u_no_emb",
        content="不带 queue_id 的推送，embedding 应为空",
    )
    _run(push_logs.push_notify("s_no_emb", payload, db))

    _, insert_params = next(
        (sql, params) for sql, params in db.executed if "INSERT INTO push_logs" in sql
    )
    assert insert_params is not None
    assert insert_params.get("content_embedding") is None


def test_group_notify_calls_jpush_for_all_active_member_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    jpush_calls: list[tuple[str, str, str]] = []
    broadcast_calls: list[tuple[str, dict[str, Any]]] = []
    online_user_ids = ["u-online-1", "u-online-2"]
    inserted_rows = iter(
        [
            [{"id": "pl1", "triggered_at": datetime(2026, 4, 23, 13, 0, 0)}],
            [{"id": "pl2", "triggered_at": datetime(2026, 4, 23, 13, 0, 1)}],
        ]
    )
    db = _FakeDB(
        [
            ("INSERT INTO push_logs", lambda _sql, _params: next(inserted_rows)),
            ("UPDATE push_logs SET delivery_status", []),
            (
                "SELECT u.device_token",
                [
                    {"device_token": "tok-online-1"},
                    {"device_token": "tok-offline-1"},
                    {"device_token": "tok-online-2"},
                ],
            ),
        ]
    )

    monkeypatch.setattr(push_logs.ws_manager, "get_online_user_ids", lambda _session_id: online_user_ids)

    async def _fake_broadcast(session_id: str, message: dict[str, Any]) -> None:
        broadcast_calls.append((session_id, message))

    async def _fake_jpush(device_token: str, content: str, title: str) -> None:
        jpush_calls.append((device_token, content, title))

    monkeypatch.setattr(push_logs.ws_manager, "broadcast_to_session", _fake_broadcast)
    monkeypatch.setattr(push_logs, "_jpush_safe", _fake_jpush)

    payload = push_logs.GroupNotifyIn(content="大家先对齐一下当前的目标")
    resp = _run(push_logs.group_notify("s-group", payload, db))

    assert resp["delivery_status"] == "delivered"
    assert resp["online_connections"] == 2
    assert broadcast_calls and broadcast_calls[0][0] == "s-group"
    assert jpush_calls == [
        ("tok-online-1", "大家先对齐一下当前的目标", "AI 讨论建议"),
        ("tok-offline-1", "大家先对齐一下当前的目标", "AI 讨论建议"),
        ("tok-online-2", "大家先对齐一下当前的目标", "AI 讨论建议"),
    ]
    assert db.commits == 2


def test_group_notify_skips_jpush_when_no_active_member_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    jpush_calls: list[tuple[str, str, str]] = []
    db = _FakeDB(
        [
            ("INSERT INTO push_logs", [{"id": "pl1", "triggered_at": datetime(2026, 4, 23, 13, 10, 0)}]),
            ("UPDATE push_logs SET delivery_status", []),
            ("SELECT u.device_token", []),
        ]
    )

    monkeypatch.setattr(push_logs.ws_manager, "get_online_user_ids", lambda _session_id: ["u1"])

    async def _fake_broadcast(session_id: str, message: dict[str, Any]) -> None:
        return None

    async def _fake_jpush(device_token: str, content: str, title: str) -> None:
        jpush_calls.append((device_token, content, title))

    monkeypatch.setattr(push_logs.ws_manager, "broadcast_to_session", _fake_broadcast)
    monkeypatch.setattr(push_logs, "_jpush_safe", _fake_jpush)

    payload = push_logs.GroupNotifyIn(content="测试群发")
    resp = _run(push_logs.group_notify("s-no-token", payload, db))

    assert resp["delivery_status"] == "delivered"
    assert resp["online_connections"] == 1
    assert jpush_calls == []


def test_group_notify_keeps_success_when_jpush_sender_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    sent_tokens: list[str] = []
    db = _FakeDB(
        [
            ("INSERT INTO push_logs", [{"id": "pl9", "triggered_at": datetime(2026, 4, 23, 13, 20, 0)}]),
            ("UPDATE push_logs SET delivery_status", []),
            (
                "SELECT u.device_token",
                [
                    {"device_token": "tok-ok"},
                    {"device_token": "tok-fail"},
                ],
            ),
        ]
    )

    monkeypatch.setattr(push_logs.ws_manager, "get_online_user_ids", lambda _session_id: ["u1"])

    async def _fake_broadcast(session_id: str, message: dict[str, Any]) -> None:
        return None

    def _fake_sender(device_token: str, content: str, title: str) -> None:
        sent_tokens.append(device_token)
        if device_token == "tok-fail":
            raise RuntimeError("boom")

    monkeypatch.setattr(push_logs.ws_manager, "broadcast_to_session", _fake_broadcast)
    monkeypatch.setattr(push_logs, "send_push_to_registration_id", _fake_sender)

    payload = push_logs.GroupNotifyIn(content="异常时也不应影响主流程")
    resp = _run(push_logs.group_notify("s-jpush-error", payload, db))

    assert resp["delivery_status"] == "delivered"
    assert resp["online_connections"] == 1
    assert sent_tokens == ["tok-ok", "tok-fail"]
