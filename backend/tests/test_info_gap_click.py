from __future__ import annotations

import asyncio
import importlib
import sys
import types
from typing import Any

import pytest

sys.modules.setdefault("jpush", types.ModuleType("jpush"))

info_gap = importlib.import_module("app.info_gap")


class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self._rows = rows or []

    def mappings(self) -> "_FakeResult":
        return self

    def first(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

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


def test_click_info_gap_uses_keyword_prefix_for_push_log_and_jpush(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    jpush_calls: list[tuple[str, str, str]] = []
    generated_content = "可以理解为一种故意打破常规表达的玩笑方式"
    display_content = f"搞抽象：{generated_content}"
    db = _FakeDB(
        [
            ("SELECT 1 FROM chat_sessions", [{"ok": 1}]),
            (
                "UPDATE info_gap_buttons",
                [{"id": "igb_1", "keyword": "搞抽象", "skw_score": 0.42}],
            ),
            ("SELECT explanation FROM info_gap_buttons", []),
            ("SELECT content", [{"content": "大家正在讨论表达方式"}]),
            ("FROM speech_transcripts", [{"speaker_id": "u2", "text": "这个说法有点搞抽象"}]),
            ("SELECT name, device_token FROM users_info", [{"name": "Terry", "device_token": "dev-token"}]),
            ("UPDATE info_gap_buttons SET explanation", []),
            ("INSERT INTO push_logs", []),
            ("UPDATE push_logs", []),
        ]
    )

    async def _fake_generate_push_content(**_: Any) -> str:
        return generated_content

    def _fake_send_push_to_registration_id(device_token: str, content: str, title: str) -> None:
        jpush_calls.append((device_token, content, title))

    monkeypatch.setattr(info_gap.nlp_push_content, "generate_push_content", _fake_generate_push_content)
    monkeypatch.setattr(info_gap, "send_push_to_registration_id", _fake_send_push_to_registration_id)

    response = _run(
        info_gap.click_info_gap_button(
            "session_1",
            info_gap.ClickRequest(button_id="igb_1"),
            db,
            {"id": "u1"},
        )
    )

    assert response.success is True
    assert response.keyword == "搞抽象"
    assert response.content == generated_content

    explanation_update = next(params for sql, params in db.executed if "UPDATE info_gap_buttons SET explanation" in sql)
    assert explanation_update == {"exp": generated_content, "id": "igb_1"}

    push_log_insert = next(params for sql, params in db.executed if "INSERT INTO push_logs" in sql)
    assert push_log_insert is not None
    assert push_log_insert["content"] == display_content

    assert jpush_calls == [("dev-token", display_content, "")]
