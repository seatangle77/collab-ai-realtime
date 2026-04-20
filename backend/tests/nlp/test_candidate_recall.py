from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.nlp import candidate_recall


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
    monkeypatch.setattr(candidate_recall.nlp_settings, "qwen_api_key", "fake-key")

    mock_response = MagicMock()
    mock_response.choices[0].message.content = """{
  "keywords": [
    {"word": "量化宽松", "needs_prompt": true, "target_user_id": "u2", "reason": "u2 多次提及但 u1 没有回应"},
    {"word": "缩表", "needs_prompt": false, "target_user_id": "", "reason": "两人理解一致"}
  ]
}"""

    with patch.object(candidate_recall, "_get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = candidate_recall.recall_with_gap({"u1": "利率政策", "u2": "量化宽松和缩表"})

    assert len(result["keywords"]) == 2
    assert result["keywords"][0]["word"] == "量化宽松"
    assert result["keywords"][0]["needs_prompt"] is True
    assert result["keywords"][0]["target_user_id"] == "u2"
    assert result["keywords"][1]["word"] == "缩表"
    assert result["keywords"][1]["needs_prompt"] is False


def test_recall_with_gap_empty_keywords(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(candidate_recall.nlp_settings, "qwen_api_key", "fake-key")

    mock_response = MagicMock()
    mock_response.choices[0].message.content = '{"keywords": []}'

    with patch.object(candidate_recall, "_get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = candidate_recall.recall_with_gap({"u1": "今天天气不错", "u2": "是的很好"})

    assert result == {"keywords": []}


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
