"""
created_by 字段集成测试

测试用例：
  T1-1: 创建会话 → 响应中 created_by == 当前登录用户 id
  T1-2: 列出会话 → 每条都包含 created_by 字段，新建那条值正确
  T1-3: member 创建会话 → created_by == member_user_id（非 leader）
  T1-4: 创建会话后调用 start → 响应中 created_by 仍正确保留
  T1-5: 结束会话（end）→ 响应中 created_by 仍正确保留

运行前提：后端已启动（uvicorn backend.app.main:app --reload --port 8000）
依赖：pip install requests
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, Tuple

import requests

BASE_URL = "http://127.0.0.1:8000"
RUN_ID = uuid.uuid4().hex[:6]


def _log(ok: bool, msg: str, extra: Any = None) -> bool:
    print(f"{'✅' if ok else '❌'} {msg}")
    if not ok and extra is not None:
        print("   详情:", extra)
    return ok


def _auth(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def register_and_login(name: str, suffix: str) -> Tuple[str, str]:
    """注册并登录，返回 (access_token, user_id)。"""
    email = f"cb_{suffix}_{uuid.uuid4().hex[:6]}@example.com"
    r = requests.post(f"{BASE_URL}/api/auth/register", json={
        "name": name,
        "email": email,
        "password": "1234",
        "device_token": f"dev-cb-{suffix}-{uuid.uuid4().hex[:8]}",
    })
    r.raise_for_status()
    user_id = r.json()["id"]
    r2 = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": "1234"})
    r2.raise_for_status()
    return r2.json()["access_token"], user_id


# ─────────────────────── setup ───────────────────────────────────────────────


def setup(ctx: Dict[str, Any]) -> bool:
    ctx["leader_token"], ctx["leader_user_id"] = register_and_login(f"Leader {RUN_ID}", "leader")
    ctx["member_token"], ctx["member_user_id"] = register_and_login(f"Member {RUN_ID}", "member")

    r = requests.post(f"{BASE_URL}/api/groups",
                      json={"name": f"CB Test Group {RUN_ID}"},
                      headers=_auth(ctx["leader_token"]))
    if r.status_code != 201:
        return _log(False, "setup: 创建 group 失败", {"status": r.status_code, "body": r.text})
    ctx["group_id"] = r.json()["group"]["id"]

    r = requests.post(f"{BASE_URL}/api/groups/{ctx['group_id']}/join",
                      headers=_auth(ctx["member_token"]))
    if r.status_code != 200:
        return _log(False, "setup: member 加入 group 失败", {"status": r.status_code, "body": r.text})

    return _log(True, "setup: group 创建 + member 加入 成功")


# ─────────────────────── T1-1 ────────────────────────────────────────────────


def t1_1_create_session_has_created_by(ctx: Dict[str, Any]) -> bool:
    """创建会话后响应中 created_by == leader_user_id"""
    r = requests.post(
        f"{BASE_URL}/api/groups/{ctx['group_id']}/sessions",
        json={"session_title": f"T1-1 Session {RUN_ID}"},
        headers=_auth(ctx["leader_token"]),
    )
    if r.status_code != 201:
        return _log(False, "T1-1: 创建会话失败", {"status": r.status_code, "body": r.text})
    data = r.json()
    ctx["session_id_leader"] = data["id"]

    ok = "created_by" in data
    ok &= data.get("created_by") == ctx["leader_user_id"]
    return _log(ok, "T1-1: 创建会话响应包含正确的 created_by",
                {"created_by": data.get("created_by"), "expected": ctx["leader_user_id"]})


# ─────────────────────── T1-2 ────────────────────────────────────────────────


def t1_2_list_sessions_include_created_by(ctx: Dict[str, Any]) -> bool:
    """列出会话时每条都包含 created_by，新建那条值正确"""
    r = requests.get(
        f"{BASE_URL}/api/groups/{ctx['group_id']}/sessions",
        headers=_auth(ctx["leader_token"]),
    )
    if r.status_code != 200:
        return _log(False, "T1-2: 列出会话失败", {"status": r.status_code, "body": r.text})
    sessions = r.json()

    ok = True
    # 每条都有 created_by 键
    for s in sessions:
        if "created_by" not in s:
            ok = False
            _log(False, f"T1-2: session {s.get('id')} 缺少 created_by 字段")

    # 新建那条值正确
    target = next((s for s in sessions if s["id"] == ctx.get("session_id_leader")), None)
    if target is None:
        return _log(False, "T1-2: 列表中未找到刚建的会话")
    ok &= target.get("created_by") == ctx["leader_user_id"]

    return _log(ok, "T1-2: 列表中每条都含 created_by，且值正确",
                {"found_created_by": target.get("created_by")})


# ─────────────────────── T1-3 ────────────────────────────────────────────────


def t1_3_member_creates_session_own_created_by(ctx: Dict[str, Any]) -> bool:
    """member 创建会话 → created_by == member_user_id（而非 leader）"""
    r = requests.post(
        f"{BASE_URL}/api/groups/{ctx['group_id']}/sessions",
        json={"session_title": f"T1-3 Member Session {RUN_ID}"},
        headers=_auth(ctx["member_token"]),
    )
    if r.status_code != 201:
        return _log(False, "T1-3: member 创建会话失败", {"status": r.status_code, "body": r.text})
    data = r.json()
    ctx["session_id_member"] = data["id"]

    ok = data.get("created_by") == ctx["member_user_id"]
    ok &= data.get("created_by") != ctx["leader_user_id"]
    return _log(ok, "T1-3: member 创建的会话 created_by == member_user_id",
                {"created_by": data.get("created_by"), "member_id": ctx["member_user_id"]})


# ─────────────────────── T1-4 ────────────────────────────────────────────────


def t1_4_start_preserves_created_by(ctx: Dict[str, Any]) -> bool:
    """start 会话后响应中 created_by 仍然正确"""
    r = requests.post(
        f"{BASE_URL}/api/sessions/{ctx['session_id_leader']}/start",
        headers=_auth(ctx["leader_token"]),
    )
    if r.status_code != 200:
        return _log(False, "T1-4: start 会话失败", {"status": r.status_code, "body": r.text})
    data = r.json()
    ok = data.get("created_by") == ctx["leader_user_id"]
    ok &= data.get("status") == "ongoing"
    return _log(ok, "T1-4: start 后 created_by 保留正确",
                {"created_by": data.get("created_by"), "status": data.get("status")})


# ─────────────────────── T1-5 ────────────────────────────────────────────────


def t1_5_end_preserves_created_by(ctx: Dict[str, Any]) -> bool:
    """end 会话后响应中 created_by 仍然正确"""
    r = requests.post(
        f"{BASE_URL}/api/sessions/{ctx['session_id_leader']}/end",
        headers=_auth(ctx["leader_token"]),
    )
    if r.status_code != 200:
        return _log(False, "T1-5: end 会话失败", {"status": r.status_code, "body": r.text})
    data = r.json()
    ok = data.get("created_by") == ctx["leader_user_id"]
    ok &= data.get("status") == "ended"
    return _log(ok, "T1-5: end 后 created_by 保留正确",
                {"created_by": data.get("created_by"), "status": data.get("status")})


# ─────────────────────── main ────────────────────────────────────────────────


def run_all() -> bool:
    print("=== 开始 created_by 字段测试 ===\n")
    ctx: Dict[str, Any] = {}

    if not setup(ctx):
        print("setup 失败，测试中止 ❌")
        return False

    results = [
        t1_1_create_session_has_created_by(ctx),
        t1_2_list_sessions_include_created_by(ctx),
        t1_3_member_creates_session_own_created_by(ctx),
        t1_4_start_preserves_created_by(ctx),
        t1_5_end_preserves_created_by(ctx),
    ]

    passed = sum(results)
    total = len(results)
    print(f"\n=== created_by 测试结果: {passed}/{total} 通过 {'✅' if passed == total else '❌'} ===")
    return all(results)


if __name__ == "__main__":
    import sys
    sys.exit(0 if run_all() else 1)
