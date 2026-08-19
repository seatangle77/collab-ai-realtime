"""Pure mocked tests for CoI AI segmentation review (no DB or network access)."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

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


def test_generate_codes_accepts_empty_categories_for_non_codeable_unit(monkeypatch) -> None:
    _FakeClient.response_content = """{"results":[
        {"unit_id":"u1","coi_categories":[],"reason":"纯附和，无实质认知贡献"}
    ]}"""
    monkeypatch.setattr(coi_ai_coding.nlp_settings, "qwen_api_key", "test-key")
    monkeypatch.setattr(coi_ai_coding, "AsyncOpenAI", _FakeClient)

    result = asyncio.run(coi_ai_coding._generate_codes([
        {"id": "u1", "order_index": 1, "content": "对，有道理。"},
    ]))

    assert result == [{
        "unit_id": "u1",
        "coi_categories": [],
        "coding_reason": "纯附和，无实质认知贡献",
    }]
    request = _FakeClient.latest.chat.completions.request
    assert request is not None
    prompt = request["messages"][1]["content"]
    assert "coi_categories 必须返回空数组 []" in prompt


def test_save_ai_code_input_accepts_empty_categories() -> None:
    payload = coi_ai_coding.SaveAiCodeIn(
        unit_id="u1",
        coi_categories=[],
        coding_reason="纯附和，无实质认知贡献",
    )

    assert payload.coi_categories == []
