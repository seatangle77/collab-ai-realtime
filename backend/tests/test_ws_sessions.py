"""
WebSocket 集成测试：/ws/sessions/{session_id}

测试用例：
  1. 连接后收到 connected 消息
  2. ping → pong
  3. 合法 audio_chunk → audio_chunk_ack（seq 一致）
  4. 连续 audio_chunk，seq 递增
  5. audio_chunk 缺少 seq → INVALID_AUDIO_CHUNK_SCHEMA
  6. audio_chunk mime_type 非法 → INVALID_AUDIO_CHUNK_SCHEMA
  7. audio_chunk audio_b64 非法 base64 → INVALID_AUDIO_CHUNK_SCHEMA
  8. audio_chunk audio_b64 过大 → INVALID_AUDIO_CHUNK_SCHEMA
  9. 未知消息类型 → UNKNOWN_TYPE
  10. 非法 JSON → INVALID_JSON
  11. JSON 格式不是对象 → INVALID_SCHEMA
  12. 广播：admin 写入转写 → 两个 WS 客户端均收到 transcript
  13. 断开后新连接不崩溃（ws_manager 清理验证）

运行前提：后端已启动（uvicorn backend.app.main:app --reload --port 8000）
依赖：pip install websocket-client requests
"""
from __future__ import annotations

import base64
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import requests
import websocket  # websocket-client

BASE_URL = "http://127.0.0.1:8000"
WS_BASE = "ws://127.0.0.1:8000"
RUN_ID = uuid.uuid4().hex[:6]

ADMIN_TOKEN = "TestAdminKey123"
ADMIN_HEADERS = {"X-Admin-Token": ADMIN_TOKEN}

WS_TIMEOUT = 5  # 等待 WS 消息的超时秒数

# ─────────────────────────── helpers ────────────────────────────────────────


def _log(ok: bool, msg: str, extra: Any = None) -> bool:
    print(f"{'✅' if ok else '❌'} {msg}")
    if not ok and extra is not None:
        print("   详情:", extra)
    return ok


def _stop(msg: str) -> None:
    print(f"\n🛑 测试中止：{msg}")
    sys.exit(1)


def _register_login(suffix: str) -> tuple[str, str]:
    email = f"ws_{suffix}_{uuid.uuid4().hex[:6]}@example.com"
    r = requests.post(f"{BASE_URL}/api/auth/register", json={
        "name": f"ws_{suffix}",
        "email": email,
        "password": "1234",
        "device_token": f"dev-ws-{suffix}-{uuid.uuid4().hex[:8]}",
    })
    r.raise_for_status()
    user_id = r.json()["id"]
    r2 = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": "1234"})
    r2.raise_for_status()
    return r2.json()["access_token"], user_id


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _min_audio_b64() -> str:
    """最小非空合法 base64，用于 audio_b64 字段。"""
    return base64.b64encode(b"\x00" * 64).decode()


def _ws_connect(session_id: str) -> websocket.WebSocket:
    """连接 WS，返回连接对象（已跳过第一条 connected 消息）。"""
    ws = websocket.create_connection(
        f"{WS_BASE}/ws/sessions/{session_id}",
        timeout=WS_TIMEOUT,
    )
    return ws


def _recv(ws: websocket.WebSocket) -> dict:
    raw = ws.recv()
    return json.loads(raw)


def _send(ws: websocket.WebSocket, payload: dict) -> None:
    ws.send(json.dumps(payload))


def _send_recv(ws: websocket.WebSocket, payload: dict) -> dict:
    _send(ws, payload)
    return _recv(ws)


def _setup(ctx: dict) -> None:
    """
    建立完整测试环境：
    - leader 注册登录 → 建群 → 建会话 → start 会话
    - member 注册登录 → 加入群组
    结果写入 ctx。
    """
    leader_token, leader_id = _register_login(f"leader_{RUN_ID}")
    member_token, member_id = _register_login(f"member_{RUN_ID}")

    # 建群
    r = requests.post(f"{BASE_URL}/api/groups",
                      json={"name": f"ws_group_{RUN_ID}"},
                      headers=_auth(leader_token))
    r.raise_for_status()
    group = r.json()
    group_id = group["group"]["id"]

    # member 加入群组
    r = requests.post(f"{BASE_URL}/api/groups/{group_id}/join",
                      headers=_auth(member_token))
    r.raise_for_status()

    # 建会话
    r = requests.post(f"{BASE_URL}/api/groups/{group_id}/sessions",
                      json={"session_title": f"ws_test_{RUN_ID}"},
                      headers=_auth(leader_token))
    r.raise_for_status()
    session = r.json()
    session_id = session["id"]

    # start 会话（status → ongoing）
    r = requests.post(f"{BASE_URL}/api/sessions/{session_id}/start",
                      headers=_auth(leader_token))
    r.raise_for_status()

    ctx.update({
        "group_id": group_id,
        "session_id": session_id,
        "leader_token": leader_token,
        "member_token": member_token,
        "leader_id": leader_id,
        "member_id": member_id,
    })


# ─────────────────────────── test cases ─────────────────────────────────────


def test_connect_receives_connected(ctx: dict) -> bool:
    ws = _ws_connect(ctx["session_id"])
    try:
        msg = _recv(ws)
        ok = (
            msg.get("type") == "connected"
            and msg.get("data", {}).get("session_id") == ctx["session_id"]
        )
        return _log(ok, "连接后收到 connected 消息", msg if not ok else None)
    finally:
        ws.close()


def test_ping_returns_pong(ctx: dict) -> bool:
    ws = _ws_connect(ctx["session_id"])
    try:
        _recv(ws)  # skip connected
        resp = _send_recv(ws, {"type": "ping", "data": {}})
        ok = resp.get("type") == "pong"
        return _log(ok, "ping → pong", resp if not ok else None)
    finally:
        ws.close()


def test_audio_chunk_valid_ack(ctx: dict) -> bool:
    ws = _ws_connect(ctx["session_id"])
    try:
        _recv(ws)  # skip connected
        resp = _send_recv(ws, {
            "type": "audio_chunk",
            "data": {
                "seq": 1,
                "mime_type": "audio/webm",
                "audio_b64": _min_audio_b64(),
                "duration_ms": 1000,
            },
        })
        ok = (
            resp.get("type") == "audio_chunk_ack"
            and resp.get("data", {}).get("seq") == 1
            and resp.get("data", {}).get("accepted") is True
        )
        return _log(ok, "合法 audio_chunk → audio_chunk_ack (seq=1)", resp if not ok else None)
    finally:
        ws.close()


def test_audio_chunk_seq_increments(ctx: dict) -> bool:
    ws = _ws_connect(ctx["session_id"])
    try:
        _recv(ws)  # skip connected
        results = []
        for seq in [1, 2, 3]:
            resp = _send_recv(ws, {
                "type": "audio_chunk",
                "data": {
                    "seq": seq,
                    "mime_type": "audio/webm",
                    "audio_b64": _min_audio_b64(),
                },
            })
            results.append(resp.get("data", {}).get("seq") == seq)
        ok = all(results)
        return _log(ok, "连续 audio_chunk seq 递增，ACK seq 一致", results if not ok else None)
    finally:
        ws.close()


def test_audio_chunk_missing_seq(ctx: dict) -> bool:
    ws = _ws_connect(ctx["session_id"])
    try:
        _recv(ws)
        resp = _send_recv(ws, {
            "type": "audio_chunk",
            "data": {
                "mime_type": "audio/webm",
                "audio_b64": _min_audio_b64(),
            },
        })
        ok = (
            resp.get("type") == "error"
            and resp.get("data", {}).get("error_code") == "INVALID_AUDIO_CHUNK_SCHEMA"
        )
        return _log(ok, "audio_chunk 缺 seq → INVALID_AUDIO_CHUNK_SCHEMA", resp if not ok else None)
    finally:
        ws.close()


def test_audio_chunk_invalid_mime(ctx: dict) -> bool:
    ws = _ws_connect(ctx["session_id"])
    try:
        _recv(ws)
        resp = _send_recv(ws, {
            "type": "audio_chunk",
            "data": {
                "seq": 1,
                "mime_type": "audio/mp3",
                "audio_b64": _min_audio_b64(),
            },
        })
        ok = (
            resp.get("type") == "error"
            and resp.get("data", {}).get("error_code") == "INVALID_AUDIO_CHUNK_SCHEMA"
        )
        return _log(ok, "audio_chunk mime_type=audio/mp3 → INVALID_AUDIO_CHUNK_SCHEMA", resp if not ok else None)
    finally:
        ws.close()


def test_audio_chunk_invalid_base64(ctx: dict) -> bool:
    ws = _ws_connect(ctx["session_id"])
    try:
        _recv(ws)
        resp = _send_recv(ws, {
            "type": "audio_chunk",
            "data": {
                "seq": 1,
                "mime_type": "audio/webm",
                "audio_b64": "not-valid-base64!!!",
            },
        })
        ok = (
            resp.get("type") == "error"
            and resp.get("data", {}).get("error_code") == "INVALID_AUDIO_CHUNK_SCHEMA"
        )
        return _log(ok, "audio_chunk 非法 base64 → INVALID_AUDIO_CHUNK_SCHEMA", resp if not ok else None)
    finally:
        ws.close()


def test_audio_chunk_too_large(ctx: dict) -> bool:
    ws = _ws_connect(ctx["session_id"])
    try:
        _recv(ws)
        oversized = "A" * 1_500_001
        resp = _send_recv(ws, {
            "type": "audio_chunk",
            "data": {
                "seq": 1,
                "mime_type": "audio/webm",
                "audio_b64": oversized,
            },
        })
        ok = (
            resp.get("type") == "error"
            and resp.get("data", {}).get("error_code") == "INVALID_AUDIO_CHUNK_SCHEMA"
        )
        return _log(ok, "audio_chunk audio_b64 超大 → INVALID_AUDIO_CHUNK_SCHEMA", resp if not ok else None)
    finally:
        ws.close()


def test_unknown_message_type(ctx: dict) -> bool:
    ws = _ws_connect(ctx["session_id"])
    try:
        _recv(ws)
        resp = _send_recv(ws, {"type": "foobar", "data": {}})
        ok = (
            resp.get("type") == "error"
            and resp.get("data", {}).get("error_code") == "UNKNOWN_TYPE"
        )
        return _log(ok, "未知消息类型 → UNKNOWN_TYPE", resp if not ok else None)
    finally:
        ws.close()


def test_invalid_json(ctx: dict) -> bool:
    ws = _ws_connect(ctx["session_id"])
    try:
        _recv(ws)
        ws.send("not json at all{{{")
        resp = _recv(ws)
        ok = (
            resp.get("type") == "error"
            and resp.get("data", {}).get("error_code") == "INVALID_JSON"
        )
        return _log(ok, "非法 JSON → INVALID_JSON", resp if not ok else None)
    finally:
        ws.close()


def test_invalid_schema_not_object(ctx: dict) -> bool:
    ws = _ws_connect(ctx["session_id"])
    try:
        _recv(ws)
        ws.send(json.dumps([1, 2, 3]))
        resp = _recv(ws)
        ok = (
            resp.get("type") == "error"
            and resp.get("data", {}).get("error_code") == "INVALID_SCHEMA"
        )
        return _log(ok, "JSON 数组（非对象）→ INVALID_SCHEMA", resp if not ok else None)
    finally:
        ws.close()


def test_broadcast_two_clients(ctx: dict) -> bool:
    """
    ws1、ws2 同时连接同一 session，
    admin REST 写入一条转写（会触发 broadcast_transcript），
    两个客户端都应收到 transcript 消息。
    """
    session_id = ctx["session_id"]
    group_id = ctx["group_id"]

    ws1 = _ws_connect(session_id)
    ws2 = _ws_connect(session_id)
    try:
        _recv(ws1)  # skip connected
        _recv(ws2)  # skip connected

        now = datetime.now(timezone.utc).isoformat()
        r = requests.post(
            f"{BASE_URL}/api/admin/transcripts/",
            json={
                "session_id": session_id,
                "group_id": group_id,
                "text": f"广播测试_{RUN_ID}",
                "speaker": "测试员",
                "start": now,
                "end": now,
            },
            headers=ADMIN_HEADERS,
        )
        if not r.ok:
            return _log(False, "广播测试：admin 写入转写失败", r.text)

        # 两个 WS 都应收到 transcript
        msg1 = _recv(ws1)
        msg2 = _recv(ws2)

        ok1 = msg1.get("type") == "transcript" and f"广播测试_{RUN_ID}" in str(msg1.get("data", {}).get("text", ""))
        ok2 = msg2.get("type") == "transcript" and f"广播测试_{RUN_ID}" in str(msg2.get("data", {}).get("text", ""))

        ok = ok1 and ok2
        return _log(ok, "广播：两个 WS 客户端均收到 transcript", {
            "ws1": msg1 if not ok1 else "OK",
            "ws2": msg2 if not ok2 else "OK",
        } if not ok else None)
    finally:
        ws1.close()
        ws2.close()


def test_disconnect_cleanup(ctx: dict) -> bool:
    """
    连接后立刻关闭，再重新连接并收发一次 ping/pong，
    验证 ws_manager 清理正常、不受旧连接影响。
    """
    session_id = ctx["session_id"]
    ws_temp = _ws_connect(session_id)
    _recv(ws_temp)  # skip connected
    ws_temp.close()
    time.sleep(0.3)

    ws = _ws_connect(session_id)
    try:
        _recv(ws)  # skip connected
        resp = _send_recv(ws, {"type": "ping", "data": {}})
        ok = resp.get("type") == "pong"
        return _log(ok, "断开后重连 ping/pong 正常（ws_manager 清理验证）", resp if not ok else None)
    finally:
        ws.close()


# ─────────────────────────── main ───────────────────────────────────────────

TESTS = [
    test_connect_receives_connected,
    test_ping_returns_pong,
    test_audio_chunk_valid_ack,
    test_audio_chunk_seq_increments,
    test_audio_chunk_missing_seq,
    test_audio_chunk_invalid_mime,
    test_audio_chunk_invalid_base64,
    test_audio_chunk_too_large,
    test_unknown_message_type,
    test_invalid_json,
    test_invalid_schema_not_object,
    test_broadcast_two_clients,
    test_disconnect_cleanup,
]


def main() -> None:
    print(f"{'='*60}")
    print("WebSocket 集成测试")
    print(f"{'='*60}\n")

    print("⚙️  准备测试环境...")
    ctx: dict = {}
    try:
        _setup(ctx)
        print(f"   session_id = {ctx['session_id']}\n")
    except Exception as e:
        _stop(f"环境准备失败：{e}")

    passed = 0
    for test_fn in TESTS:
        try:
            result = test_fn(ctx)
        except Exception as e:
            _log(False, test_fn.__name__, str(e))
            _stop(f"{test_fn.__name__} 抛出异常：{e}")
            return
        if not result:
            _stop(f"{test_fn.__name__} 失败，停止测试。请检查上方详情。")
            return
        passed += 1

    print(f"\n{'='*60}")
    print(f"✅ 全部 {passed}/{len(TESTS)} 通过")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
