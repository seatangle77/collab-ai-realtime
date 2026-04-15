from __future__ import annotations

import pytest

from app.nlp import structured_push_content


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


class _BoomCompletions:
    def create(self, **kwargs):  # noqa: ANN003
        raise RuntimeError("boom")


class _BoomChat:
    def __init__(self) -> None:
        self.completions = _BoomCompletions()


class _BoomClient:
    def __init__(self) -> None:
        self.chat = _BoomChat()


@pytest.mark.parametrize("trigger_type", ["low_participation", "shallow_discussion"])
def test_generate_structured_push_content_parses_anchor_and_content(
    monkeypatch: pytest.MonkeyPatch,
    trigger_type: str,
) -> None:
    mock_content = """
{
  "needs_prompt": true,
  "anchor": {
    "transcript_id": "t2",
    "speaker_id": "uB",
    "text": "我们先限定MVP范围"
  },
  "content": "你认可先限定MVP范围吗？"
}
""".strip()
    monkeypatch.setattr(structured_push_content.nlp_settings, "qwen_api_key", "test-key", raising=False)
    monkeypatch.setattr(structured_push_content, "_get_client", lambda: _FakeClient(mock_content))

    result = structured_push_content.generate_structured_push_content(
        trigger_type=trigger_type,
        summary="讨论MVP定义和执行边界",
        transcripts=[
            {"transcript_id": "t1", "user_id": "uA", "text": "我还没想清楚"},
            {"transcript_id": "t2", "user_id": "uB", "text": "我们先限定MVP范围"},
        ],
        user_id="uA",
        trigger_metrics={"speaking_ratio": 0.08, "ttr": 0.2},
        candidate_points=[
            {"transcript_id": "t2", "speaker_id": "uB", "text": "我们先限定MVP范围"},
        ],
    )

    assert result["needs_prompt"] is True
    assert result["anchor"]["transcript_id"] == "t2"
    assert result["content"] == "你认可先限定MVP范围吗？"


def test_generate_structured_push_content_extracts_json_from_wrapped_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_content = """
先给你结果：
{
  "needs_prompt": true,
  "anchor": {
    "transcript_id": "t2",
    "speaker_id": "uB",
    "text": "我们先限定MVP范围"
  },
  "content": "你认可先限定MVP范围吗？"
}
""".strip()
    monkeypatch.setattr(structured_push_content.nlp_settings, "qwen_api_key", "test-key", raising=False)
    monkeypatch.setattr(structured_push_content, "_get_client", lambda: _FakeClient(mock_content))

    result = structured_push_content.generate_structured_push_content(
        trigger_type="low_participation",
        summary="讨论MVP定义和执行边界",
        transcripts=[
            {"transcript_id": "t2", "user_id": "uB", "text": "我们先限定MVP范围"},
        ],
        user_id="uA",
        trigger_metrics={"speaking_ratio": 0.08},
        candidate_points=[
            {"transcript_id": "t2", "speaker_id": "uB", "text": "我们先限定MVP范围"},
        ],
    )

    assert result["needs_prompt"] is True
    assert result["anchor"]["speaker_id"] == "uB"


def test_generate_structured_push_content_returns_empty_without_qwen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(structured_push_content.nlp_settings, "qwen_api_key", "", raising=False)

    result = structured_push_content.generate_structured_push_content(
        trigger_type="low_participation",
        summary="讨论MVP定义和执行边界",
        transcripts=[{"transcript_id": "t2", "user_id": "uB", "text": "我们先限定MVP范围"}],
        user_id="uA",
        trigger_metrics={"speaking_ratio": 0.08},
        candidate_points=[{"transcript_id": "t2", "speaker_id": "uB", "text": "我们先限定MVP范围"}],
    )

    assert result == {"needs_prompt": False, "anchor": None, "content": ""}


def test_generate_structured_push_content_returns_empty_when_low_participation_has_no_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(structured_push_content.nlp_settings, "qwen_api_key", "test-key", raising=False)
    monkeypatch.setattr(
        structured_push_content,
        "_get_client",
        lambda: pytest.fail("model should not be called without candidate points"),
    )

    result = structured_push_content.generate_structured_push_content(
        trigger_type="low_participation",
        summary="讨论MVP定义和执行边界",
        transcripts=[{"transcript_id": "t2", "user_id": "uB", "text": "我们先限定MVP范围"}],
        user_id="uA",
        trigger_metrics={"speaking_ratio": 0.08},
        candidate_points=[],
    )

    assert result == {"needs_prompt": False, "anchor": None, "content": ""}


def test_generate_structured_push_content_returns_empty_when_shallow_discussion_has_no_target_quotes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(structured_push_content.nlp_settings, "qwen_api_key", "test-key", raising=False)
    monkeypatch.setattr(
        structured_push_content,
        "_get_client",
        lambda: pytest.fail("model should not be called without target quotes"),
    )

    result = structured_push_content.generate_structured_push_content(
        trigger_type="shallow_discussion",
        summary="讨论MVP定义和执行边界",
        transcripts=[{"transcript_id": "t2", "user_id": "uB", "text": "我们先限定MVP范围"}],
        user_id="uA",
        trigger_metrics={"ttr": 0.2},
    )

    assert result == {"needs_prompt": False, "anchor": None, "content": ""}


def test_generate_structured_push_content_returns_empty_when_shallow_discussion_has_no_supported_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(structured_push_content.nlp_settings, "qwen_api_key", "test-key", raising=False)
    monkeypatch.setattr(
        structured_push_content,
        "_get_client",
        lambda: pytest.fail("model should not be called without supported metrics"),
    )

    result = structured_push_content.generate_structured_push_content(
        trigger_type="shallow_discussion",
        summary="讨论MVP定义和执行边界",
        transcripts=[{"transcript_id": "t2", "user_id": "uA", "text": "我们先限定MVP范围"}],
        user_id="uA",
        trigger_metrics={"description": "没有结构化指标"},
    )

    assert result == {"needs_prompt": False, "anchor": None, "content": ""}


def test_generate_structured_push_content_returns_empty_when_model_returns_invalid_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(structured_push_content.nlp_settings, "qwen_api_key", "test-key", raising=False)
    monkeypatch.setattr(structured_push_content, "_get_client", lambda: _FakeClient("not-json"))

    result = structured_push_content.generate_structured_push_content(
        trigger_type="low_participation",
        summary="讨论MVP定义和执行边界",
        transcripts=[{"transcript_id": "t2", "user_id": "uB", "text": "我们先限定MVP范围"}],
        user_id="uA",
        trigger_metrics={"speaking_ratio": 0.08},
        candidate_points=[{"transcript_id": "t2", "speaker_id": "uB", "text": "我们先限定MVP范围"}],
    )

    assert result == {"needs_prompt": False, "anchor": None, "content": ""}


def test_generate_structured_push_content_returns_empty_when_model_says_no_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(structured_push_content.nlp_settings, "qwen_api_key", "test-key", raising=False)
    monkeypatch.setattr(
        structured_push_content,
        "_get_client",
        lambda: _FakeClient('{"needs_prompt": false, "anchor": null, "content": ""}'),
    )

    result = structured_push_content.generate_structured_push_content(
        trigger_type="low_participation",
        summary="讨论MVP定义和执行边界",
        transcripts=[{"transcript_id": "t2", "user_id": "uB", "text": "我们先限定MVP范围"}],
        user_id="uA",
        trigger_metrics={"speaking_ratio": 0.08},
        candidate_points=[{"transcript_id": "t2", "speaker_id": "uB", "text": "我们先限定MVP范围"}],
    )

    assert result == {"needs_prompt": False, "anchor": None, "content": ""}


def test_generate_structured_push_content_returns_empty_when_anchor_is_incomplete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_content = """
{
  "needs_prompt": true,
  "anchor": {
    "transcript_id": "",
    "speaker_id": "uB",
    "text": "我们先限定MVP范围"
  },
  "content": "你认可先限定MVP范围吗？"
}
""".strip()
    monkeypatch.setattr(structured_push_content.nlp_settings, "qwen_api_key", "test-key", raising=False)
    monkeypatch.setattr(structured_push_content, "_get_client", lambda: _FakeClient(mock_content))

    result = structured_push_content.generate_structured_push_content(
        trigger_type="low_participation",
        summary="讨论MVP定义和执行边界",
        transcripts=[{"transcript_id": "t2", "user_id": "uB", "text": "我们先限定MVP范围"}],
        user_id="uA",
        trigger_metrics={"speaking_ratio": 0.08},
        candidate_points=[{"transcript_id": "t2", "speaker_id": "uB", "text": "我们先限定MVP范围"}],
    )

    assert result == {"needs_prompt": False, "anchor": None, "content": ""}


def test_generate_structured_push_content_returns_empty_when_content_too_long(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_content = """
{
  "needs_prompt": true,
  "anchor": {
    "transcript_id": "t2",
    "speaker_id": "uB",
    "text": "我们先限定MVP范围"
  },
  "content": "这是一条明显超过三十个字的测试文案，用来验证长度上限保护是否仍然有效"
}
""".strip()
    monkeypatch.setattr(structured_push_content.nlp_settings, "qwen_api_key", "test-key", raising=False)
    monkeypatch.setattr(structured_push_content, "_get_client", lambda: _FakeClient(mock_content))

    result = structured_push_content.generate_structured_push_content(
        trigger_type="low_participation",
        summary="讨论MVP定义和执行边界",
        transcripts=[{"transcript_id": "t2", "user_id": "uB", "text": "我们先限定MVP范围"}],
        user_id="uA",
        trigger_metrics={"speaking_ratio": 0.08},
        candidate_points=[{"transcript_id": "t2", "speaker_id": "uB", "text": "我们先限定MVP范围"}],
    )

    assert result == {"needs_prompt": False, "anchor": None, "content": ""}


def test_generate_structured_push_content_returns_empty_when_model_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(structured_push_content.nlp_settings, "qwen_api_key", "test-key", raising=False)
    monkeypatch.setattr(structured_push_content, "_get_client", lambda: _BoomClient())

    result = structured_push_content.generate_structured_push_content(
        trigger_type="low_participation",
        summary="讨论MVP定义和执行边界",
        transcripts=[{"transcript_id": "t2", "user_id": "uB", "text": "我们先限定MVP范围"}],
        user_id="uA",
        trigger_metrics={"speaking_ratio": 0.08},
        candidate_points=[{"transcript_id": "t2", "speaker_id": "uB", "text": "我们先限定MVP范围"}],
    )

    assert result == {"needs_prompt": False, "anchor": None, "content": ""}
