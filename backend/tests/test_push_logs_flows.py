from __future__ import annotations

import uuid
from typing import Any, Dict, Tuple

import requests

BASE_URL = "http://127.0.0.1:8000"
RUN_ID = uuid.uuid4().hex[:6]
ADMIN_HEADERS = {"X-Admin-Token": "TestAdminKey123"}


def _log(ok: bool, message: str, extra: Any = None) -> bool:
    print(f"{'✅' if ok else '❌'} {message}")
    if not ok and extra is not None:
        print("   详情:", extra)
    return ok


def _register_and_login(label: str) -> Tuple[Dict[str, Any], str]:
    email = f"pl_{label}_{uuid.uuid4().hex[:6]}@example.com"
    r = requests.post(f"{BASE_URL}/api/auth/register", json={
        "name": f"PL {label} {RUN_ID}",
        "email": email,
        "password": "1234",
        "device_token": f"dev-{uuid.uuid4().hex[:8]}",
    })
    r.raise_for_status()
    user = r.json()
    token = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": email, "password": "1234"}).json()["access_token"]
    return user, token


def _auth(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _setup_session(label: str) -> Tuple[Dict, str, str, str]:
    """注册 leader → 建群 → 建会话 → start"""
    leader, token = _register_and_login(f"Leader{label}")

    r = requests.post(f"{BASE_URL}/api/groups", headers=_auth(token),
                      json={"name": f"PL Group {label} {RUN_ID}"})
    r.raise_for_status()
    group_id = r.json()["group"]["id"]

    r2 = requests.post(f"{BASE_URL}/api/groups/{group_id}/sessions",
                       headers=_auth(token), json={"session_title": f"PL Session {label}"})
    r2.raise_for_status()
    session_id = r2.json()["id"]

    requests.post(f"{BASE_URL}/api/sessions/{session_id}/start",
                  headers=_auth(token)).raise_for_status()

    return leader, token, group_id, session_id


def _create_log(session_id: str, target_user_id: str, **kwargs) -> Dict[str, Any]:
    r = requests.post(f"{BASE_URL}/api/admin/push-logs/",
                      headers=ADMIN_HEADERS,
                      json={"session_id": session_id,
                            "target_user_id": target_user_id,
                            "push_channel": "app",
                            **kwargs})
    r.raise_for_status()
    return r.json()


# ─────────────────────────────────────────────────
# 1. 未登录访问 → 401
# ─────────────────────────────────────────────────

def scenario_unauth() -> bool:
    r = requests.get(f"{BASE_URL}/api/sessions/fake/push-logs")
    return _log(r.status_code == 401, "GET /push-logs 未登录返回 401", {"status": r.status_code})


# ─────────────────────────────────────────────────
# 2. 会话不存在 → 404
# ─────────────────────────────────────────────────

def scenario_session_not_found() -> bool:
    _, token = _register_and_login("SessNF")
    r = requests.get(f"{BASE_URL}/api/sessions/non-exist-xyz/push-logs",
                     headers=_auth(token))
    return _log(r.status_code == 404, "GET /push-logs 会话不存在返回 404", {"status": r.status_code})


# ─────────────────────────────────────────────────
# 3. 非群组成员访问 → 403
# ─────────────────────────────────────────────────

def scenario_not_member() -> bool:
    _, _, _, session_id = _setup_session("NotMember")
    _, outsider_token = _register_and_login("Outsider")
    r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/push-logs",
                     headers=_auth(outsider_token))
    return _log(r.status_code == 403, "GET /push-logs 非群组成员返回 403", {"status": r.status_code})


# ─────────────────────────────────────────────────
# 4. 无记录时返回空列表
# ─────────────────────────────────────────────────

def scenario_empty() -> bool:
    leader, token, _, session_id = _setup_session("Empty")
    r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/push-logs",
                     headers=_auth(token))
    if r.status_code != 200:
        return _log(False, "GET /push-logs 无记录应返回 200", r.text)
    data = r.json()
    ok = data == []
    return _log(ok, "GET /push-logs 无记录返回空列表", data)


# ─────────────────────────────────────────────────
# 5. 有记录时返回正确字段
# ─────────────────────────────────────────────────

def scenario_fields_complete() -> bool:
    leader, token, _, session_id = _setup_session("Fields")
    _create_log(session_id, leader["id"],
                push_content="你好，请更积极参与",
                push_channel="app",
                delivery_status="delivered",
                jpush_message_id="jmsg-001")
    r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/push-logs",
                     headers=_auth(token))
    if r.status_code != 200:
        return _log(False, "GET /push-logs 字段完整性失败", r.text)
    data = r.json()
    if not data:
        return _log(False, "GET /push-logs 期望有记录但返回空", data)
    item = data[0]
    required = ["id", "session_id", "push_channel", "delivery_status", "triggered_at"]
    ok = all(f in item for f in required)
    return _log(ok, "GET /push-logs 字段完整性验证", item)


# ─────────────────────────────────────────────────
# 6. 只返回当前用户的记录（隔离性）
# ─────────────────────────────────────────────────

def scenario_user_isolation() -> bool:
    leader, leader_token, group_id, session_id = _setup_session("Isolation")
    member, member_token = _register_and_login("MemberIso")
    requests.post(f"{BASE_URL}/api/groups/{group_id}/join",
                  headers=_auth(member_token)).raise_for_status()

    # 给 leader 创建 2 条，给 member 创建 1 条
    _create_log(session_id, leader["id"], push_channel="app")
    _create_log(session_id, leader["id"], push_channel="web")
    _create_log(session_id, member["id"], push_channel="glasses")

    r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/push-logs",
                     headers=_auth(leader_token))
    r.raise_for_status()
    data = r.json()
    # leader 只能看到自己的 2 条
    ok = len(data) == 2
    return _log(ok, "GET /push-logs 只返回当前用户记录（隔离性）", {"count": len(data)})


# ─────────────────────────────────────────────────
# 7. 按 push_channel 过滤
# ─────────────────────────────────────────────────

def scenario_filter_channel() -> bool:
    leader, token, _, session_id = _setup_session("FilterChan")
    _create_log(session_id, leader["id"], push_channel="app")
    _create_log(session_id, leader["id"], push_channel="web")
    _create_log(session_id, leader["id"], push_channel="glasses")

    r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/push-logs",
                     headers=_auth(token), params={"push_channel": "web"})
    r.raise_for_status()
    data = r.json()
    ok = len(data) == 1 and data[0]["push_channel"] == "web"
    return _log(ok, "GET /push-logs 按 push_channel=web 过滤", {"count": len(data)})


# ─────────────────────────────────────────────────
# 8. 按 delivery_status 过滤
# ─────────────────────────────────────────────────

def scenario_filter_delivery_status() -> bool:
    leader, token, _, session_id = _setup_session("FilterStatus")
    _create_log(session_id, leader["id"], delivery_status="pending")
    _create_log(session_id, leader["id"], delivery_status="delivered")
    _create_log(session_id, leader["id"], delivery_status="failed")

    r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/push-logs",
                     headers=_auth(token), params={"delivery_status": "delivered"})
    r.raise_for_status()
    data = r.json()
    ok = len(data) == 1 and data[0]["delivery_status"] == "delivered"
    return _log(ok, "GET /push-logs 按 delivery_status=delivered 过滤", {"count": len(data)})


# ─────────────────────────────────────────────────
# 9. 非法 push_channel → 400
# ─────────────────────────────────────────────────

def scenario_invalid_channel() -> bool:
    leader, token, _, session_id = _setup_session("InvalidChan")
    r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/push-logs",
                     headers=_auth(token), params={"push_channel": "sms"})
    return _log(r.status_code == 400, "GET /push-logs 非法 push_channel 返回 400", {"status": r.status_code})


# ─────────────────────────────────────────────────
# 10. 非法 delivery_status → 400
# ─────────────────────────────────────────────────

def scenario_invalid_delivery_status() -> bool:
    leader, token, _, session_id = _setup_session("InvalidStatus")
    r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/push-logs",
                     headers=_auth(token), params={"delivery_status": "unknown"})
    return _log(r.status_code == 400, "GET /push-logs 非法 delivery_status 返回 400", {"status": r.status_code})


# ─────────────────────────────────────────────────
# 11. 结果按 triggered_at 降序排列
# ─────────────────────────────────────────────────

def scenario_order_desc() -> bool:
    leader, token, _, session_id = _setup_session("Order")
    _create_log(session_id, leader["id"], push_channel="app")
    _create_log(session_id, leader["id"], push_channel="app")
    _create_log(session_id, leader["id"], push_channel="app")

    r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/push-logs",
                     headers=_auth(token))
    r.raise_for_status()
    data = r.json()
    if len(data) < 2:
        return _log(False, "GET /push-logs 排序验证：记录数不足", data)
    ok = data[0]["triggered_at"] >= data[-1]["triggered_at"]
    return _log(ok, "GET /push-logs 结果按 triggered_at 降序", {
        "first": data[0]["triggered_at"], "last": data[-1]["triggered_at"]
    })


def run_all() -> bool:
    print("=== 开始 Push Logs 用户端接口测试 ===")
    ok = True
    ok &= scenario_unauth()
    ok &= scenario_session_not_found()
    ok &= scenario_not_member()
    ok &= scenario_empty()
    ok &= scenario_fields_complete()
    ok &= scenario_user_isolation()
    ok &= scenario_filter_channel()
    ok &= scenario_filter_delivery_status()
    ok &= scenario_invalid_channel()
    ok &= scenario_invalid_delivery_status()
    ok &= scenario_order_desc()
    print("\n=== Push Logs 用户端测试结果: {} ===".format("全部通过 ✅" if ok else "有失败 ❌"))
    return ok


if __name__ == "__main__":
    import sys
    sys.exit(0 if run_all() else 1)
