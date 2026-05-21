"""
concepts.lookup_concept 单元测试

覆盖：
- 缓存命中 → 不调模型，直接返回
- 缓存未命中 → 调模型，写缓存后返回
- 模型失败 / 超时 → 返回空内容，不排后台任务
- session_id 非成员 → 403
- button_id 不属于该 session/user → 404
- 后台任务：按钮状态更新 pending→clicked
- 后台任务：写 push_logs 并发 JPush
"""
from __future__ import annotations

import asyncio
import importlib
import sys
import types
from typing import Any

import pytest
from starlette.background import BackgroundTasks

sys.modules.setdefault("jpush", types.ModuleType("jpush"))

concepts = importlib.import_module("app.concepts")


# ── 公共 Fake 工具 ─────────────────────────────────────────────────────────────

class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self._rows = rows or []

    def mappings(self) -> "_FakeResult":
        return self

    def first(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None


class _FakeDB:
    """主请求里用的同步 DB，不需要 async with。"""
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


class _BgDB:
    """后台任务里用的 async context manager DB。"""
    def __init__(self, device_token: str | None = None) -> None:
        self._device_token = device_token
        self.executed: list[tuple[str, dict[str, Any] | None]] = []
        self.commits = 0

    async def execute(self, statement: Any, params: dict[str, Any] | None = None) -> _FakeResult:
        sql = str(statement)
        self.executed.append((sql, params))
        if "SELECT device_token" in sql:
            return _FakeResult([{"device_token": self._device_token}] if self._device_token else [{}])
        return _FakeResult([])

    async def commit(self) -> None:
        self.commits += 1

    async def __aenter__(self) -> "_BgDB":
        return self

    async def __aexit__(self, *_: Any) -> None:
        pass


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


# ── 正常查询链路 ──────────────────────────────────────────────────────────────

def test_cache_hit_returns_immediately_without_model_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """缓存命中 → 不调模型，直接返回缓存内容。"""
    model_calls: list[str] = []
    db = _FakeDB([
        ("SELECT 1 FROM chat_sessions", [{"ok": 1}]),
        ("SELECT 1 FROM info_gap_buttons", [{"ok": 1}]),
    ])

    async def fake_get_cache(keyword: str) -> str | None:
        return "量化宽松：央行购买资产向市场注入资金的货币政策。"

    async def fake_generate(keyword: str) -> str:
        model_calls.append(keyword)
        return ""

    monkeypatch.setattr(concepts, "_get_from_cache", fake_get_cache)
    monkeypatch.setattr(concepts, "_generate_explanation", fake_generate)

    response = _run(
        concepts.lookup_concept(
            concepts.ConceptLookupRequest(keyword="量化宽松", button_id="btn_1", session_id="sess_1"),
            BackgroundTasks(),
            db,
            {"id": "u1"},
        )
    )

    assert response.keyword == "量化宽松"
    assert "量化宽松" in response.content
    assert model_calls == []


def test_cache_miss_calls_model_and_caches_result(monkeypatch: pytest.MonkeyPatch) -> None:
    """缓存未命中 → 调模型，写缓存，返回模型结果。"""
    cached: dict[str, str] = {}
    db = _FakeDB([
        ("SELECT 1 FROM chat_sessions", [{"ok": 1}]),
        ("SELECT 1 FROM info_gap_buttons", [{"ok": 1}]),
    ])

    async def fake_get_cache(keyword: str) -> str | None:
        return cached.get(keyword)

    async def fake_set_cache(keyword: str, content: str) -> None:
        cached[keyword] = content

    async def fake_generate(keyword: str) -> str:
        return "内卷：内部过度竞争导致效率下降的社会现象。"

    monkeypatch.setattr(concepts, "_get_from_cache", fake_get_cache)
    monkeypatch.setattr(concepts, "_set_cache", fake_set_cache)
    monkeypatch.setattr(concepts, "_generate_explanation", fake_generate)

    response = _run(
        concepts.lookup_concept(
            concepts.ConceptLookupRequest(keyword="内卷", button_id="btn_2", session_id="sess_1"),
            BackgroundTasks(),
            db,
            {"id": "u1"},
        )
    )

    assert response.content == "内卷：内部过度竞争导致效率下降的社会现象。"
    assert cached.get("内卷") == "内卷：内部过度竞争导致效率下降的社会现象。"


# ── 模型失败处理 ──────────────────────────────────────────────────────────────

def test_model_failure_returns_empty_without_background_task(monkeypatch: pytest.MonkeyPatch) -> None:
    """模型返回空 → content 为空，不把按钮标记为已读。"""
    db = _FakeDB([
        ("SELECT 1 FROM chat_sessions", [{"ok": 1}]),
        ("SELECT 1 FROM info_gap_buttons", [{"ok": 1}]),
    ])
    background_tasks = BackgroundTasks()

    async def fake_get_cache(keyword: str) -> str | None:
        return None

    async def fake_generate(keyword: str) -> str:
        return ""

    monkeypatch.setattr(concepts, "_get_from_cache", fake_get_cache)
    monkeypatch.setattr(concepts, "_generate_explanation", fake_generate)

    response = _run(
        concepts.lookup_concept(
            concepts.ConceptLookupRequest(keyword="某概念"),
            background_tasks,
            db,
            {"id": "u1"},
        )
    )

    assert response.content == ""
    assert len(background_tasks.tasks) == 0


# ── 权限校验 ──────────────────────────────────────────────────────────────────

def test_non_member_session_returns_403(monkeypatch: pytest.MonkeyPatch) -> None:
    """session_id 不属于当前用户 → 403。"""
    from fastapi import HTTPException

    db = _FakeDB([
        ("SELECT 1 FROM chat_sessions", []),  # 空结果 = 非成员
    ])

    async def fake_get_cache(keyword: str) -> str | None:
        return None

    monkeypatch.setattr(concepts, "_get_from_cache", fake_get_cache)

    with pytest.raises(HTTPException) as exc:
        _run(
            concepts.lookup_concept(
                concepts.ConceptLookupRequest(keyword="某词", session_id="sess_other"),
                BackgroundTasks(),
                db,
                {"id": "u1"},
            )
        )
    assert exc.value.status_code == 403


def test_button_not_owned_returns_404(monkeypatch: pytest.MonkeyPatch) -> None:
    """button_id 不属于该 session / user → 404。"""
    from fastapi import HTTPException

    db = _FakeDB([
        ("SELECT 1 FROM chat_sessions", [{"ok": 1}]),   # session 合法
        ("SELECT 1 FROM info_gap_buttons", []),           # 按钮不存在
    ])

    async def fake_get_cache(keyword: str) -> str | None:
        return None

    monkeypatch.setattr(concepts, "_get_from_cache", fake_get_cache)

    with pytest.raises(HTTPException) as exc:
        _run(
            concepts.lookup_concept(
                concepts.ConceptLookupRequest(keyword="某词", session_id="sess_1", button_id="btn_other"),
                BackgroundTasks(),
                db,
                {"id": "u1"},
            )
        )
    assert exc.value.status_code == 404


# ── 后台任务 ──────────────────────────────────────────────────────────────────

def test_background_task_updates_button_status_to_clicked(monkeypatch: pytest.MonkeyPatch) -> None:
    """后台任务：按钮状态从 pending 更新为 clicked。"""
    bg_db = _BgDB(device_token=None)

    def fake_get_sessionmaker():
        class _Factory:
            def __call__(self) -> _BgDB:
                return bg_db
        return _Factory()

    monkeypatch.setattr(concepts, "get_sessionmaker", fake_get_sessionmaker)

    _run(
        concepts._run_background_tasks(
            button_id="btn_x",
            session_id="sess_1",
            user_id="u1",
            keyword="量化宽松",
            content="央行购买资产注入流动性。",
        )
    )

    update_params = next(
        (p for sql, p in bg_db.executed if "UPDATE info_gap_buttons" in sql),
        None,
    )
    assert update_params is not None
    assert update_params.get("button_id") == "btn_x"
    assert update_params.get("user_id") == "u1"


def test_background_task_writes_push_log_and_sends_jpush(monkeypatch: pytest.MonkeyPatch) -> None:
    """后台任务：有 device_token → 写 push_logs 并发 JPush，内容含 keyword。"""
    jpush_calls: list[tuple[str, str, str]] = []
    bg_db = _BgDB(device_token="dev-token-abc")

    def fake_get_sessionmaker():
        class _Factory:
            def __call__(self) -> _BgDB:
                return bg_db
        return _Factory()

    def fake_send_push(device_token: str, content: str, title: str) -> None:
        jpush_calls.append((device_token, content, title))

    monkeypatch.setattr(concepts, "get_sessionmaker", fake_get_sessionmaker)
    monkeypatch.setattr(concepts, "send_push_to_registration_id", fake_send_push)

    _run(
        concepts._run_background_tasks(
            button_id="btn_y",
            session_id="sess_1",
            user_id="u1",
            keyword="内卷",
            content="内部过度竞争的社会现象。",
        )
    )

    assert len(jpush_calls) == 1
    device_token, push_content, _ = jpush_calls[0]
    assert device_token == "dev-token-abc"
    assert "内卷" in push_content
    assert "内部过度竞争的社会现象" in push_content


def test_background_task_no_device_token_skips_jpush(monkeypatch: pytest.MonkeyPatch) -> None:
    """后台任务：无 device_token → 不发 JPush，push_logs 标记 skipped。"""
    jpush_calls: list[tuple[str, str, str]] = []
    bg_db = _BgDB(device_token=None)

    def fake_get_sessionmaker():
        class _Factory:
            def __call__(self) -> _BgDB:
                return bg_db
        return _Factory()

    def fake_send_push(device_token: str, content: str, title: str) -> None:
        jpush_calls.append((device_token, content, title))

    monkeypatch.setattr(concepts, "get_sessionmaker", fake_get_sessionmaker)
    monkeypatch.setattr(concepts, "send_push_to_registration_id", fake_send_push)

    _run(
        concepts._run_background_tasks(
            button_id="btn_z",
            session_id="sess_1",
            user_id="u1",
            keyword="内卷",
            content="内部过度竞争的社会现象。",
        )
    )

    assert jpush_calls == []
    skipped = next(
        (p for sql, p in bg_db.executed if "jpush_no_device_token" in sql),
        None,
    )
    assert skipped is not None
