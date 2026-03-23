"""
模块五 + 模块六 集成测试（连着后端跑）

用例分类：
  A. 正常流程（1-5）
  B. 边界场景（6-11）
  C. 异常场景（12-19）
  D. 资源与清理（20-23）

运行前提：后端已启动（env $(cat .env.local | xargs) uvicorn app.main:app --port 8000）
运行方式（在 backend/ 目录下）：
  python tests/test_ws_audio_integration.py
"""
from __future__ import annotations

import base64
import json
import sys
import time
import uuid
from typing import Any

import requests
import websocket

BASE_URL = "http://127.0.0.1:8000"
WS_BASE  = "ws://127.0.0.1:8000"
RUN_ID   = uuid.uuid4().hex[:6]
ADMIN_TOKEN   = "TestAdminKey123"
ADMIN_HEADERS = {"X-Admin-Token": ADMIN_TOKEN}
WS_TIMEOUT    = 5

PASS = 0
FAIL = 0

# ── helpers ──────────────────────────────────────────────────────

def _log(ok: bool, msg: str, extra: Any = None) -> None:
    global PASS, FAIL
    print(f"{'✅' if ok else '❌'} {msg}")
    if not ok and extra is not None:
        print("   详情:", extra)
    if ok:
        PASS += 1
    else:
        FAIL += 1


def _abort(msg: str) -> None:
    print(f"\n🛑 测试中止：{msg}")
    sys.exit(1)


def _register_login(label: str) -> dict:
    ts = int(time.time() * 1000)
    email = f"audio_int_{label}_{RUN_ID}_{ts}@test.com"
    r = requests.post(f"{BASE_URL}/api/auth/register", json={
        "name": label, "email": email, "password": "1234", "device_token": f"tok_{label}"
    })
    if not r.ok:
        _abort(f"注册失败 {label}: {r.text}")
    user_id = r.json()["id"]
    r2 = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": "1234"})
    token = r2.json()["access_token"]
    return {"user_id": user_id, "token": token, "email": email}


def _create_group_session(token: str) -> tuple[str, str]:
    r = requests.post(f"{BASE_URL}/api/groups",
                      json={"name": f"AudioInt_{RUN_ID}_{int(time.time())}"},
                      headers={"Authorization": f"Bearer {token}"})
    group_id = r.json()["group"]["id"]
    r2 = requests.post(f"{BASE_URL}/api/groups/{group_id}/sessions",
                       json={"session_title": f"IntTest_{RUN_ID}"},
                       headers={"Authorization": f"Bearer {token}"})
    session_id = r2.json()["id"]
    requests.post(f"{BASE_URL}/api/sessions/{session_id}/start",
                  headers={"Authorization": f"Bearer {token}"})
    return group_id, session_id


def _make_webm_chunk() -> str:
    """最小合法 WebM EBML 头 base64"""
    data = bytes([
        0x1A,0x45,0xDF,0xA3,0x9F,
        0x42,0x86,0x81,0x01,0x42,0xF7,0x81,0x01,
        0x42,0xF2,0x81,0x04,0x42,0xF3,0x81,0x08,
        0x42,0x82,0x84,0x77,0x65,0x62,0x6D,
        0x42,0x87,0x81,0x02,0x42,0x85,0x81,0x02,
    ])
    return base64.b64encode(data).decode()


def _make_audio_chunk_msg(seq: int, audio_b64: str | None = None) -> str:
    return json.dumps({
        "type": "audio_chunk",
        "data": {
            "seq": seq,
            "mime_type": "audio/webm",
            "audio_b64": audio_b64 or _make_webm_chunk(),
        }
    })


def _ws_connect(session_id: str) -> websocket.WebSocket:
    ws = websocket.WebSocket()
    ws.connect(f"{WS_BASE}/ws/sessions/{session_id}")
    ws.settimeout(WS_TIMEOUT)
    return ws


def _recv(ws: websocket.WebSocket) -> dict | None:
    try:
        return json.loads(ws.recv())
    except Exception:
        return None


def _send_chunk(ws: websocket.WebSocket, seq: int, audio_b64: str | None = None) -> dict | None:
    ws.send(_make_audio_chunk_msg(seq, audio_b64))
    return _recv(ws)


def _add_transcript_admin(session_id: str, group_id: str, speaker: str, text: str) -> bool:
    r = requests.post(f"{BASE_URL}/api/admin/transcripts/",
                      json={"session_id": session_id, "group_id": group_id,
                            "speaker": speaker, "text": text,
                            "start": "2024-01-01T00:00:01Z",
                            "end": "2024-01-01T00:00:05Z"},
                      headers=ADMIN_HEADERS)
    return r.ok


# ── 环境准备 ────────────────────────────────────────────────────

def _setup() -> tuple[dict, str, str]:
    user = _register_login("audio_int")
    group_id, session_id = _create_group_session(user["token"])
    return user, group_id, session_id

# ════════════════════════════════════════════════════════════════
# A. 正常流程
# ════════════════════════════════════════════════════════════════

def test_A1_audio_chunk_returns_ack():
    """A-1: WS 发 audio_chunk → 收到 audio_chunk_ack"""
    _, _, session_id = _setup()
    ws = _ws_connect(session_id)
    _recv(ws)  # connected
    ack = _send_chunk(ws, seq=1)
    ok = ack is not None and ack.get("type") == "audio_chunk_ack" and ack.get("data", {}).get("seq") == 1
    _log(ok, "A-1: audio_chunk → audio_chunk_ack (seq=1)", ack)
    ws.close()


def test_A2_multiple_chunks_ack_seq():
    """A-2: 连续发 5 个 chunk → ACK seq 依次对应"""
    _, _, session_id = _setup()
    ws = _ws_connect(session_id)
    _recv(ws)
    results = []
    for i in range(1, 6):
        ack = _send_chunk(ws, seq=i)
        results.append(ack and ack.get("data", {}).get("seq") == i)
    ok = all(results)
    _log(ok, "A-2: 连续 5 个 chunk → ACK seq 依次对应", results)
    ws.close()


def test_A3_two_clients_receive_broadcast():
    """A-3: 两个 WS 客户端连同一 session，admin 写入 → 两个都收到 transcript"""
    _, group_id, session_id = _setup()
    ws1 = _ws_connect(session_id)
    ws2 = _ws_connect(session_id)
    _recv(ws1)
    _recv(ws2)

    _add_transcript_admin(session_id, group_id, "测试人", "广播测试文本")
    time.sleep(0.5)

    msg1 = _recv(ws1)
    msg2 = _recv(ws2)
    ok = (msg1 and msg1.get("type") == "transcript" and
          msg2 and msg2.get("type") == "transcript")
    _log(ok, "A-3: 两个 WS 客户端均收到 transcript 广播", {"ws1": msg1, "ws2": msg2})
    ws1.close()
    ws2.close()


def test_A4_reconnect_works_after_disconnect():
    """A-4: WS 断开后重连不崩溃，新连接正常收 connected"""
    _, _, session_id = _setup()
    ws = _ws_connect(session_id)
    _recv(ws)
    ws.close()
    time.sleep(0.3)

    ws2 = _ws_connect(session_id)
    msg = _recv(ws2)
    ok = msg is not None and msg.get("type") == "connected"
    _log(ok, "A-4: 断开后重连 → connected 正常", msg)
    ws2.close()


def test_A5_chunk_seq_noncontinuous():
    """A-5: seq 不连续（跳号）→ 每个 ACK 对应正确 seq"""
    _, _, session_id = _setup()
    ws = _ws_connect(session_id)
    _recv(ws)
    seqs = [1, 5, 100, 9999]
    results = []
    for s in seqs:
        ack = _send_chunk(ws, seq=s)
        results.append(ack and ack.get("data", {}).get("seq") == s)
    ok = all(results)
    _log(ok, "A-5: seq 不连续 → 各 ACK seq 正确对应", results)
    ws.close()

# ════════════════════════════════════════════════════════════════
# B. 边界场景
# ════════════════════════════════════════════════════════════════

def test_B6_minimal_webm():
    """B-6: 最小合法 WebM（只有 EBML 头）→ 不崩溃，ACK 正常"""
    _, _, session_id = _setup()
    ws = _ws_connect(session_id)
    _recv(ws)
    ack = _send_chunk(ws, seq=1, audio_b64=_make_webm_chunk())
    ok = ack is not None and ack.get("type") == "audio_chunk_ack"
    _log(ok, "B-6: 最小 WebM → 不崩溃，ACK 正常", ack)
    ws.close()


def test_B7_single_byte_audio():
    """B-7: audio_b64 解码后只有 1 字节 → 后端不崩溃，返回 ACK"""
    _, _, session_id = _setup()
    ws = _ws_connect(session_id)
    _recv(ws)
    single_byte = base64.b64encode(b"\x00").decode()
    ack = _send_chunk(ws, seq=1, audio_b64=single_byte)
    ok = ack is not None and ack.get("type") == "audio_chunk_ack"
    _log(ok, "B-7: 单字节音频 → 不崩溃，ACK 正常", ack)
    ws.close()


def test_B8_max_size_chunk():
    """B-8: 发送接近最大限制的分片（1.4MB base64）→ ACK 正常，不超时"""
    _, _, session_id = _setup()
    ws = _ws_connect(session_id)
    ws.settimeout(15)
    _recv(ws)
    big_bytes = b"\x1A\x45\xDF\xA3" + b"\x00" * (1_000_000)
    big_b64 = base64.b64encode(big_bytes).decode()
    ack = _send_chunk(ws, seq=1, audio_b64=big_b64)
    ok = ack is not None and ack.get("type") == "audio_chunk_ack"
    _log(ok, "B-8: 接近最大分片 → ACK 正常（无超时）", ack)
    ws.close()


def test_B9_hundred_chunks():
    """B-9: 快速发 100 个 chunk → 全部 ACK，无丢失"""
    _, _, session_id = _setup()
    ws = _ws_connect(session_id)
    ws.settimeout(30)
    _recv(ws)
    failed = []
    for i in range(1, 101):
        ack = _send_chunk(ws, seq=i)
        if not ack or ack.get("data", {}).get("seq") != i:
            failed.append(i)
    ok = len(failed) == 0
    _log(ok, f"B-9: 100 个 chunk 全部 ACK（失败：{len(failed)} 个）", failed[:5] if failed else None)
    ws.close()


def test_B10_seq_zero():
    """B-10: seq=0 → ACK 正常（边界值）"""
    _, _, session_id = _setup()
    ws = _ws_connect(session_id)
    _recv(ws)
    ack = _send_chunk(ws, seq=0)
    ok = ack is not None and ack.get("data", {}).get("seq") == 0
    _log(ok, "B-10: seq=0 → ACK 正常", ack)
    ws.close()


def test_B11_create_destroy_cycle():
    """B-11: 同一 session 连续建立/断开 5 次 → 服务不崩溃，第 5 次仍正常"""
    _, _, session_id = _setup()
    for i in range(5):
        ws = _ws_connect(session_id)
        _recv(ws)
        _send_chunk(ws, seq=i)
        ws.close()
        time.sleep(0.2)

    ws = _ws_connect(session_id)
    msg = _recv(ws)
    ok = msg is not None and msg.get("type") == "connected"
    _log(ok, "B-11: 5 次建立/断开后第 5 次仍正常连接", msg)
    ws.close()

# ════════════════════════════════════════════════════════════════
# C. 异常场景
# ════════════════════════════════════════════════════════════════

def test_C12_corrupted_webm():
    """C-12: 发送完全随机 bytes（不是 WebM）→ 后端不崩溃，ACK 正常"""
    _, _, session_id = _setup()
    ws = _ws_connect(session_id)
    _recv(ws)
    garbage = base64.b64encode(b"\xFF\xFE\xAB\xCD" * 500).decode()
    ack = _send_chunk(ws, seq=1, audio_b64=garbage)
    ok = ack is not None and ack.get("type") == "audio_chunk_ack"
    _log(ok, "C-12: 损坏 WebM → 不崩溃，ACK 正常", ack)
    ws.close()


def test_C13_missing_seq():
    """C-13: audio_chunk 缺少 seq 字段 → INVALID_AUDIO_CHUNK_SCHEMA"""
    _, _, session_id = _setup()
    ws = _ws_connect(session_id)
    _recv(ws)
    ws.send(json.dumps({
        "type": "audio_chunk",
        "data": {"mime_type": "audio/webm", "audio_b64": _make_webm_chunk()}
    }))
    msg = _recv(ws)
    ok = msg is not None and msg.get("data", {}).get("error_code") == "INVALID_AUDIO_CHUNK_SCHEMA"
    _log(ok, "C-13: 缺 seq → INVALID_AUDIO_CHUNK_SCHEMA", msg)
    ws.close()


def test_C14_wrong_mime_type():
    """C-14: mime_type 非 audio/webm → INVALID_AUDIO_CHUNK_SCHEMA"""
    _, _, session_id = _setup()
    ws = _ws_connect(session_id)
    _recv(ws)
    ws.send(json.dumps({
        "type": "audio_chunk",
        "data": {"seq": 1, "mime_type": "audio/mp3", "audio_b64": _make_webm_chunk()}
    }))
    msg = _recv(ws)
    ok = msg is not None and msg.get("data", {}).get("error_code") == "INVALID_AUDIO_CHUNK_SCHEMA"
    _log(ok, "C-14: 非法 mime_type → INVALID_AUDIO_CHUNK_SCHEMA", msg)
    ws.close()


def test_C15_invalid_base64():
    """C-15: audio_b64 不是合法 base64 → INVALID_AUDIO_CHUNK_SCHEMA"""
    _, _, session_id = _setup()
    ws = _ws_connect(session_id)
    _recv(ws)
    ws.send(json.dumps({
        "type": "audio_chunk",
        "data": {"seq": 1, "mime_type": "audio/webm", "audio_b64": "!!!not_base64!!!"}
    }))
    msg = _recv(ws)
    ok = msg is not None and msg.get("data", {}).get("error_code") == "INVALID_AUDIO_CHUNK_SCHEMA"
    _log(ok, "C-15: 非法 base64 → INVALID_AUDIO_CHUNK_SCHEMA", msg)
    ws.close()


def test_C16_oversized_chunk():
    """C-16: audio_b64 超过 1.5MB → INVALID_AUDIO_CHUNK_SCHEMA"""
    _, _, session_id = _setup()
    ws = _ws_connect(session_id)
    ws.settimeout(15)
    _recv(ws)
    over_limit = base64.b64encode(b"\x00" * 1_200_000).decode()
    ws.send(json.dumps({
        "type": "audio_chunk",
        "data": {"seq": 1, "mime_type": "audio/webm", "audio_b64": over_limit}
    }))
    msg = _recv(ws)
    ok = msg is not None and msg.get("data", {}).get("error_code") == "INVALID_AUDIO_CHUNK_SCHEMA"
    _log(ok, "C-16: 超大 audio_b64 → INVALID_AUDIO_CHUNK_SCHEMA", msg)
    ws.close()


def test_C17_empty_audio_b64():
    """C-17: audio_b64 为空字符串 → INVALID_AUDIO_CHUNK_SCHEMA"""
    _, _, session_id = _setup()
    ws = _ws_connect(session_id)
    _recv(ws)
    ws.send(json.dumps({
        "type": "audio_chunk",
        "data": {"seq": 1, "mime_type": "audio/webm", "audio_b64": ""}
    }))
    msg = _recv(ws)
    ok = msg is not None and msg.get("data", {}).get("error_code") == "INVALID_AUDIO_CHUNK_SCHEMA"
    _log(ok, "C-17: 空 audio_b64 → INVALID_AUDIO_CHUNK_SCHEMA", msg)
    ws.close()


def test_C18_unknown_message_type():
    """C-18: 未知消息类型 → UNKNOWN_TYPE"""
    _, _, session_id = _setup()
    ws = _ws_connect(session_id)
    _recv(ws)
    ws.send(json.dumps({"type": "unknown_xyz", "data": {}}))
    msg = _recv(ws)
    ok = msg is not None and msg.get("data", {}).get("error_code") == "UNKNOWN_TYPE"
    _log(ok, "C-18: 未知类型 → UNKNOWN_TYPE", msg)
    ws.close()


def test_C19_invalid_json():
    """C-19: 非法 JSON → INVALID_JSON"""
    _, _, session_id = _setup()
    ws = _ws_connect(session_id)
    _recv(ws)
    ws.send("{{not_json}}")
    msg = _recv(ws)
    ok = msg is not None and msg.get("data", {}).get("error_code") == "INVALID_JSON"
    _log(ok, "C-19: 非法 JSON → INVALID_JSON", msg)
    ws.close()

# ════════════════════════════════════════════════════════════════
# D. 资源与清理
# ════════════════════════════════════════════════════════════════

def test_D20_server_still_alive_after_all():
    """D-20: 全部测试后服务仍可用（健康检查）"""
    try:
        r = requests.get(f"{BASE_URL}/", timeout=3)
        ok = r.status_code == 200
    except Exception as e:
        ok = False
        _log(ok, "D-20: 全部测试后服务仍可用", str(e))
        return
    _log(ok, "D-20: 全部测试后服务仍可用（GET / 返回 200）")


def test_D21_concurrent_sessions():
    """D-21: 多个 session 并发发 chunk → 各自 ACK 独立，互不干扰"""
    user = _register_login("concurrent")
    results = []
    sessions = []
    for _ in range(3):
        gid, sid = _create_group_session(user["token"])
        sessions.append(sid)

    wss = [_ws_connect(sid) for sid in sessions]
    for ws in wss:
        _recv(ws)

    for i, ws in enumerate(wss):
        ack = _send_chunk(ws, seq=i + 1)
        results.append(ack and ack.get("data", {}).get("seq") == i + 1)

    ok = all(results)
    _log(ok, "D-21: 3 个并发 session 各自 ACK 正确", results)
    for ws in wss:
        ws.close()


def test_D22_broadcast_only_to_same_session():
    """D-22: session A 广播不影响 session B 的 WS 客户端"""
    user = _register_login("isolation")
    gid_a, sid_a = _create_group_session(user["token"])
    gid_b, sid_b = _create_group_session(user["token"])

    ws_a = _ws_connect(sid_a)
    ws_b = _ws_connect(sid_b)
    _recv(ws_a)
    _recv(ws_b)

    _add_transcript_admin(sid_a, gid_a, "A说话人", "只有A应收到")
    time.sleep(0.5)

    msg_a = _recv(ws_a)
    ws_b.settimeout(1)
    try:
        msg_b = _recv(ws_b)
    except Exception:
        msg_b = None

    ok = (msg_a and msg_a.get("type") == "transcript") and msg_b is None
    _log(ok, "D-22: session A 广播不泄漏到 session B",
         {"ws_a_got": msg_a and msg_a.get("type"), "ws_b_got": msg_b})
    ws_a.close()
    ws_b.close()


def test_D23_new_connection_after_heavy_load():
    """D-23: 压测 50 个 chunk 后，新连接仍正常"""
    _, _, session_id = _setup()
    ws = _ws_connect(session_id)
    ws.settimeout(30)
    _recv(ws)
    for i in range(50):
        _send_chunk(ws, seq=i)
    ws.close()
    time.sleep(0.3)

    ws2 = _ws_connect(session_id)
    msg = _recv(ws2)
    ok = msg is not None and msg.get("type") == "connected"
    _log(ok, "D-23: 50 chunk 压测后新连接仍正常", msg)
    ws2.close()

# ── 入口 ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("模块五 + 模块六 集成测试")
    print("=" * 60)

    # A. 正常流程
    print("\n── A. 正常流程 ──")
    test_A1_audio_chunk_returns_ack()
    test_A2_multiple_chunks_ack_seq()
    test_A3_two_clients_receive_broadcast()
    test_A4_reconnect_works_after_disconnect()
    test_A5_chunk_seq_noncontinuous()

    # B. 边界场景
    print("\n── B. 边界场景 ──")
    test_B6_minimal_webm()
    test_B7_single_byte_audio()
    test_B8_max_size_chunk()
    test_B9_hundred_chunks()
    test_B10_seq_zero()
    test_B11_create_destroy_cycle()

    # C. 异常场景
    print("\n── C. 异常场景 ──")
    test_C12_corrupted_webm()
    test_C13_missing_seq()
    test_C14_wrong_mime_type()
    test_C15_invalid_base64()
    test_C16_oversized_chunk()
    test_C17_empty_audio_b64()
    test_C18_unknown_message_type()
    test_C19_invalid_json()

    # D. 资源与清理
    print("\n── D. 资源与清理 ──")
    test_D20_server_still_alive_after_all()
    test_D21_concurrent_sessions()
    test_D22_broadcast_only_to_same_session()
    test_D23_new_connection_after_heavy_load()

    print("\n" + "=" * 60)
    total = PASS + FAIL
    print(f"{'✅' if FAIL == 0 else '❌'} 全部 {PASS}/{total} 通过")
    print("=" * 60)
    sys.exit(0 if FAIL == 0 else 1)
