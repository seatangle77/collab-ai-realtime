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
    email = f"eng_{label}_{uuid.uuid4().hex[:6]}@example.com"
    r = requests.post(f"{BASE_URL}/api/auth/register", json={
        "name": f"Eng {label} {RUN_ID}",
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
    """注册 leader → 建群 → 建会话 → start，返回 (leader_user, leader_token, group_id, session_id)"""
    leader, token = _register_and_login(f"Leader{label}")

    # 建群
    r = requests.post(f"{BASE_URL}/api/groups", headers=_auth(token),
                      json={"name": f"Eng Group {label} {RUN_ID}"})
    r.raise_for_status()
    group_id = r.json()["group"]["id"]

    # 建会话
    r2 = requests.post(f"{BASE_URL}/api/groups/{group_id}/sessions",
                       headers=_auth(token), json={"session_title": f"Eng Session {label}"})
    r2.raise_for_status()
    session_id = r2.json()["id"]

    # start
    requests.post(f"{BASE_URL}/api/sessions/{session_id}/start",
                  headers=_auth(token)).raise_for_status()

    return leader, token, group_id, session_id


def _create_metric(session_id: str, user_id: str, **kwargs) -> Dict[str, Any]:
    r = requests.post(f"{BASE_URL}/api/admin/engagement-metrics/",
                      headers=ADMIN_HEADERS,
                      json={"session_id": session_id, "user_id": user_id, **kwargs})
    r.raise_for_status()
    return r.json()


# ─────────────────────────────────────────
# A. 用户端 GET /sessions/{id}/engagement
# ─────────────────────────────────────────

def scenario_engagement_unauth() -> bool:
    r = requests.get(f"{BASE_URL}/api/sessions/fake-session/engagement")
    return _log(r.status_code == 401, "GET /engagement 未登录返回 401", {"status": r.status_code})


def scenario_engagement_not_member() -> bool:
    leader, leader_token, _, session_id = _setup_session("NotMember")
    outsider, outsider_token = _register_and_login("Outsider")
    r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/engagement",
                     headers=_auth(outsider_token))
    return _log(r.status_code == 403, "GET /engagement 非群组成员返回 403", {"status": r.status_code})


def scenario_engagement_session_not_found() -> bool:
    _, token = _register_and_login("SessNotFound")
    r = requests.get(f"{BASE_URL}/api/sessions/non-existent-session-xyz/engagement",
                     headers=_auth(token))
    return _log(r.status_code == 404, "GET /engagement session 不存在返回 404", {"status": r.status_code})


def scenario_engagement_empty() -> bool:
    leader, token, _, session_id = _setup_session("Empty")
    r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/engagement",
                     headers=_auth(token))
    if r.status_code != 200:
        return _log(False, "GET /engagement 无记录失败（期望 200）", r.text)
    data = r.json()
    ok = data.get("members") == [] and data.get("calculated_at") is None
    return _log(ok, "GET /engagement 无指标记录返回空快照场景", data)


def scenario_engagement_single_member() -> bool:
    leader, token, _, session_id = _setup_session("Single")
    _create_metric(session_id, leader["id"],
                   speaking_ratio=0.4, speaking_frequency=2.0,
                   silence_duration_s=30, mattr_score=0.7,
                   avg_sentence_length=10.0, response_rate=0.8,
                   new_idea_rate=0.3, topic_cosine_similarity=0.6,
                   semantic_cohesion=0.65, semantic_uniqueness=0.5)

    r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/engagement",
                     headers=_auth(token))
    if r.status_code != 200:
        return _log(False, "GET /engagement 单成员失败", r.text)
    data = r.json()
    ok = len(data.get("members", [])) == 1
    ok &= data.get("calculated_at") is not None
    member = data["members"][0]
    required = ["user_id", "user_name", "speaking_ratio", "speaking_frequency",
                "silence_duration_s", "mattr_score", "avg_sentence_length",
                "response_rate", "new_idea_rate", "topic_cosine_similarity",
                "semantic_cohesion", "semantic_uniqueness"]
    ok &= all(f in member for f in required)
    return _log(ok, "GET /engagement 单成员字段完整性场景", data)


def scenario_engagement_dedup_latest() -> bool:
    """同一用户有 2 条记录，只返回最新一条。"""
    leader, token, _, session_id = _setup_session("Dedup")
    _create_metric(session_id, leader["id"], speaking_ratio=0.2)
    _create_metric(session_id, leader["id"], speaking_ratio=0.9)

    r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/engagement",
                     headers=_auth(token))
    r.raise_for_status()
    data = r.json()
    ok = len(data.get("members", [])) == 1
    # 最新一条的 speaking_ratio 应该是 0.9
    ok &= data["members"][0].get("speaking_ratio") == 0.9
    return _log(ok, "GET /engagement 同用户多条记录只返回最新场景", data)


def scenario_engagement_multi_member() -> bool:
    """2 个成员各有记录，返回 2 条。"""
    leader, leader_token, group_id, session_id = _setup_session("Multi")
    member, member_token = _register_and_login("Member2")
    # member 加入群组
    requests.post(f"{BASE_URL}/api/groups/{group_id}/join",
                  headers=_auth(member_token)).raise_for_status()

    _create_metric(session_id, leader["id"], speaking_ratio=0.6)
    _create_metric(session_id, member["id"], speaking_ratio=0.4)

    r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/engagement",
                     headers=_auth(leader_token))
    r.raise_for_status()
    data = r.json()
    ok = len(data.get("members", [])) == 2
    return _log(ok, "GET /engagement 多成员各返回最新记录场景", data)


def scenario_engagement_snapshot_structure() -> bool:
    """验证 EngagementSnapshotOut 顶层结构字段。"""
    leader, token, _, session_id = _setup_session("Structure")
    _create_metric(session_id, leader["id"])
    r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/engagement",
                     headers=_auth(token))
    r.raise_for_status()
    data = r.json()
    ok = "calculated_at" in data and "members" in data
    ok &= isinstance(data["members"], list)
    return _log(ok, "GET /engagement EngagementSnapshotOut 结构验证场景", data)


def run_all() -> bool:
    print("=== 开始 Engagement 用户端接口测试 ===")
    ok = True
    ok &= scenario_engagement_unauth()
    ok &= scenario_engagement_not_member()
    ok &= scenario_engagement_session_not_found()
    ok &= scenario_engagement_empty()
    ok &= scenario_engagement_single_member()
    ok &= scenario_engagement_dedup_latest()
    ok &= scenario_engagement_multi_member()
    ok &= scenario_engagement_snapshot_structure()
    print("\n=== Engagement 用户端测试结果: {} ===".format("全部通过 ✅" if ok else "有失败 ❌"))
    return ok


if __name__ == "__main__":
    import sys
    sys.exit(0 if run_all() else 1)
