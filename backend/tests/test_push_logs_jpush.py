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
                "SELECT status\n                FROM push_queue",
                [{"status": "delivered"}],
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

    assert resp == {"id": None, "delivery_status": "delivered", "ws_sent": False}
    assert jpush_calls == []
    assert db.commits == 0
    assert len(db.executed) == 1


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

