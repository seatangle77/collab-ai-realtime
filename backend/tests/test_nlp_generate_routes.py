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
