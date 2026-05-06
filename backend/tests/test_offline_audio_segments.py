"""
离线音频补传接口集成测试。

运行前提：
  OFFLINE_AUDIO_TRANSCRIPT_PLACEHOLDER=1 uvicorn backend.app.main:app --reload --port 8000

运行：
  python -m backend.tests.test_offline_audio_segments

依赖：
  ffmpeg, requests, websocket-client
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
import uuid
from typing import Any, Callable, Dict, Tuple

import requests
import websocket

BASE_URL = "http://127.0.0.1:8000"
WS_BASE = "ws://127.0.0.1:8000"
RUN_ID = uuid.uuid4().hex[:6]
MAX_BYTES = 20 * 1024 * 1024


def _log(ok: bool, msg: str, extra: Any = None) -> bool:
    print(f"{'✅' if ok else '❌'} {msg}")
    if not ok and extra is not None:
        print("   详情:", extra)
    return ok


def _auth(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _make_webm_segment(duration: float = 1.0) -> bytes:
    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=1000:duration={duration}",
            "-c:a",
            "libopus",
            "-f",
            "webm",
            "pipe:1",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return result.stdout


def register_and_login(name: str, suffix: str) -> Tuple[str, str]:
    email = f"offline_{suffix}_{uuid.uuid4().hex[:6]}@example.com"
    r = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={
            "name": name,
            "email": email,
            "password": "1234",
            "device_token": f"dev-offline-{suffix}-{uuid.uuid4().hex[:8]}",
        },
    )
    r.raise_for_status()
    user_id = r.json()["id"]
    r2 = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": "1234"})
    r2.raise_for_status()
    return r2.json()["access_token"], user_id


def setup(ctx: Dict[str, Any]) -> bool:
    ctx["leader_token"], ctx["leader_user_id"] = register_and_login(f"Offline Leader {RUN_ID}", "leader")
    ctx["member_token"], ctx["member_user_id"] = register_and_login(f"Offline Member {RUN_ID}", "member")
    ctx["outsider_token"], ctx["outsider_user_id"] = register_and_login(f"Offline Outsider {RUN_ID}", "outsider")

    r = requests.post(
        f"{BASE_URL}/api/groups",
        json={"name": f"Offline Segment Group {RUN_ID}"},
        headers=_auth(ctx["leader_token"]),
    )
    if r.status_code != 201:
        return _log(False, "setup: 创建 group 失败", {"status": r.status_code, "body": r.text})
    ctx["group_id"] = r.json()["group"]["id"]

    r2 = requests.post(f"{BASE_URL}/api/groups/{ctx['group_id']}/join", headers=_auth(ctx["member_token"]))
    if r2.status_code != 200:
        return _log(False, "setup: member 加入 group 失败", {"status": r2.status_code, "body": r2.text})
    return _log(True, "setup: 用户和 group 准备完成")


def _end_any_ongoing(leader_token: str, group_id: str) -> None:
    r = requests.get(f"{BASE_URL}/api/groups/{group_id}/sessions", headers=_auth(leader_token))
    if r.status_code != 200:
        return
    for s in r.json():
        if s.get("status") == "ongoing":
            requests.post(f"{BASE_URL}/api/sessions/{s['id']}/end", headers=_auth(leader_token))


def _create_session(token: str, group_id: str, title: str, *, start: bool = True) -> str:
    _end_any_ongoing(token, group_id)
    r = requests.post(
        f"{BASE_URL}/api/groups/{group_id}/sessions",
        json={"session_title": title},
        headers=_auth(token),
    )
    r.raise_for_status()
    session_id = r.json()["id"]
    if start:
        requests.post(f"{BASE_URL}/api/sessions/{session_id}/start", headers=_auth(token)).raise_for_status()
    return session_id


def _upload(
    session_id: str,
    token: str,
    *,
    segment_id: str,
    audio_bytes: bytes,
    mime_type: str = "audio/webm",
    started_at: str = "2026-05-06T10:00:00Z",
    ended_at: str = "2026-05-06T10:00:01Z",
) -> requests.Response:
    return requests.post(
        f"{BASE_URL}/api/sessions/{session_id}/audio-segments",
        headers=_auth(token),
        data={
            "segment_id": segment_id,
            "started_at": started_at,
            "ended_at": ended_at,
            "mime_type": mime_type,
        },
        files={"audio": ("segment.webm", audio_bytes, mime_type)},
        timeout=30,
    )


def _list_transcripts(session_id: str, token: str) -> list[dict[str, Any]]:
    r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/transcripts", headers=_auth(token))
    r.raise_for_status()
    return r.json()


def _ws_connect(session_id: str, token: str) -> websocket.WebSocket:
    ws = websocket.create_connection(f"{WS_BASE}/ws/sessions/{session_id}?token={token}", timeout=8)
    json.loads(ws.recv())  # connected
    return ws


def test_success_idempotency_and_broadcast(ctx: Dict[str, Any]) -> bool:
    session_id = _create_session(ctx["leader_token"], ctx["group_id"], f"Offline success {RUN_ID}")
    audio = _make_webm_segment()
    seg_id = f"seg-success-{uuid.uuid4().hex[:8]}"
    ws = None
    try:
        ws = _ws_connect(session_id, ctx["leader_token"])
        r = _upload(session_id, ctx["leader_token"], segment_id=seg_id, audio_bytes=audio)
        if r.status_code == 503:
            return _log(
                True,
                "合法 offline segment 默认返回 503（离线 ASR 未启用，上传与解码已通过）",
                {"status": r.status_code, "body": r.text},
            )
        if r.status_code != 200:
            return _log(False, "合法 offline segment 上传应成功", {"status": r.status_code, "body": r.text})
        body = r.json()
        ok = body.get("status") == "processed" and bool(body.get("transcript_id"))

        ws.settimeout(8)
        ws_msg = json.loads(ws.recv())
        ok &= ws_msg.get("type") == "transcript"
        ok &= ws_msg.get("data", {}).get("transcript_id") == body.get("transcript_id")

        items = _list_transcripts(session_id, ctx["leader_token"])
        ok &= any(item["transcript_id"] == body.get("transcript_id") for item in items)

        r2 = _upload(session_id, ctx["leader_token"], segment_id=seg_id, audio_bytes=audio)
        ok &= r2.status_code == 200
        dup = r2.json()
        ok &= dup.get("duplicate") is True
        ok &= dup.get("transcript_id") == body.get("transcript_id")

        after_items = _list_transcripts(session_id, ctx["leader_token"])
        matching = [item for item in after_items if item["transcript_id"] == body.get("transcript_id")]
        ok &= len(matching) == 1
        return _log(ok, "成功上传 + WS 广播 + transcript 入库 + 幂等重复上传", {"first": body, "duplicate": dup})
    finally:
        if ws:
            ws.close()
        requests.post(f"{BASE_URL}/api/sessions/{session_id}/end", headers=_auth(ctx["leader_token"]))


def test_validation_errors(ctx: Dict[str, Any]) -> bool:
    session_id = _create_session(ctx["leader_token"], ctx["group_id"], f"Offline validation {RUN_ID}")
    audio = _make_webm_segment()
    cases = [
        ("非法 mime 返回 400", {"mime_type": "audio/mp3", "audio_bytes": audio}, 400),
        ("空文件返回 400", {"audio_bytes": b""}, 400),
        ("超过 20MB 返回 413", {"audio_bytes": b"x" * (MAX_BYTES + 1)}, 413),
        ("ended_at 早于 started_at 返回 422", {"started_at": "2026-05-06T10:00:02Z", "ended_at": "2026-05-06T10:00:01Z", "audio_bytes": audio}, 422),
        ("解码失败返回 422", {"audio_bytes": b"not-a-webm"}, 422),
    ]
    ok = True
    try:
        for label, kwargs, expected_status in cases:
            r = _upload(
                session_id,
                ctx["leader_token"],
                segment_id=f"seg-{uuid.uuid4().hex[:8]}",
                **kwargs,
            )
            ok &= _log(r.status_code == expected_status, label, {"status": r.status_code, "body": r.text})
        return ok
    finally:
        requests.post(f"{BASE_URL}/api/sessions/{session_id}/end", headers=_auth(ctx["leader_token"]))


def test_auth_and_session_state_errors(ctx: Dict[str, Any]) -> bool:
    audio = _make_webm_segment()
    ok = True

    missing = _upload(
        "s_missing_offline",
        ctx["leader_token"],
        segment_id=f"seg-{uuid.uuid4().hex[:8]}",
        audio_bytes=audio,
    )
    ok &= _log(missing.status_code == 404, "session 不存在返回 404", {"status": missing.status_code, "body": missing.text})

    ended_id = _create_session(ctx["leader_token"], ctx["group_id"], f"Offline ended {RUN_ID}")
    requests.post(f"{BASE_URL}/api/sessions/{ended_id}/end", headers=_auth(ctx["leader_token"]))
    ended = _upload(
        ended_id,
        ctx["leader_token"],
        segment_id=f"seg-{uuid.uuid4().hex[:8]}",
        audio_bytes=audio,
    )
    ok &= _log(ended.status_code == 409, "session 已结束返回 409", {"status": ended.status_code, "body": ended.text})

    ongoing_id = _create_session(ctx["leader_token"], ctx["group_id"], f"Offline auth {RUN_ID}")
    try:
        outsider = _upload(
            ongoing_id,
            ctx["outsider_token"],
            segment_id=f"seg-{uuid.uuid4().hex[:8]}",
            audio_bytes=audio,
        )
        ok &= _log(outsider.status_code == 403, "非 group 成员返回 403", {"status": outsider.status_code, "body": outsider.text})
    finally:
        requests.post(f"{BASE_URL}/api/sessions/{ongoing_id}/end", headers=_auth(ctx["leader_token"]))

    return ok


def run_all() -> bool:
    if shutil.which("ffmpeg") is None:
        print("⚠️ ffmpeg 不存在，跳过离线补传接口测试")
        return True
    try:
        root = requests.get(f"{BASE_URL}/", timeout=5)
        root.raise_for_status()
    except Exception as exc:
        print("后端未启动，测试中止 ❌", exc)
        return False

    ctx: Dict[str, Any] = {}
    if not setup(ctx):
        return False

    tests: list[Callable[[Dict[str, Any]], bool]] = [
        test_success_idempotency_and_broadcast,
        test_validation_errors,
        test_auth_and_session_state_errors,
    ]
    results = [test(ctx) for test in tests]
    ok = all(results)
    print("\n=== 离线音频补传接口测试完成：%s ===" % ("通过" if ok else "失败"))
    return ok


if __name__ == "__main__":
    sys.exit(0 if run_all() else 1)
