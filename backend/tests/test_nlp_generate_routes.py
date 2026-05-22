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
                    "target_user_ids": ["u2"],
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
    assert resp.json()["keywords"][0]["target_user_ids"] == ["u2"]


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


def test_reasoning_batch_ok(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.nlp.router.batch_has_reasoning",
        lambda members: [
            {
                "user_id": "u1",
                "reasoning_status": True,
                "evidence_status": False,
                "reasoning_source": "发言中明确说明了选择该方案的原因。",
                "evidence_source": "发言中没有提供例子、数据或事实依据。",
            },
            {
                "user_id": "u2",
                "reasoning_status": False,
                "evidence_status": True,
                "reasoning_source": "发言中只有观点表态，没有展开原因。",
                "evidence_source": "发言中引用了具体案例作为支撑。",
            },
        ],
    )
    client = _make_client()

    resp = client.post(
        "/api/nlp/reasoning_batch",
        headers=ADMIN_HEADERS,
        json={
            "members": [
                {"user_id": "u1", "text": "我建议先做 MVP，因为范围更容易控制。"},
                {"user_id": "u2", "text": "比如腾讯会议也用了类似做法。"},
            ]
        },
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["members"][0]["user_id"] == "u1"
    assert payload["members"][0]["reasoning_status"] is True
    assert payload["members"][0]["evidence_source"] == "发言中没有提供例子、数据或事实依据。"
    assert payload["members"][1]["evidence_status"] is True


def test_reasoning_batch_422_when_members_shape_invalid() -> None:
    client = _make_client()

    resp = client.post(
        "/api/nlp/reasoning_batch",
        headers=ADMIN_HEADERS,
        json={"members": [{"user_id": "u1"}]},
    )

    assert resp.status_code == 422


def test_analyze_members_ok(monkeypatch) -> None:
    async def _fake_analyze_members_batch(**kwargs):
        return {
            "members": [
                {
                    "user_id": "u2",
                    "challenge_type": "stagnation",
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
                    "reasoning_status": False,
                    "evidence_status": False,
                    "reasoning_source": "发言中只有观点表态，没有展开原因。",
                    "evidence_source": "发言中没有提供例子、数据或事实依据。",
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
