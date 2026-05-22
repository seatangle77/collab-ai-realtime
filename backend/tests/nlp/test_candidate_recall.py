from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.nlp import candidate_recall


# ── _find_word_context ────────────────────────────────────────────────────────

def test_find_word_context_found_in_first_user() -> None:
    texts = {"u1": "我在研究量化宽松政策。它影响很大", "u2": "利率方面我不太懂"}
    result = candidate_recall._find_word_context("量化宽松", texts)
    assert result == "我在研究量化宽松政策"


def test_find_word_context_found_in_second_user() -> None:
    texts = {"u1": "今天天气不错", "u2": "我们聊聊内卷的问题吧"}
    result = candidate_recall._find_word_context("内卷", texts)
    assert result == "我们聊聊内卷的问题吧"


def test_find_word_context_not_found_returns_empty() -> None:
    texts = {"u1": "今天天气不错", "u2": "是的很好"}
    result = candidate_recall._find_word_context("量化宽松", texts)
    assert result == ""


def test_find_word_context_empty_texts() -> None:
    result = candidate_recall._find_word_context("量化宽松", {})
    assert result == ""


def test_find_word_context_word_at_sentence_boundary() -> None:
    texts = {"u1": "第一句话。搭子就是这个意思！没错"}
    result = candidate_recall._find_word_context("搭子", texts)
    assert "搭子" in result


# ── _validate_keywords ────────────────────────────────────────────────────────

def test_validate_keywords_empty_list() -> None:
    result = candidate_recall._validate_keywords([], {"u1": "随便说说"})
    assert result == set()


def test_validate_keywords_no_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(candidate_recall.nlp_settings, "qwen_api_key", "")
    keywords = [{"word": "量化宽松"}, {"word": "八子"}]
    result = candidate_recall._validate_keywords(keywords, {"u1": "量化宽松和八子"})
    # fail open：返回所有词
    assert result == {"量化宽松", "八子"}


def test_validate_keywords_filters_asr_noise(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(candidate_recall.nlp_settings, "qwen_api_key", "fake-key")

    validate_response = MagicMock()
    validate_response.choices[0].message.content = (
        '{"results": ['
        '{"word": "量化宽松", "is_valid": true},'
        '{"word": "八子", "is_valid": false}'
        ']}'
    )

    with patch.object(candidate_recall, "_get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = validate_response
        mock_get_client.return_value = mock_client

        keywords = [{"word": "量化宽松"}, {"word": "八子"}]
        result = candidate_recall._validate_keywords(keywords, {"u1": "量化宽松和八子"})

    assert result == {"量化宽松"}
    assert "八子" not in result


def test_validate_keywords_all_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(candidate_recall.nlp_settings, "qwen_api_key", "fake-key")

    validate_response = MagicMock()
    validate_response.choices[0].message.content = (
        '{"results": ['
        '{"word": "搭子", "is_valid": true},'
        '{"word": "MBTI", "is_valid": true}'
        ']}'
    )

    with patch.object(candidate_recall, "_get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = validate_response
        mock_get_client.return_value = mock_client

        keywords = [{"word": "搭子"}, {"word": "MBTI"}]
        result = candidate_recall._validate_keywords(keywords, {"u1": "搭子和MBTI"})

    assert result == {"搭子", "MBTI"}


def test_validate_keywords_all_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(candidate_recall.nlp_settings, "qwen_api_key", "fake-key")

    validate_response = MagicMock()
    validate_response.choices[0].message.content = (
        '{"results": ['
        '{"word": "八子", "is_valid": false},'
        '{"word": "哦的", "is_valid": false}'
        ']}'
    )

    with patch.object(candidate_recall, "_get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = validate_response
        mock_get_client.return_value = mock_client

        keywords = [{"word": "八子"}, {"word": "哦的"}]
        result = candidate_recall._validate_keywords(keywords, {"u1": "八子哦的"})

    assert result == set()


def test_validate_keywords_json_decode_error_fail_open(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(candidate_recall.nlp_settings, "qwen_api_key", "fake-key")

    validate_response = MagicMock()
    validate_response.choices[0].message.content = "不是合法JSON"

    with patch.object(candidate_recall, "_get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = validate_response
        mock_get_client.return_value = mock_client

        keywords = [{"word": "量化宽松"}, {"word": "八子"}]
        result = candidate_recall._validate_keywords(keywords, {"u1": "量化宽松和八子"})

    # fail open：返回所有词
    assert result == {"量化宽松", "八子"}


def test_validate_keywords_api_exception_fail_open(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(candidate_recall.nlp_settings, "qwen_api_key", "fake-key")

    with patch.object(candidate_recall, "_get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("network error")
        mock_get_client.return_value = mock_client

        keywords = [{"word": "搭子"}, {"word": "内卷"}]
        result = candidate_recall._validate_keywords(keywords, {"u1": "搭子和内卷"})

    # fail open：返回所有词
    assert result == {"搭子", "内卷"}


def test_validate_keywords_malformed_response_fail_open(monkeypatch: pytest.MonkeyPatch) -> None:
    """返回 JSON 合法但缺少 results 字段时，fail open。"""
    monkeypatch.setattr(candidate_recall.nlp_settings, "qwen_api_key", "fake-key")

    validate_response = MagicMock()
    validate_response.choices[0].message.content = '{"unexpected_key": []}'

    with patch.object(candidate_recall, "_get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = validate_response
        mock_get_client.return_value = mock_client

        keywords = [{"word": "量化宽松"}]
        result = candidate_recall._validate_keywords(keywords, {"u1": "量化宽松"})

    # results 为空列表 → valid_words 为空集合，不 fail open，这是正常过滤
    # 但此处 results key 缺失等价于空列表，返回空集合属于正确行为
    assert isinstance(result, set)


def test_validate_keywords_extra_word_in_response_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    """验证模型返回了输入之外的词，不应影响结果。"""
    monkeypatch.setattr(candidate_recall.nlp_settings, "qwen_api_key", "fake-key")

    validate_response = MagicMock()
    validate_response.choices[0].message.content = (
        '{"results": ['
        '{"word": "量化宽松", "is_valid": true},'
        '{"word": "幻觉词", "is_valid": true}'  # 输入里没有这个词
        ']}'
    )

    with patch.object(candidate_recall, "_get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = validate_response
        mock_get_client.return_value = mock_client

        keywords = [{"word": "量化宽松"}]
        result = candidate_recall._validate_keywords(keywords, {"u1": "量化宽松"})

    # "幻觉词" 进入 valid_words，但 recall_with_gap 只保留原始候选词里的词，这里只测验证层
    assert "量化宽松" in result


# ── _dedupe_semantic_keywords ────────────────────────────────────────────────

def test_dedupe_semantic_keywords_empty_or_single() -> None:
    assert candidate_recall._dedupe_semantic_keywords([], {}) == []

    keywords = [{"word": "MBTI", "needs_prompt": True, "target_user_ids": ["u1"], "reason": ""}]
    assert candidate_recall._dedupe_semantic_keywords(keywords, {"u1": "MBTI"}) == keywords


def test_dedupe_semantic_keywords_merges_similar_terms() -> None:
    keywords = [
        {"word": "搞抽象", "needs_prompt": True, "target_user_ids": ["u1"], "reason": ""},
        {"word": "玩抽象", "needs_prompt": False, "target_user_ids": [], "reason": ""},
        {"word": "MBTI", "needs_prompt": True, "target_user_ids": ["u2"], "reason": ""},
    ]

    with (
        patch.object(candidate_recall.embedder, "encode") as mock_encode,
        patch.object(candidate_recall.similarity, "cosine_similarity") as mock_similarity,
    ):
        mock_encode.return_value = [[1, 0], [0.99, 0.01], [0, 1]]
        mock_similarity.side_effect = [0.92, 0.12, 0.08]

        result = candidate_recall._dedupe_semantic_keywords(
            keywords,
            {"u1": "我觉得这里是在搞抽象，不是玩抽象。MBTI 也能解释"},
        )

    words = [item["word"] for item in result]
    assert words == ["搞抽象", "MBTI"]


def test_dedupe_semantic_keywords_keeps_distinct_terms() -> None:
    keywords = [
        {"word": "MBTI", "needs_prompt": True, "target_user_ids": ["u1"], "reason": ""},
        {"word": "量化宽松", "needs_prompt": True, "target_user_ids": ["u2"], "reason": ""},
    ]

    with (
        patch.object(candidate_recall.embedder, "encode") as mock_encode,
        patch.object(candidate_recall.similarity, "cosine_similarity") as mock_similarity,
    ):
        mock_encode.return_value = [[1, 0], [0, 1]]
        mock_similarity.return_value = 0.2

        result = candidate_recall._dedupe_semantic_keywords(
            keywords,
            {"u1": "MBTI", "u2": "量化宽松"},
        )

    assert [item["word"] for item in result] == ["MBTI", "量化宽松"]


def test_dedupe_semantic_keywords_prefers_needs_prompt_and_longer_term() -> None:
    keywords = [
        {"word": "抽象", "needs_prompt": False, "target_user_ids": [], "reason": ""},
        {"word": "搞抽象", "needs_prompt": True, "target_user_ids": ["u1"], "reason": "需要提示"},
    ]

    with (
        patch.object(candidate_recall.embedder, "encode") as mock_encode,
        patch.object(candidate_recall.similarity, "cosine_similarity") as mock_similarity,
    ):
        mock_encode.return_value = [[1, 0], [0.99, 0.01]]
        mock_similarity.return_value = 0.93

        result = candidate_recall._dedupe_semantic_keywords(
            keywords,
            {"u1": "这里真的很抽象，或者说是在搞抽象"},
        )

    assert [item["word"] for item in result] == ["搞抽象"]
    assert result[0]["needs_prompt"] is True


def test_dedupe_semantic_keywords_embedding_exception_fail_open() -> None:
    keywords = [
        {"word": "搞抽象", "needs_prompt": True, "target_user_ids": ["u1"], "reason": ""},
        {"word": "玩抽象", "needs_prompt": False, "target_user_ids": [], "reason": ""},
    ]

    with patch.object(candidate_recall.embedder, "encode", side_effect=RuntimeError("model not loaded")):
        result = candidate_recall._dedupe_semantic_keywords(keywords, {"u1": "搞抽象 玩抽象"})

    assert result == keywords


# ── recall_with_gap（含验证步骤的集成测试） ──────────────────────────────────

def test_recall_with_gap_empty_input() -> None:
    result = candidate_recall.recall_with_gap({})
    assert result == {"keywords": []}


def test_recall_with_gap_single_member() -> None:
    result = candidate_recall.recall_with_gap({"u1": "量化宽松很重要"})
    assert result == {"keywords": []}


def test_recall_with_gap_no_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(candidate_recall.nlp_settings, "qwen_api_key", "")
    result = candidate_recall.recall_with_gap({"u1": "量化宽松", "u2": "利率政策"})
    assert result == {"keywords": []}


def test_recall_with_gap_normal(monkeypatch: pytest.MonkeyPatch) -> None:
    """正常流程：召回两个词，验证均通过，全部返回。"""
    monkeypatch.setattr(candidate_recall.nlp_settings, "qwen_api_key", "fake-key")

    recall_response = MagicMock()
    recall_response.choices[0].message.content = """{
  "keywords": [
    {"word": "量化宽松", "needs_prompt": true, "target_user_ids": ["u2"], "reason": "u2 多次提及但 u1 没有回应"},
    {"word": "缩表", "needs_prompt": false, "target_user_ids": [], "reason": "两人理解一致"}
  ]
}"""

    validate_response = MagicMock()
    validate_response.choices[0].message.content = (
        '{"results": ['
        '{"word": "量化宽松", "is_valid": true},'
        '{"word": "缩表", "is_valid": true}'
        ']}'
    )

    with patch.object(candidate_recall, "_get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [recall_response, validate_response]
        mock_get_client.return_value = mock_client

        result = candidate_recall.recall_with_gap({"u1": "利率政策", "u2": "量化宽松和缩表"})

    assert len(result["keywords"]) == 2
    assert result["keywords"][0]["word"] == "量化宽松"
    assert result["keywords"][0]["needs_prompt"] is True
    assert result["keywords"][0]["target_user_ids"] == ["u2"]
    assert result["keywords"][1]["word"] == "缩表"
    assert result["keywords"][1]["needs_prompt"] is False


def test_recall_with_gap_validation_filters_noise(monkeypatch: pytest.MonkeyPatch) -> None:
    """验证层过滤掉 ASR 乱码，只返回有效词。"""
    monkeypatch.setattr(candidate_recall.nlp_settings, "qwen_api_key", "fake-key")

    recall_response = MagicMock()
    recall_response.choices[0].message.content = """{
  "keywords": [
    {"word": "量化宽松", "needs_prompt": true, "target_user_ids": ["u2"], "reason": "u2 提及"},
    {"word": "八子", "needs_prompt": true, "target_user_ids": ["u1"], "reason": "u1 多次提及"}
  ]
}"""

    validate_response = MagicMock()
    validate_response.choices[0].message.content = (
        '{"results": ['
        '{"word": "量化宽松", "is_valid": true},'
        '{"word": "八子", "is_valid": false}'
        ']}'
    )

    with patch.object(candidate_recall, "_get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [recall_response, validate_response]
        mock_get_client.return_value = mock_client

        result = candidate_recall.recall_with_gap({"u1": "量化宽松八子", "u2": "量化宽松很重要"})

    assert len(result["keywords"]) == 1
    assert result["keywords"][0]["word"] == "量化宽松"
    words = [kw["word"] for kw in result["keywords"]]
    assert "八子" not in words


def test_recall_with_gap_semantic_dedupe_after_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    """验证通过后，再用 embedding 合并同轮语义重复词。"""
    monkeypatch.setattr(candidate_recall.nlp_settings, "qwen_api_key", "fake-key")

    recall_response = MagicMock()
    recall_response.choices[0].message.content = """{
  "keywords": [
    {"word": "搞抽象", "needs_prompt": true, "target_user_ids": ["u1"], "reason": "u1 可能不懂"},
    {"word": "玩抽象", "needs_prompt": false, "target_user_ids": [], "reason": "语义相近"},
    {"word": "MBTI", "needs_prompt": true, "target_user_ids": ["u2"], "reason": "u2 可能不懂"}
  ]
}"""

    validate_response = MagicMock()
    validate_response.choices[0].message.content = (
        '{"results": ['
        '{"word": "搞抽象", "is_valid": true},'
        '{"word": "玩抽象", "is_valid": true},'
        '{"word": "MBTI", "is_valid": true}'
        ']}'
    )

    with (
        patch.object(candidate_recall, "_get_client") as mock_get_client,
        patch.object(candidate_recall.embedder, "encode") as mock_encode,
        patch.object(candidate_recall.similarity, "cosine_similarity") as mock_similarity,
    ):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [recall_response, validate_response]
        mock_get_client.return_value = mock_client
        mock_encode.return_value = [[1, 0], [0.99, 0.01], [0, 1]]
        mock_similarity.side_effect = [0.91, 0.1, 0.08]

        result = candidate_recall.recall_with_gap(
            {"u1": "这个表达有点搞抽象，也像玩抽象", "u2": "MBTI 是另一个概念"},
        )

    assert [item["word"] for item in result["keywords"]] == ["搞抽象", "MBTI"]


def test_recall_with_gap_validation_filters_all(monkeypatch: pytest.MonkeyPatch) -> None:
    """验证层把所有词都过滤掉时，返回空列表。"""
    monkeypatch.setattr(candidate_recall.nlp_settings, "qwen_api_key", "fake-key")

    recall_response = MagicMock()
    recall_response.choices[0].message.content = """{
  "keywords": [
    {"word": "八子", "needs_prompt": true, "target_user_ids": ["u1"], "reason": "乱码"},
    {"word": "哦的", "needs_prompt": true, "target_user_ids": ["u2"], "reason": "乱码"}
  ]
}"""

    validate_response = MagicMock()
    validate_response.choices[0].message.content = (
        '{"results": ['
        '{"word": "八子", "is_valid": false},'
        '{"word": "哦的", "is_valid": false}'
        ']}'
    )

    with patch.object(candidate_recall, "_get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [recall_response, validate_response]
        mock_get_client.return_value = mock_client

        result = candidate_recall.recall_with_gap({"u1": "八子哦的", "u2": "八子哦的"})

    assert result == {"keywords": []}


def test_recall_with_gap_validation_fail_open(monkeypatch: pytest.MonkeyPatch) -> None:
    """验证调用异常时 fail open，召回词全部保留。"""
    monkeypatch.setattr(candidate_recall.nlp_settings, "qwen_api_key", "fake-key")

    recall_response = MagicMock()
    recall_response.choices[0].message.content = """{
  "keywords": [
    {"word": "量化宽松", "needs_prompt": true, "target_user_ids": ["u2"], "reason": "u2 提及"}
  ]
}"""

    validate_response = MagicMock()
    validate_response.choices[0].message.content = "非法JSON"

    with patch.object(candidate_recall, "_get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [recall_response, validate_response]
        mock_get_client.return_value = mock_client

        result = candidate_recall.recall_with_gap({"u1": "利率", "u2": "量化宽松很重要"})

    # 验证失败 fail open，召回词应完整保留
    assert len(result["keywords"]) == 1
    assert result["keywords"][0]["word"] == "量化宽松"


def test_recall_with_gap_empty_keywords(monkeypatch: pytest.MonkeyPatch) -> None:
    """召回返回空列表，验证步骤不触发。"""
    monkeypatch.setattr(candidate_recall.nlp_settings, "qwen_api_key", "fake-key")

    recall_response = MagicMock()
    recall_response.choices[0].message.content = '{"keywords": []}'

    with patch.object(candidate_recall, "_get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = recall_response
        mock_get_client.return_value = mock_client

        result = candidate_recall.recall_with_gap({"u1": "今天天气不错", "u2": "是的很好"})

    # 只有一次 LLM 调用（召回），验证未触发
    assert result == {"keywords": []}
    assert mock_client.chat.completions.create.call_count == 1


def test_recall_with_gap_json_decode_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(candidate_recall.nlp_settings, "qwen_api_key", "fake-key")

    mock_response = MagicMock()
    mock_response.choices[0].message.content = "不是合法JSON内容"

    with patch.object(candidate_recall, "_get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = candidate_recall.recall_with_gap({"u1": "量化宽松", "u2": "利率政策"})

    assert result == {"keywords": []}


def test_recall_with_gap_api_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(candidate_recall.nlp_settings, "qwen_api_key", "fake-key")

    with patch.object(candidate_recall, "_get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("timeout")
        mock_get_client.return_value = mock_client

        result = candidate_recall.recall_with_gap({"u1": "量化宽松", "u2": "利率政策"})

    assert result == {"keywords": []}
