from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))

from app.nlp import candidate_recall


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


def test_recall_with_gap_returns_fallback_when_no_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(candidate_recall.nlp_settings, "qwen_api_key", "", raising=False)

    result = candidate_recall.recall_with_gap(
        {"u1": "讨论 MVP", "u2": "我不理解 MVP 是什么"}
    )

    assert result == {"keywords": []}


def test_recall_with_gap_normalizes_llm_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "keywords": [
            {
                "word": "MVP",
                "needs_prompt": True,
                "target_user_id": "u2",
                "reason": "u2 明显没跟上这个缩写。",
                "extra_field": "ignored",
            },
            {"word": "   ", "needs_prompt": True},
            "not-a-dict",
        ]
    }
    monkeypatch.setattr(candidate_recall.nlp_settings, "qwen_api_key", "test-key", raising=False)
    monkeypatch.setattr(
        candidate_recall,
        "_get_client",
        lambda: _FakeClient(json.dumps(payload, ensure_ascii=False)),
    )

    result = candidate_recall.recall_with_gap(
        {"u1": "我们先做 MVP", "u2": "MVP 是最终上线版本吗"}
    )

    assert result == {
        "keywords": [
            {
                "word": "MVP",
                "needs_prompt": True,
                "target_user_id": "u2",
                "reason": "u2 明显没跟上这个缩写。",
            }
        ]
    }


def test_recall_with_gap_returns_empty_when_llm_json_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(candidate_recall.nlp_settings, "qwen_api_key", "test-key", raising=False)
    monkeypatch.setattr(candidate_recall, "_get_client", lambda: _FakeClient("not-json"))

    result = candidate_recall.recall_with_gap(
        {"u1": "讨论框架", "u2": "这个框架是什么意思"}
    )

    assert result == {"keywords": []}
