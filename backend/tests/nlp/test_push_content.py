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


def test_generate_push_content_batch_renders_template_and_parses_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_content = """
{
  "items": [
    {
      "user_id": "u1",
      "challenge_type": "personal_stagnation",
      "needs_prompt": true,
      "analysis": "该成员近期没有提出新观点",
      "content": "试着从执行成本再想一步"
    },
    {
      "user_id": "ALL",
      "challenge_type": "group_stagnation",
      "needs_prompt": false,
      "analysis": "当前全组仍有自然推进空间",
      "content": "这一项会被清空"
    }
  ]
}
""".strip()
    monkeypatch.setattr(push_content.nlp_settings, "qwen_api_key", "test-key", raising=False)
    monkeypatch.setattr(push_content, "_get_client", lambda: _FakeClient(mock_content))

    items = push_content.generate_push_content_batch(
        session_id="s1",
        summary="讨论围绕教育公平展开",
        transcripts="u1：我暂时没想到新角度\nu2：我们还可以讨论执行难点",
        members=[{"user_id": "u1"}, {"user_id": "u2"}],
        targets=[
            {
                "user_id": "u1",
                "challenge_type": "personal_stagnation",
                "evidence": {"speaking_ratio": 0.08},
                "diagnosis": "发言较少且缺乏新观点",
                "design_goal": "提供新切入角度",
            },
            {
                "user_id": "ALL",
                "challenge_type": "group_stagnation",
                "evidence": {"silence_s": 42},
                "diagnosis": "全组讨论短暂停滞",
                "design_goal": "提供新讨论方向",
            },
        ],
    )

    assert items == [
        {
            "user_id": "u1",
            "challenge_type": "personal_stagnation",
            "needs_prompt": True,
            "analysis": "该成员近期没有提出新观点",
            "content": "试着从执行成本再想一步",
        },
        {
            "user_id": "ALL",
            "challenge_type": "group_stagnation",
            "needs_prompt": False,
            "analysis": "当前全组仍有自然推进空间",
            "content": "",
        },
    ]
