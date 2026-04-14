from __future__ import annotations

import pytest

from app.nlp import candidate_recall


@pytest.fixture(autouse=True)
def _mock_phrase_extractor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(candidate_recall, "_extract_noun_phrases", lambda text: set())


def test_recall_candidates_empty_input() -> None:
    result = candidate_recall.recall_candidates({}, top_n=15)
    assert result == {"keywords": [], "sources": {}}


def test_recall_candidates_priority_and_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        candidate_recall,
        "extract_tfidf",
        lambda member_texts, top_n=20: {"keywords": ["框架", "机制", "价值"], "member_keyword_contexts": {}},
    )
    monkeypatch.setattr(candidate_recall, "ABSTRACT_CONCEPTS", {"价值", "效率", "共识"})
    monkeypatch.setattr(candidate_recall, "_extract_noun_phrases", lambda text: {"用户体验", "资源配置"})

    member_texts = {
        "u1": "我们讨论AI MVP和创新价值，以及用户体验",
        "u2": "我关心MVP推进效率和资源配置",
        "u3": "MVP要先做共识",
    }
    result = candidate_recall.recall_candidates(member_texts, top_n=6)

    assert result["keywords"] == ["框架", "机制", "价值", "MVP", "共识", "效率"]
    assert result["sources"]["框架"] == "tfidf"
    assert result["sources"]["MVP"] == "acronym"
    assert result["sources"]["共识"] == "abstract"


def test_recall_candidates_acronym_must_appear_in_at_least_two_members(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        candidate_recall,
        "extract_tfidf",
        lambda member_texts, top_n=20: {"keywords": [], "member_keyword_contexts": {}},
    )
    monkeypatch.setattr(candidate_recall, "ABSTRACT_CONCEPTS", set())

    member_texts = {
        "u1": "这个方向要看MVP和KPI，OK",
        "u2": "我只提了MVP",
        "u3": "只说了AI",
    }
    result = candidate_recall.recall_candidates(member_texts, top_n=10)

    # MVP 在 u1/u2 至少 2 人出现，KPI 和 AI 仅 1 人出现；OK 属于噪音词
    assert result["keywords"] == ["MVP"]
    assert result["sources"]["MVP"] == "acronym"
