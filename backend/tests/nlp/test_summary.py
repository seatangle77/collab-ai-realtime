from __future__ import annotations

import pytest

from app.nlp import summary


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


def test_generate_summary_without_prev_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_summary = "讨论围绕教育公平与AI资源配置展开，各成员立场分化，焦点在可执行方案。"
    monkeypatch.setattr(summary.nlp_settings, "qwen_api_key", "test-key", raising=False)
    monkeypatch.setattr(summary, "_get_client", lambda: _FakeClient(mock_summary))

    result = summary.generate_summary(
        transcripts=[
            {"user_id": "uA", "text": "我认为应该优先保障弱势地区"},
            {"user_id": "uB", "text": "还要看预算和落地难度"},
        ],
        prev_summary="",
    )

    assert isinstance(result, str)
    assert result.strip() != ""
    assert len(result) <= 200


def test_generate_summary_with_prev_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_summary = "在原有公平性讨论基础上，新增预算分配方案与评估指标，讨论进入实施细化阶段。"
    monkeypatch.setattr(summary.nlp_settings, "qwen_api_key", "test-key", raising=False)
    monkeypatch.setattr(summary, "_get_client", lambda: _FakeClient(mock_summary))

    result = summary.generate_summary(
        transcripts=[
            {"user_id": "uC", "text": "可以分阶段推进，先试点再扩展"},
        ],
        prev_summary="上一轮已明确核心矛盾是资源与效率平衡。",
    )

    assert isinstance(result, str)
    assert result.strip() != ""
    assert len(result) <= 200


def test_generate_summary_with_empty_transcripts() -> None:
    result = summary.generate_summary(transcripts=[], prev_summary="已有摘要")
    assert result == ""
