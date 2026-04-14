from __future__ import annotations

import json

import pytest

from app.nlp import gap_assessor


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, content: str) -> None:
        self._content = content

    def create(self, **kwargs):  # noqa: ANN003
        return _FakeResponse(self._content)


class _FakeChat:
    def __init__(self, content: str) -> None:
        self.completions = _FakeCompletions(content)


class _FakeClient:
    def __init__(self, content: str) -> None:
        self.chat = _FakeChat(content)


def test_assess_gap_returns_fallback_when_no_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gap_assessor.nlp_settings, "qwen_api_key", "", raising=False)
    items = gap_assessor.assess_gap(
        keywords=["MVP", "框架"],
        summary="讨论了MVP和框架",
        member_texts={"u1": "我理解MVP是最小可行产品"},
        skw_scores={"MVP": 0.23, "框架": 0.41},
    )

    assert len(items) == 2
    assert items[0]["keyword"] == "MVP"
    assert items[0]["needs_prompt"] is False
    assert items[0]["skw_score"] == pytest.approx(0.23)


def test_assess_gap_normalizes_llm_output(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "items": [
            {
                "keyword": "MVP",
                "needs_prompt": True,
                "target_user_id": "u2",
                "gap_type": "未知类型",
                "confidence": 1.3,
                "reason": "该成员把MVP误解为最终版本。",
                "skw_score": 0.12,
            }
        ]
    }
    monkeypatch.setattr(gap_assessor.nlp_settings, "qwen_api_key", "test-key", raising=False)
    monkeypatch.setattr(gap_assessor, "_get_client", lambda: _FakeClient(json.dumps(payload, ensure_ascii=False)))

    items = gap_assessor.assess_gap(
        keywords=["MVP"],
        summary="讨论产品开发节奏",
        member_texts={"u1": "MVP要快速验证", "u2": "MVP就是最终可上线版本"},
        skw_scores={"MVP": 0.2},
    )

    assert len(items) == 1
    item = items[0]
    assert item["keyword"] == "MVP"
    assert item["gap_type"] == "抽象概念未对齐"
    assert item["confidence"] == pytest.approx(1.0)
    assert item["target_user_id"] == "u2"


def test_assess_gap_returns_empty_when_llm_json_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gap_assessor.nlp_settings, "qwen_api_key", "test-key", raising=False)
    monkeypatch.setattr(gap_assessor, "_get_client", lambda: _FakeClient("not-json"))

    items = gap_assessor.assess_gap(
        keywords=["框架"],
        summary="",
        member_texts={"u1": "内容"},
        skw_scores={"框架": 0.5},
    )
    assert items == []
