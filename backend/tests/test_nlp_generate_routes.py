from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.nlp.router import router as nlp_router


ADMIN_HEADERS = {"X-Admin-Token": "TestAdminKey123"}


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(nlp_router)
    return TestClient(app)


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


def test_keyword_recall_with_gap_ok(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.nlp.candidate_recall.recall_with_gap",
        lambda member_texts: {
            "keywords": [
                {
                    "word": "MVP",
                    "needs_prompt": True,
                    "target_user_id": "u2",
                    "reason": "u2 没跟上这个缩写",
                }
            ]
        },
    )
    client = _make_client()

    resp = client.post(
        "/api/nlp/keyword_recall_with_gap",
        headers=ADMIN_HEADERS,
        json={"member_texts": {"u1": "我们先做 MVP", "u2": "MVP 是什么"}},
    )

    assert resp.status_code == 200
    assert resp.json()["keywords"][0]["target_user_id"] == "u2"


def test_keyword_recall_with_gap_403_without_admin_token() -> None:
    client = _make_client()

    resp = client.post(
        "/api/nlp/keyword_recall_with_gap",
        json={"member_texts": {"u1": "x", "u2": "y"}},
    )

    assert resp.status_code == 403


def test_generate_group_silence_ok(monkeypatch) -> None:
    async def _fake_generate_group_silence(**kwargs):
        return "大家可以先对齐一下当前分歧。"

    monkeypatch.setattr(
        "app.nlp.push_content.generate_group_silence",
        _fake_generate_group_silence,
    )
    client = _make_client()

    resp = client.post(
        "/api/nlp/generate_group_silence",
        headers=ADMIN_HEADERS,
        json={"summary": "讨论卡住了", "transcripts": "A: ...", "silence_s": 35},
    )

    assert resp.status_code == 200
    assert resp.json() == {"content": "大家可以先对齐一下当前分歧。"}


def test_generate_group_silence_403_without_admin_token() -> None:
    client = _make_client()

    resp = client.post(
        "/api/nlp/generate_group_silence",
        json={"summary": "讨论卡住了", "transcripts": "", "silence_s": 35},
    )

    assert resp.status_code == 403


def test_analyze_members_ok(monkeypatch) -> None:
    async def _fake_analyze_members_batch(**kwargs):
        return {
            "members": [
                {
                    "user_id": "u2",
                    "challenge_type": "low_participation",
                    "needs_prompt": True,
                    "analysis": "u2 发言占比偏低。",
                    "content": "你怎么看刚才这个方案？",
                    "anchor": {"transcript_id": "t1"},
                }
            ]
        }

    monkeypatch.setattr(
        "app.nlp.push_content.analyze_members_batch",
        _fake_analyze_members_batch,
    )
    client = _make_client()

    resp = client.post(
        "/api/nlp/analyze_members",
        headers=ADMIN_HEADERS,
        json={
            "summary": "讨论摘要",
            "transcripts": [
                {
                    "transcript_id": "t1",
                    "user_id": "u1",
                    "speaker_name": "Alice",
                    "text": "我们先明确范围",
                }
            ],
            "members": [
                {
                    "user_id": "u2",
                    "speaking_ratio": 0.08,
                    "silence_s": 42,
                    "ttr": 0.2,
                    "arg_density": 0.01,
                    "srep": 0.1,
                    "info_gain": 0.0,
                    "has_reasoning": False,
                    "has_evidence": False,
                }
            ],
        },
    )

    assert resp.status_code == 200
    assert resp.json()["members"][0]["user_id"] == "u2"
    assert resp.json()["members"][0]["needs_prompt"] is True


def test_analyze_members_422_when_transcript_shape_invalid() -> None:
    client = _make_client()

    resp = client.post(
        "/api/nlp/analyze_members",
        headers=ADMIN_HEADERS,
        json={
            "summary": "讨论摘要",
            "transcripts": [{"user_id": "u1", "text": "缺少 transcript_id"}],
            "members": [],
        },
    )

    assert resp.status_code == 422
