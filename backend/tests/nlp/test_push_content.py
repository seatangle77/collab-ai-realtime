from __future__ import annotations

import pytest

from app.nlp import push_content


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


@pytest.mark.parametrize(
    ("trigger_type", "mock_content", "max_len"),
    [
        ("group_silence", "换个角度聊聊用户体验", 30),
        ("low_participation", "你怎么看这个点，想听听你", 30),
        ("shallow_discussion", "这个观点背后的原因是什么", 30),
        ("info_gap", "这个词可理解为资源投入与机会分配差异", 40),
    ],
)
def test_generate_push_content_by_trigger_type(
    monkeypatch: pytest.MonkeyPatch,
    trigger_type: str,
    mock_content: str,
    max_len: int,
) -> None:
    monkeypatch.setattr(push_content.nlp_settings, "qwen_api_key", "test-key", raising=False)
    monkeypatch.setattr(
        push_content,
        "_get_client",
        lambda: _FakeClient(mock_content),
    )

    content = push_content.generate_push_content(
        trigger_type=trigger_type,
        summary="讨论围绕教育公平展开",
        transcripts="uA: 我认为资源分配不均衡",
        username="uA",
        silence_s=35,
        speaking_ratio=0.08,
        triggered_metrics="TTR偏低",
        keyword="资源",
        skw_score=0.21,
    )

    assert isinstance(content, str)
    assert content.strip() != ""
    assert len(content) <= max_len
