"""Pure mocked tests for CoI AI segmentation review (no DB or network access)."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.app.admin import coi_ai_coding


class _FakeCompletions:
    def __init__(self, content: str) -> None:
        self.content = content
        self.request: dict | None = None

    async def create(self, **kwargs):
        self.request = kwargs
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))],
        )


class _FakeClient:
    latest: "_FakeClient | None" = None
    response_content = ""

    def __init__(self, **_kwargs) -> None:
        self.chat = SimpleNamespace(completions=_FakeCompletions(self.response_content))
        _FakeClient.latest = self


def test_review_segmentation_parses_suggestions_without_real_ai(monkeypatch) -> None:
    _FakeClient.response_content = """{"results":[
        {"unit_id":"u2","suggestion":"合并建议：与[u1]合并"},
        {"unit_id":"u1","suggestion":"无需调整"}
    ]}"""
    monkeypatch.setattr(coi_ai_coding.nlp_settings, "qwen_api_key", "test-key")
    monkeypatch.setattr(coi_ai_coding, "AsyncOpenAI", _FakeClient)

    result = asyncio.run(coi_ai_coding._review_segmentation([
        {"id": "u1", "order_index": 1, "content": "观点一"},
        {"id": "u2", "order_index": 2, "content": "观点二"},
    ]))

    assert result == [
        {"unit_id": "u1", "suggestion": "无需调整"},
        {"unit_id": "u2", "suggestion": "合并建议：与第1条合并"},
    ]
    request = _FakeClient.latest.chat.completions.request
    assert request is not None
    prompt = request["messages"][1]["content"]
    assert "不要进行 TE/EX/IN/RE 编码" in prompt
    assert "不得修改原文" in prompt
    assert "不得出现 unit_id" in prompt


def test_generate_codes_uses_other_for_non_codeable_unit(monkeypatch) -> None:
    _FakeClient.response_content = """{"results":[
        {"unit_id":"u1","coi_categories":["OTHER"],"reason":"纯附和，无实质认知贡献"}
    ]}"""
    monkeypatch.setattr(coi_ai_coding.nlp_settings, "qwen_api_key", "test-key")
    monkeypatch.setattr(coi_ai_coding, "AsyncOpenAI", _FakeClient)

    result = asyncio.run(coi_ai_coding._generate_codes([
        {"id": "u1", "order_index": 1, "content": "对，有道理。"},
    ]))

    assert result == [{
        "unit_id": "u1",
        "coi_categories": ["OTHER"],
        "coding_reason": "纯附和，无实质认知贡献",
    }]
    request = _FakeClient.latest.chat.completions.request
    assert request is not None
    prompt = request["messages"][1]["content"]
    assert 'coi_categories 必须返回 ["OTHER"]' in prompt
    assert "表达排序方向、相对位置或有序答案" in prompt
    assert "程序性片段不得抵消该排序贡献" in prompt
    assert '"coi_categories":["TE"]' in prompt
    assert "必须且只能包含一个类别" in prompt
    assert "不得返回两个或以上类别" in prompt
    assert "短句可以承接前文形成 IN" in prompt
    assert "长句或多个并列材料也可能仍是 EX" in prompt
    assert "不得仅凭‘如果、因为、所以、对比、分类’等词或材料数量决定 EX/IN" in prompt


def test_generate_codes_rejects_multiple_categories(monkeypatch) -> None:
    _FakeClient.response_content = """{"results":[
        {"unit_id":"u1","coi_categories":["IN","TE"],"reason":"提出疑问并进行比较权衡"}
    ]}"""
    monkeypatch.setattr(coi_ai_coding.nlp_settings, "qwen_api_key", "test-key")
    monkeypatch.setattr(coi_ai_coding, "AsyncOpenAI", _FakeClient)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(coi_ai_coding._generate_codes([
            {"id": "u1", "order_index": 1, "content": "提出疑问并比较多个条件。"},
        ]))

    assert exc_info.value.status_code == 502


def test_generate_codes_audits_request_response_and_parsed_result(monkeypatch) -> None:
    _FakeClient.response_content = """{"results":[
        {"unit_id":"u9","coi_categories":["TE"],"reason":"提出待确认问题"}
    ]}"""
    audit_records: list[dict] = []
    monkeypatch.setattr(coi_ai_coding.nlp_settings, "qwen_api_key", "test-key")
    monkeypatch.setattr(coi_ai_coding, "AsyncOpenAI", _FakeClient)
    monkeypatch.setattr(
        coi_ai_coding, "write_coi_ai_audit", lambda record: audit_records.append(record),
    )

    result = asyncio.run(coi_ai_coding._generate_codes(
        [{"id": "u9", "order_index": 9, "content": "要不大家都说一下对应的字母。"}],
        session_id="session-test",
        request_id="coia-test",
    ))

    assert result[0]["coi_categories"] == ["TE"]
    assert [record["stage"] for record in audit_records] == [
        "request", "model_response", "parsed",
    ]
    assert audit_records[0]["units"][0]["id"] == "u9"
    assert audit_records[1]["raw_response"] == _FakeClient.response_content
    assert audit_records[2]["results"] == result


def test_save_ai_code_input_accepts_empty_categories() -> None:
    payload = coi_ai_coding.SaveAiCodeIn(
        unit_id="u1",
        coi_categories=[],
        coding_reason="纯附和，无实质认知贡献",
    )

    assert payload.coi_categories == []


def test_empty_categories_are_returned_as_completed_ai_result() -> None:
    item = coi_ai_coding._row_to_out({
        "unit_id": "u9",
        "order_index": 9,
        "content": "程序性话语",
        "start_time": 1.0,
        "ai_segmentation_suggestion": "无需调整",
        "ai_segmentation_reviewed_at": None,
        "coi_categories": [],
        "ai_original_categories": [],
        "coding_reason": "仅为程序性话语，不编码。",
        "has_ai_result": True,
        "coded_by": "AI 编码员 C",
        "coded_at": None,
        "updated_at": None,
    })

    assert item.has_ai_result is True
    assert item.coi_categories == []
    assert item.coding_reason == "仅为程序性话语，不编码。"
