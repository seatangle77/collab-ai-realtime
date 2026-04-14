from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.nlp.router import router as nlp_router


ADMIN_HEADERS = {"X-Admin-Token": "TestAdminKey123"}


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(nlp_router)
    return TestClient(app)


def test_generate_push_ok(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.nlp.push_content.generate_push_content",
        lambda **kwargs: "测试推送文案",
    )
    client = _make_client()

    resp = client.post(
        "/api/nlp/generate_push",
        headers=ADMIN_HEADERS,
        json={
            "trigger_type": "low_participation",
            "summary": "讨论摘要",
            "transcripts": "uA: hello",
            "username": "uA",
        },
    )

    assert resp.status_code == 200
    assert resp.json() == {"content": "测试推送文案"}


def test_generate_push_forbidden_without_admin_token() -> None:
    client = _make_client()

    resp = client.post(
        "/api/nlp/generate_push",
        json={"trigger_type": "group_silence"},
    )

    assert resp.status_code == 403


def test_generate_push_422_when_missing_trigger_type() -> None:
    client = _make_client()

    resp = client.post(
        "/api/nlp/generate_push",
        headers=ADMIN_HEADERS,
        json={"summary": "讨论摘要"},
    )

    assert resp.status_code == 422


def test_generate_summary_ok(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.nlp.summary.generate_summary",
        lambda transcripts, prev_summary="": "更新后摘要",
    )
    client = _make_client()

    resp = client.post(
        "/api/nlp/generate_summary",
        headers=ADMIN_HEADERS,
        json={
            "transcripts": [{"user_id": "uA", "text": "本轮发言"}],
            "prev_summary": "上一轮摘要",
        },
    )

    assert resp.status_code == 200
    assert resp.json() == {"summary": "更新后摘要"}


def test_generate_summary_forbidden_without_admin_token() -> None:
    client = _make_client()

    resp = client.post(
        "/api/nlp/generate_summary",
        json={"transcripts": [{"user_id": "uA", "text": "发言"}]},
    )

    assert resp.status_code == 403


def test_generate_summary_422_when_transcripts_is_wrong_type() -> None:
    client = _make_client()

    resp = client.post(
        "/api/nlp/generate_summary",
        headers=ADMIN_HEADERS,
        json={"transcripts": "not-a-list"},
    )

    assert resp.status_code == 422


def test_candidate_recall_ok(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.nlp.candidate_recall.recall_candidates",
        lambda member_texts, top_n=15: {
            "keywords": ["MVP", "框架"],
            "sources": {"MVP": "acronym", "框架": "tfidf"},
        },
    )
    client = _make_client()

    resp = client.post(
        "/api/nlp/candidate_recall",
        headers=ADMIN_HEADERS,
        json={"member_texts": {"u1": "我们聊MVP"}, "top_n": 10},
    )

    assert resp.status_code == 200
    assert resp.json()["keywords"] == ["MVP", "框架"]


def test_candidate_recall_403_without_admin_token() -> None:
    client = _make_client()
    resp = client.post("/api/nlp/candidate_recall", json={"member_texts": {"u1": "x"}})
    assert resp.status_code == 403


def test_assess_gap_ok(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.nlp.gap_assessor.assess_gap",
        lambda keywords, summary, member_texts, skw_scores: [
            {
                "keyword": "MVP",
                "needs_prompt": True,
                "target_user_id": "u2",
                "gap_type": "缩写不懂",
                "confidence": 0.81,
                "reason": "该成员未理解缩写",
                "skw_score": 0.2,
            }
        ],
    )
    client = _make_client()

    resp = client.post(
        "/api/nlp/assess_gap",
        headers=ADMIN_HEADERS,
        json={
            "keywords": ["MVP"],
            "summary": "讨论产品节奏",
            "member_texts": {"u1": "MVP", "u2": "不懂MVP"},
            "skw_scores": {"MVP": 0.2},
        },
    )

    assert resp.status_code == 200
    assert resp.json()["items"][0]["target_user_id"] == "u2"


def test_assess_gap_ok_when_keywords_missing() -> None:
    client = _make_client()
    resp = client.post(
        "/api/nlp/assess_gap",
        headers=ADMIN_HEADERS,
        json={
            "summary": "讨论产品节奏",
            "member_texts": {"u1": "MVP"},
            "skw_scores": {"MVP": 0.2},
        },
    )
    # keywords 有默认值，不会 422；这里验证至少返回结构正确
    assert resp.status_code == 200
    assert "items" in resp.json()
