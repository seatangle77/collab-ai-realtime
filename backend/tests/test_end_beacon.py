"""
end-beacon 端点集成测试

POST /api/sessions/{session_id}/end-beacon
  body: text/plain，内容为 JWT access_token

测试用例：
  T2-1: 有效 token + ongoing 会话 → 200，session status → ended
  T2-2: 有效 token + 已结束会话 → 200（幂等）
  T2-3: 非法 token（随机字符串）→ 401
  T2-4: 空 body → 401
  T2-5: 不存在的 session_id → 404
  T2-6: 其他用户的有效 token → 200（端点只验证 token 合法，不校验归属）

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
    email = f"beacon_{suffix}_{uuid.uuid4().hex[:6]}@example.com"
    r = requests.post(f"{BASE_URL}/api/auth/register", json={
        "name": name,
        "email": email,
        "password": "1234",
        "device_token": f"dev-beacon-{suffix}-{uuid.uuid4().hex[:8]}",
    })
    r.raise_for_status()
    user_id = r.json()["id"]
    r2 = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": "1234"})
    r2.raise_for_status()
    return r2.json()["access_token"], user_id


def _beacon(session_id: str, token_body: str) -> requests.Response:
    """模拟 navigator.sendBeacon：POST text/plain body = token"""
    return requests.post(
        f"{BASE_URL}/api/sessions/{session_id}/end-beacon",
        data=token_body,
        headers={"Content-Type": "text/plain"},
    )


def _get_session_status(session_id: str, token: str) -> str | None:
    """通过列举群组会话获取 status（含 ended）"""
    # 直接用 admin 或绕过：这里改用 transcripts 端点间接验证
    # 实际上 sessions 没有单独 GET，用 include_ended 列表查
    return None  # 由各用例自行验证


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


def _create_ongoing_session(
    leader_token: str, group_id: str, title: str
) -> str:
    """创建并 start 一个会话，返回 session_id"""
    _end_any_ongoing(leader_token, group_id)
    r = requests.post(
        f"{BASE_URL}/api/groups/{group_id}/sessions",
        json={"session_title": title},
        headers=_auth(leader_token),
    )
    r.raise_for_status()
    session_id = r.json()["id"]

    r2 = requests.post(
        f"{BASE_URL}/api/sessions/{session_id}/start",
        headers=_auth(leader_token),
    )
    r2.raise_for_status()
    return session_id


def _verify_ended(session_id: str, leader_token: str, group_id: str) -> bool:
    """从 include_ended=true 列表中验证会话状态为 ended"""
    r = requests.get(
        f"{BASE_URL}/api/groups/{group_id}/sessions",
        params={"include_ended": "true"},
        headers=_auth(leader_token),
    )
    if r.status_code != 200:
        return False
    sessions = r.json()
    target = next((s for s in sessions if s["id"] == session_id), None)
    return target is not None and target.get("status") == "ended"


# ─────────────────────── setup ───────────────────────────────────────────────


def setup(ctx: Dict[str, Any]) -> bool:
    ctx["leader_token"], ctx["leader_user_id"] = register_and_login(
        f"Beacon Leader {RUN_ID}", "leader"
    )
    ctx["other_token"], ctx["other_user_id"] = register_and_login(
        f"Beacon Other {RUN_ID}", "other"
    )

    r = requests.post(
        f"{BASE_URL}/api/groups",
        json={"name": f"Beacon Test Group {RUN_ID}"},
        headers=_auth(ctx["leader_token"]),
    )
    if r.status_code != 201:
        return _log(False, "setup: 创建 group 失败", {"status": r.status_code, "body": r.text})
    ctx["group_id"] = r.json()["group"]["id"]

    # other 加入同一 group（为 T2-6 准备有效 token 且是群成员）
    r = requests.post(
        f"{BASE_URL}/api/groups/{ctx['group_id']}/join",
        headers=_auth(ctx["other_token"]),
    )
    if r.status_code != 200:
        return _log(False, "setup: other 加入 group 失败", {"status": r.status_code, "body": r.text})

    return _log(True, "setup: 用户注册 + group 创建 成功")


# ─────────────────────── T2-1 ────────────────────────────────────────────────


def t2_1_valid_token_ongoing(ctx: Dict[str, Any]) -> bool:
    """有效 token + ongoing 会话 → 200，status → ended"""
    session_id = _create_ongoing_session(
        ctx["leader_token"], ctx["group_id"], f"T2-1 Session {RUN_ID}"
    )
    r = _beacon(session_id, ctx["leader_token"])
    if r.status_code != 200:
        return _log(False, "T2-1: beacon 请求失败", {"status": r.status_code, "body": r.text})

    ended = _verify_ended(session_id, ctx["leader_token"], ctx["group_id"])
    return _log(ended, "T2-1: 有效 token + ongoing → 200，status 变为 ended",
                {"session_id": session_id})


# ─────────────────────── T2-2 ────────────────────────────────────────────────


def t2_2_valid_token_already_ended(ctx: Dict[str, Any]) -> bool:
    """有效 token + 已结束会话 → 200（幂等）"""
    session_id = _create_ongoing_session(
        ctx["leader_token"], ctx["group_id"], f"T2-2 Session {RUN_ID}"
    )
    # 先正常结束
    requests.post(
        f"{BASE_URL}/api/sessions/{session_id}/end",
        headers=_auth(ctx["leader_token"]),
    ).raise_for_status()

    # 再发 beacon
    r = _beacon(session_id, ctx["leader_token"])
    ok = r.status_code == 200
    return _log(ok, "T2-2: 已结束会话再发 beacon → 200（幂等）",
                {"status": r.status_code, "body": r.text})


# ─────────────────────── T2-3 ────────────────────────────────────────────────


def t2_3_invalid_token(ctx: Dict[str, Any]) -> bool:
    """非法 token → 401"""
    session_id = _create_ongoing_session(
        ctx["leader_token"], ctx["group_id"], f"T2-3 Session {RUN_ID}"
    )
    r = _beacon(session_id, "this.is.not.a.jwt")
    ok = r.status_code == 401
    return _log(ok, "T2-3: 非法 token → 401", {"status": r.status_code, "body": r.text})


# ─────────────────────── T2-4 ────────────────────────────────────────────────


def t2_4_empty_body(ctx: Dict[str, Any]) -> bool:
    """空 body → 401"""
    session_id = _create_ongoing_session(
        ctx["leader_token"], ctx["group_id"], f"T2-4 Session {RUN_ID}"
    )
    r = _beacon(session_id, "")
    ok = r.status_code == 401
    return _log(ok, "T2-4: 空 body → 401", {"status": r.status_code, "body": r.text})


# ─────────────────────── T2-5 ────────────────────────────────────────────────


def t2_5_nonexistent_session(ctx: Dict[str, Any]) -> bool:
    """不存在的 session_id → 404"""
    fake_id = str(uuid.uuid4())
    r = _beacon(fake_id, ctx["leader_token"])
    ok = r.status_code == 404
    return _log(ok, "T2-5: 不存在的 session_id → 404", {"status": r.status_code, "body": r.text})


# ─────────────────────── T2-6 ────────────────────────────────────────────────


def t2_6_other_users_valid_token(ctx: Dict[str, Any]) -> bool:
    """其他用户（合法 token，非 created_by）发 beacon → 200（端点不校验归属）"""
    session_id = _create_ongoing_session(
        ctx["leader_token"], ctx["group_id"], f"T2-6 Session {RUN_ID}"
    )
    r = _beacon(session_id, ctx["other_token"])
    ok = r.status_code == 200
    return _log(ok, "T2-6: 其他用户有效 token → 200（不校验归属）",
                {"status": r.status_code, "body": r.text})


# ─────────────────────── main ────────────────────────────────────────────────


def run_all() -> bool:
    print("=== 开始 end-beacon 端点测试 ===\n")
    ctx: Dict[str, Any] = {}

    if not setup(ctx):
        print("setup 失败，测试中止 ❌")
        return False

    results = [
        t2_1_valid_token_ongoing(ctx),
        t2_2_valid_token_already_ended(ctx),
        t2_3_invalid_token(ctx),
        t2_4_empty_body(ctx),
        t2_5_nonexistent_session(ctx),
        t2_6_other_users_valid_token(ctx),
    ]

    passed = sum(results)
    total = len(results)
    print(f"\n=== end-beacon 测试结果: {passed}/{total} 通过 {'✅' if passed == total else '❌'} ===")
    return all(results)


if __name__ == "__main__":
    import sys
    sys.exit(0 if run_all() else 1)
