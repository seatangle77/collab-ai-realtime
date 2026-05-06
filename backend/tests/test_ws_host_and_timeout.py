"""
WS 主机识别 + 心跳超时 + session_ended 广播 集成测试

测试用例（快速，约 60s）：
  T3-1: 有效 token（created_by 用户）→ connected，无错误
  T3-2: 有效 token（非 created_by 成员）→ connected，静默 6s 不超时
  T3-3: 无 token 参数 → connected，不报错
  T3-4: 非法 token 字符串 → connected（降级），不断连
  T4-5: host 快速连发多个 ping → 不崩溃，均收到 pong
  T4-6: host 干净断线后重连 → 会话继续，仍能 ping/pong

测试用例（慢速，需 --include-slow）：
  T4-1: host 151s 无消息 → session_ended{reason: host_timeout}，DB status=ended（约 155s）
  T4-2: host 分两段 ping，总计 50s → 不超时，两次均得到 pong（约 55s）
  T4-3: 参与者静默 35s → 不超时，host 无需频繁 ping 保活（约 40s）
  T4-4: host 在第 30s 发 ping（旧超时边界）→ 会话继续（约 35s）
  T5-1: host 超时 → host + guest 两端均收到 session_ended（约 155s）
  T5-2: 超时时只有 host 在线 → session_ended 正常，不崩溃（约 155s）
  T5-3: host + 2 个 guest → 三端均收到 session_ended（约 155s）

运行：
  # 快速测试（T3 + T4-5/6，约 60s）
  python tests/test_ws_host_and_timeout.py

  # 含慢速测试（全部，约 15-20 分钟）
  python tests/test_ws_host_and_timeout.py --include-slow

运行前提：后端已启动（uvicorn backend.app.main:app --reload --port 8000）
依赖：pip install websocket-client requests
"""
from __future__ import annotations

import json
import sys
import time
import uuid
from typing import Any, Dict, List, Tuple

import requests
import websocket  # websocket-client

BASE_URL = "http://127.0.0.1:8000"
WS_BASE = "ws://127.0.0.1:8000"
RUN_ID = uuid.uuid4().hex[:6]

HEARTBEAT_TIMEOUT = 150  # 与后端 ws_sessions.py 保持一致
FAST_WS_TIMEOUT = 5      # 快速用例等待消息超时
SLOW_WS_TIMEOUT = 160    # 慢速用例等待超时消息（须 > HEARTBEAT_TIMEOUT）


def _log(ok: bool, msg: str, extra: Any = None) -> bool:
    print(f"{'✅' if ok else '❌'} {msg}")
    if not ok and extra is not None:
        print("   详情:", extra)
    return ok


def _auth(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def register_and_login(name: str, suffix: str) -> Tuple[str, str]:
    email = f"wshost_{suffix}_{uuid.uuid4().hex[:6]}@example.com"
    r = requests.post(f"{BASE_URL}/api/auth/register", json={
        "name": name,
        "email": email,
        "password": "1234",
        "device_token": f"dev-wshost-{suffix}-{uuid.uuid4().hex[:8]}",
    })
    r.raise_for_status()
    user_id = r.json()["id"]
    r2 = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": "1234"})
    r2.raise_for_status()
    return r2.json()["access_token"], user_id


def _ws_connect(session_id: str, token: str | None = None, timeout: int = FAST_WS_TIMEOUT) -> websocket.WebSocket:
    url = f"{WS_BASE}/ws/sessions/{session_id}"
    if token:
        url += f"?token={token}"
    ws = websocket.create_connection(url, timeout=timeout)
    return ws


def _recv(ws: websocket.WebSocket) -> Dict[str, Any]:
    raw = ws.recv()
    return json.loads(raw)


def _send(ws: websocket.WebSocket, msg_type: str, data: Dict[str, Any]) -> None:
    ws.send(json.dumps({"type": msg_type, "data": data}))


def _end_any_ongoing(leader_token: str, group_id: str) -> None:
    """结束 group 内所有 ongoing 会话，避免下一个 start 触发 409。"""
    r = requests.get(
        f"{BASE_URL}/api/groups/{group_id}/sessions",
        headers=_auth(leader_token),
    )
    if r.status_code != 200:
        return
    for s in r.json():
        if s.get("status") == "ongoing":
            requests.post(
                f"{BASE_URL}/api/sessions/{s['id']}/end",
                headers=_auth(leader_token),
            )


def _create_ongoing_session(leader_token: str, group_id: str, title: str) -> str:
    _end_any_ongoing(leader_token, group_id)
    r = requests.post(
        f"{BASE_URL}/api/groups/{group_id}/sessions",
        json={"session_title": title},
        headers=_auth(leader_token),
    )
    r.raise_for_status()
    session_id = r.json()["id"]
    requests.post(
        f"{BASE_URL}/api/sessions/{session_id}/start",
        headers=_auth(leader_token),
    ).raise_for_status()
    return session_id


def _verify_session_status(session_id: str, leader_token: str, group_id: str) -> str | None:
    """返回会话当前 status 字符串，查询失败返回 None。"""
    r = requests.get(
        f"{BASE_URL}/api/groups/{group_id}/sessions",
        params={"include_ended": "true"},
        headers=_auth(leader_token),
    )
    if r.status_code != 200:
        return None
    sessions = r.json()
    target = next((s for s in sessions if s["id"] == session_id), None)
    return target["status"] if target else None


def _verify_session_ended(session_id: str, leader_token: str, group_id: str) -> bool:
    return _verify_session_status(session_id, leader_token, group_id) == "ended"


# ─────────────────────── setup ───────────────────────────────────────────────


def setup(ctx: Dict[str, Any]) -> bool:
    ctx["leader_token"], ctx["leader_user_id"] = register_and_login(f"WS Leader {RUN_ID}", "leader")
    ctx["member_token"], ctx["member_user_id"] = register_and_login(f"WS Member {RUN_ID}", "member")
    ctx["guest2_token"], ctx["guest2_user_id"] = register_and_login(f"WS Guest2 {RUN_ID}", "guest2")

    r = requests.post(
        f"{BASE_URL}/api/groups",
        json={"name": f"WS Host Test Group {RUN_ID}"},
        headers=_auth(ctx["leader_token"]),
    )
    if r.status_code != 201:
        return _log(False, "setup: 创建 group 失败", {"status": r.status_code, "body": r.text})
    ctx["group_id"] = r.json()["group"]["id"]

    for tok_key in ["member_token", "guest2_token"]:
        r = requests.post(
            f"{BASE_URL}/api/groups/{ctx['group_id']}/join",
            headers=_auth(ctx[tok_key]),
        )
        if r.status_code != 200:
            return _log(False, f"setup: {tok_key} 加入 group 失败",
                        {"status": r.status_code, "body": r.text})

    return _log(True, "setup: 3 个用户注册 + 加入 group 成功")


# ═══════════════════════════════════════════════════════════════════════
#  快速用例：T3 主机识别
# ═══════════════════════════════════════════════════════════════════════


def t3_1_host_token_connects(ctx: Dict[str, Any]) -> bool:
    """有效 host token → connected 消息，无错误"""
    session_id = _create_ongoing_session(
        ctx["leader_token"], ctx["group_id"], f"T3-1 {RUN_ID}"
    )
    ws = None
    try:
        ws = _ws_connect(session_id, ctx["leader_token"])
        msg = _recv(ws)
        ok = msg.get("type") == "connected"
        ok &= msg.get("data", {}).get("session_id") == session_id
        return _log(ok, "T3-1: host token 连接 → 收到 connected", msg)
    except Exception as e:
        return _log(False, "T3-1: 异常", str(e))
    finally:
        if ws:
            try:
                ws.close()
            except Exception:
                pass
        requests.post(f"{BASE_URL}/api/sessions/{session_id}/end",
                      headers=_auth(ctx["leader_token"]))


def t3_2_member_token_no_timeout(ctx: Dict[str, Any]) -> bool:
    """非 created_by 成员的 token → connected，静默 6s 不超时（is_host=False 无 wait_for）"""
    session_id = _create_ongoing_session(
        ctx["leader_token"], ctx["group_id"], f"T3-2 {RUN_ID}"
    )
    ws = None
    try:
        ws = _ws_connect(session_id, ctx["member_token"], timeout=FAST_WS_TIMEOUT)
        msg = _recv(ws)
        if msg.get("type") != "connected":
            return _log(False, "T3-2: 未收到 connected", msg)

        time.sleep(6)

        _send(ws, "ping", {})
        ws.settimeout(FAST_WS_TIMEOUT)
        pong = _recv(ws)
        ok = pong.get("type") == "pong"
        return _log(ok, "T3-2: member token 静默 6s 后 ping 仍得到 pong（未超时）", pong)
    except Exception as e:
        return _log(False, "T3-2: 异常", str(e))
    finally:
        if ws:
            try:
                ws.close()
            except Exception:
                pass
        requests.post(f"{BASE_URL}/api/sessions/{session_id}/end",
                      headers=_auth(ctx["leader_token"]))


def t3_3_no_token_connects(ctx: Dict[str, Any]) -> bool:
    """无 token 参数 → connected，不报错（降级为 is_host=False）"""
    session_id = _create_ongoing_session(
        ctx["leader_token"], ctx["group_id"], f"T3-3 {RUN_ID}"
    )
    ws = None
    try:
        ws = _ws_connect(session_id, token=None)
        msg = _recv(ws)
        ok = msg.get("type") == "connected"
        return _log(ok, "T3-3: 无 token → connected（不断连）", msg)
    except Exception as e:
        return _log(False, "T3-3: 异常", str(e))
    finally:
        if ws:
            try:
                ws.close()
            except Exception:
                pass
        requests.post(f"{BASE_URL}/api/sessions/{session_id}/end",
                      headers=_auth(ctx["leader_token"]))


def t3_4_invalid_token_connects(ctx: Dict[str, Any]) -> bool:
    """非法 token 字符串 → connected（降级，不断连）"""
    session_id = _create_ongoing_session(
        ctx["leader_token"], ctx["group_id"], f"T3-4 {RUN_ID}"
    )
    ws = None
    try:
        ws = _ws_connect(session_id, token="not.a.valid.jwt.token")
        msg = _recv(ws)
        ok = msg.get("type") == "connected"
        return _log(ok, "T3-4: 非法 token → connected（降级，不断连）", msg)
    except Exception as e:
        return _log(False, "T3-4: 异常", str(e))
    finally:
        if ws:
            try:
                ws.close()
            except Exception:
                pass
        requests.post(f"{BASE_URL}/api/sessions/{session_id}/end",
                      headers=_auth(ctx["leader_token"]))


# ═══════════════════════════════════════════════════════════════════════
#  快速用例：T4-5 T4-6（新增，不需等待超时）
# ═══════════════════════════════════════════════════════════════════════


def t4_5_rapid_ping_no_crash(ctx: Dict[str, Any]) -> bool:
    """host 短时间内连发 10 个 ping → 均收到 pong，后端不崩溃"""
    session_id = _create_ongoing_session(
        ctx["leader_token"], ctx["group_id"], f"T4-5 {RUN_ID}"
    )
    ws = None
    try:
        ws = _ws_connect(session_id, ctx["leader_token"])
        msg = _recv(ws)
        if msg.get("type") != "connected":
            return _log(False, "T4-5: 未收到 connected", msg)

        pong_count = 0
        for _ in range(10):
            _send(ws, "ping", {})
        ws.settimeout(FAST_WS_TIMEOUT)
        for _ in range(10):
            resp = _recv(ws)
            if resp.get("type") == "pong":
                pong_count += 1

        ok = pong_count == 10
        return _log(ok, f"T4-5: 连发 10 个 ping → 收到 {pong_count}/10 个 pong", None)
    except Exception as e:
        return _log(False, "T4-5: 异常", str(e))
    finally:
        if ws:
            try:
                ws.close()
            except Exception:
                pass
        requests.post(f"{BASE_URL}/api/sessions/{session_id}/end",
                      headers=_auth(ctx["leader_token"]))


def t4_6_host_reconnect_session_continues(ctx: Dict[str, Any]) -> bool:
    """host 干净断线后重连 → 会话仍为 ongoing，重连后能正常 ping/pong"""
    session_id = _create_ongoing_session(
        ctx["leader_token"], ctx["group_id"], f"T4-6 {RUN_ID}"
    )
    ws1 = ws2 = None
    try:
        ws1 = _ws_connect(session_id, ctx["leader_token"])
        msg = _recv(ws1)
        if msg.get("type") != "connected":
            return _log(False, "T4-6: 初次连接未收到 connected", msg)

        # 干净断开（模拟刷新页面）
        ws1.close()
        ws1 = None
        time.sleep(1)

        # 重连
        ws2 = _ws_connect(session_id, ctx["leader_token"])
        msg2 = _recv(ws2)
        if msg2.get("type") != "connected":
            return _log(False, "T4-6: 重连后未收到 connected", msg2)

        # 重连后 ping/pong 正常
        _send(ws2, "ping", {})
        ws2.settimeout(FAST_WS_TIMEOUT)
        pong = _recv(ws2)
        pong_ok = pong.get("type") == "pong"

        # DB 确认会话仍为 ongoing
        status = _verify_session_status(session_id, ctx["leader_token"], ctx["group_id"])
        status_ok = status == "ongoing"

        ok = pong_ok and status_ok
        return _log(ok, "T4-6: host 重连后 ping/pong 正常，会话仍为 ongoing",
                    {"pong": pong, "db_status": status})
    except Exception as e:
        return _log(False, "T4-6: 异常", str(e))
    finally:
        if ws1:
            try:
                ws1.close()
            except Exception:
                pass
        if ws2:
            try:
                ws2.close()
            except Exception:
                pass
        requests.post(f"{BASE_URL}/api/sessions/{session_id}/end",
                      headers=_auth(ctx["leader_token"]))


# ═══════════════════════════════════════════════════════════════════════
#  慢速用例：T4 心跳超时
# ═══════════════════════════════════════════════════════════════════════


def t4_1_host_timeout_ends_session(ctx: Dict[str, Any]) -> bool:
    """host 超过 150s 无 ping → session_ended{reason: host_timeout}，DB status=ended"""
    wait = HEARTBEAT_TIMEOUT + 1
    print(f"   ⏳ T4-1 等待 {wait}s（host 超时）...")
    session_id = _create_ongoing_session(
        ctx["leader_token"], ctx["group_id"], f"T4-1 {RUN_ID}"
    )
    ws = None
    try:
        ws = _ws_connect(session_id, ctx["leader_token"], timeout=SLOW_WS_TIMEOUT)
        msg = _recv(ws)
        if msg.get("type") != "connected":
            return _log(False, "T4-1: 未收到 connected", msg)

        time.sleep(wait)

        ws.settimeout(SLOW_WS_TIMEOUT)
        ended_msg = _recv(ws)
        ok = ended_msg.get("type") == "session_ended"
        ok &= ended_msg.get("data", {}).get("reason") == "host_timeout"

        db_ended = _verify_session_ended(session_id, ctx["leader_token"], ctx["group_id"])
        ok &= db_ended

        return _log(ok, "T4-1: host 超时 → session_ended + DB status=ended",
                    {"ws_msg": ended_msg, "db_ended": db_ended})
    except Exception as e:
        return _log(False, "T4-1: 异常", str(e))
    finally:
        if ws:
            try:
                ws.close()
            except Exception:
                pass


def t4_2_host_ping_resets_timer(ctx: Dict[str, Any]) -> bool:
    """host 在 25s、50s 各 ping 一次 → 两次均得到 pong，计时器每次重置，连接不中断"""
    print("   ⏳ T4-2 等待约 55s（ping 重置计时器验证）...")
    session_id = _create_ongoing_session(
        ctx["leader_token"], ctx["group_id"], f"T4-2 {RUN_ID}"
    )
    ws = None
    try:
        ws = _ws_connect(session_id, ctx["leader_token"], timeout=SLOW_WS_TIMEOUT)
        msg = _recv(ws)
        if msg.get("type") != "connected":
            return _log(False, "T4-2: 未收到 connected", msg)

        # 第 25s ping
        time.sleep(25)
        _send(ws, "ping", {})
        ws.settimeout(FAST_WS_TIMEOUT)
        pong1 = _recv(ws)
        if pong1.get("type") != "pong":
            return _log(False, "T4-2: 第 25s ping 未收到 pong", pong1)

        # 第 50s ping（每次 ping 后计时器重置，不会在第 150s 处累计超时）
        time.sleep(25)
        _send(ws, "ping", {})
        ws.settimeout(FAST_WS_TIMEOUT)
        pong2 = _recv(ws)
        ok = pong2.get("type") == "pong"
        return _log(ok, "T4-2: 25s/50s ping 均收到 pong，计时器正确重置", pong2)
    except Exception as e:
        return _log(False, "T4-2: 异常", str(e))
    finally:
        if ws:
            try:
                ws.close()
            except Exception:
                pass
        requests.post(f"{BASE_URL}/api/sessions/{session_id}/end",
                      headers=_auth(ctx["leader_token"]))


def t4_3_member_no_timeout(ctx: Dict[str, Any]) -> bool:
    """参与者静默 35s → 不超时；host 在 150s 窗口内无需频繁 ping 保活"""
    print("   ⏳ T4-3 等待约 36s（参与者无超时验证）...")
    session_id = _create_ongoing_session(
        ctx["leader_token"], ctx["group_id"], f"T4-3 {RUN_ID}"
    )
    ws_member = ws_host = None
    try:
        # host 连接（35s < 150s，不会触发超时，无需中途 ping）
        ws_host = _ws_connect(session_id, ctx["leader_token"], timeout=SLOW_WS_TIMEOUT)
        _recv(ws_host)  # connected

        ws_member = _ws_connect(session_id, ctx["member_token"], timeout=SLOW_WS_TIMEOUT)
        msg = _recv(ws_member)
        if msg.get("type") != "connected":
            return _log(False, "T4-3: member 未收到 connected", msg)

        time.sleep(35)

        _send(ws_member, "ping", {})
        ws_member.settimeout(FAST_WS_TIMEOUT)
        pong = _recv(ws_member)
        ok = pong.get("type") == "pong"
        return _log(ok, "T4-3: member 静默 35s 后 ping 仍得到 pong（无超时）", pong)
    except Exception as e:
        return _log(False, "T4-3: 异常", str(e))
    finally:
        for ws in [ws_member, ws_host]:
            if ws:
                try:
                    ws.close()
                except Exception:
                    pass
        requests.post(f"{BASE_URL}/api/sessions/{session_id}/end",
                      headers=_auth(ctx["leader_token"]))


def t4_4_host_ping_at_old_boundary(ctx: Dict[str, Any]) -> bool:
    """host 在第 30s 发 ping（旧超时边界）→ 不超时，会话继续（验证 150s 修复效果）"""
    print("   ⏳ T4-4 等待约 35s（旧 30s 边界回归验证）...")
    session_id = _create_ongoing_session(
        ctx["leader_token"], ctx["group_id"], f"T4-4 {RUN_ID}"
    )
    ws = None
    try:
        ws = _ws_connect(session_id, ctx["leader_token"], timeout=SLOW_WS_TIMEOUT)
        msg = _recv(ws)
        if msg.get("type") != "connected":
            return _log(False, "T4-4: 未收到 connected", msg)

        # 在旧 30s 超时点发 ping，期望仍得到 pong（而非 session_ended）
        time.sleep(30)
        _send(ws, "ping", {})
        ws.settimeout(FAST_WS_TIMEOUT)
        resp = _recv(ws)

        pong_ok = resp.get("type") == "pong"
        not_ended = resp.get("type") != "session_ended"

        # 额外确认 DB 状态
        status = _verify_session_status(session_id, ctx["leader_token"], ctx["group_id"])
        db_ongoing = status == "ongoing"

        ok = pong_ok and db_ongoing
        return _log(ok, "T4-4: 第 30s ping → 收到 pong，会话仍为 ongoing（旧超时边界已修复）",
                    {"resp": resp, "db_status": status, "not_ended": not_ended})
    except Exception as e:
        return _log(False, "T4-4: 异常", str(e))
    finally:
        if ws:
            try:
                ws.close()
            except Exception:
                pass
        requests.post(f"{BASE_URL}/api/sessions/{session_id}/end",
                      headers=_auth(ctx["leader_token"]))


# ═══════════════════════════════════════════════════════════════════════
#  慢速用例：T5 session_ended 广播
# ═══════════════════════════════════════════════════════════════════════


def t5_1_timeout_broadcast_to_all(ctx: Dict[str, Any]) -> bool:
    """host 超时 → host + guest 两端均收到 session_ended{reason: host_timeout}"""
    wait = HEARTBEAT_TIMEOUT + 1
    print(f"   ⏳ T5-1 等待 {wait}s（广播验证）...")
    session_id = _create_ongoing_session(
        ctx["leader_token"], ctx["group_id"], f"T5-1 {RUN_ID}"
    )
    ws_host = ws_guest = None
    try:
        ws_host = _ws_connect(session_id, ctx["leader_token"], timeout=SLOW_WS_TIMEOUT)
        _recv(ws_host)  # connected

        ws_guest = _ws_connect(session_id, ctx["member_token"], timeout=SLOW_WS_TIMEOUT)
        _recv(ws_guest)  # connected

        time.sleep(wait)

        ws_host.settimeout(SLOW_WS_TIMEOUT)
        host_msg = _recv(ws_host)
        ws_guest.settimeout(SLOW_WS_TIMEOUT)
        guest_msg = _recv(ws_guest)

        ok = host_msg.get("type") == "session_ended"
        ok &= host_msg.get("data", {}).get("reason") == "host_timeout"
        ok &= guest_msg.get("type") == "session_ended"
        ok &= guest_msg.get("data", {}).get("reason") == "host_timeout"
        return _log(ok, "T5-1: host 超时 → host + guest 均收到 session_ended",
                    {"host_msg": host_msg, "guest_msg": guest_msg})
    except Exception as e:
        return _log(False, "T5-1: 异常", str(e))
    finally:
        for ws in [ws_host, ws_guest]:
            if ws:
                try:
                    ws.close()
                except Exception:
                    pass


def t5_2_timeout_only_host_online(ctx: Dict[str, Any]) -> bool:
    """超时时只有 host 在线 → session_ended 正常，后端不崩溃"""
    wait = HEARTBEAT_TIMEOUT + 1
    print(f"   ⏳ T5-2 等待 {wait}s（单 host 超时）...")
    session_id = _create_ongoing_session(
        ctx["leader_token"], ctx["group_id"], f"T5-2 {RUN_ID}"
    )
    ws = None
    try:
        ws = _ws_connect(session_id, ctx["leader_token"], timeout=SLOW_WS_TIMEOUT)
        _recv(ws)  # connected

        time.sleep(wait)

        ws.settimeout(SLOW_WS_TIMEOUT)
        msg = _recv(ws)
        ok = msg.get("type") == "session_ended"

        db_ended = _verify_session_ended(session_id, ctx["leader_token"], ctx["group_id"])
        ok &= db_ended
        return _log(ok, "T5-2: 只有 host 在线时超时 → session_ended + DB ended",
                    {"msg": msg, "db_ended": db_ended})
    except Exception as e:
        return _log(False, "T5-2: 异常", str(e))
    finally:
        if ws:
            try:
                ws.close()
            except Exception:
                pass


def t5_3_timeout_three_clients(ctx: Dict[str, Any]) -> bool:
    """host + 2 个 guest 同时在线，host 超时 → 三端均收到 session_ended"""
    wait = HEARTBEAT_TIMEOUT + 1
    print(f"   ⏳ T5-3 等待 {wait}s（三端广播）...")
    session_id = _create_ongoing_session(
        ctx["leader_token"], ctx["group_id"], f"T5-3 {RUN_ID}"
    )
    connections: List[websocket.WebSocket] = []
    try:
        for token in [ctx["leader_token"], ctx["member_token"], ctx["guest2_token"]]:
            ws = _ws_connect(session_id, token, timeout=SLOW_WS_TIMEOUT)
            _recv(ws)  # connected
            connections.append(ws)

        time.sleep(wait)

        ok = True
        for i, ws in enumerate(connections):
            ws.settimeout(SLOW_WS_TIMEOUT)
            msg = _recv(ws)
            client_ok = (
                msg.get("type") == "session_ended"
                and msg.get("data", {}).get("reason") == "host_timeout"
            )
            ok &= _log(client_ok, f"T5-3: 客户端 {i + 1} 收到 session_ended", msg)
        return ok
    except Exception as e:
        return _log(False, "T5-3: 异常", str(e))
    finally:
        for ws in connections:
            try:
                ws.close()
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════════════════
#  main
# ═══════════════════════════════════════════════════════════════════════


def run_all(include_slow: bool = False) -> bool:
    print("=== 开始 WS 主机识别 + 心跳超时 + 广播 测试 ===\n")
    ctx: Dict[str, Any] = {}

    if not setup(ctx):
        print("setup 失败，测试中止 ❌")
        return False

    print("\n─── 快速用例：T3 主机识别 ───")
    fast_results = [
        t3_1_host_token_connects(ctx),
        t3_2_member_token_no_timeout(ctx),
        t3_3_no_token_connects(ctx),
        t3_4_invalid_token_connects(ctx),
    ]

    print("\n─── 快速用例：T4-5/6 补 ping 行为 ───")
    fast_results += [
        t4_5_rapid_ping_no_crash(ctx),
        t4_6_host_reconnect_session_continues(ctx),
    ]

    slow_results: List[bool] = []
    if include_slow:
        print("\n─── 慢速用例：T4 心跳超时 ───")
        slow_results += [
            t4_1_host_timeout_ends_session(ctx),
            t4_2_host_ping_resets_timer(ctx),
            t4_3_member_no_timeout(ctx),
            t4_4_host_ping_at_old_boundary(ctx),
        ]
        print("\n─── 慢速用例：T5 session_ended 广播 ───")
        slow_results += [
            t5_1_timeout_broadcast_to_all(ctx),
            t5_2_timeout_only_host_online(ctx),
            t5_3_timeout_three_clients(ctx),
        ]
    else:
        print("\n（慢速用例 T4/T5 已跳过，使用 --include-slow 运行）")

    all_results = fast_results + slow_results
    passed = sum(all_results)
    total = len(all_results)
    print(f"\n=== WS 测试结果: {passed}/{total} 通过 {'✅' if passed == total else '❌'} ===")
    return all(all_results)


if __name__ == "__main__":
    include_slow = "--include-slow" in sys.argv
    sys.exit(0 if run_all(include_slow=include_slow) else 1)
