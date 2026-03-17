from __future__ import annotations

import uuid
from typing import Any, Dict, Tuple

import requests

BASE_URL = "http://127.0.0.1:8000"
RUN_ID = uuid.uuid4().hex[:6]


def _log(ok: bool, message: str, extra: Any | None = None) -> bool:
    prefix = "✅" if ok else "❌"
    print(f"{prefix} {message}")
    if not ok and extra is not None:
        print("   详情:", extra)
    return ok


def register_and_login(name: str, email_suffix: str) -> Tuple[str, str]:
    """注册一个用户并登录，返回 (access_token, user_id)。"""
    email = f"test_{email_suffix}_{uuid.uuid4().hex[:6]}@example.com"
    password = "1234"

    r = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={
            "name": name,
            "email": email,
            "password": password,
            "device_token": f"device-sessions-{email_suffix}-{uuid.uuid4().hex[:8]}",
        },
    )
    r.raise_for_status()
    user = r.json()
    user_id = user["id"]

    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
    )
    r.raise_for_status()
    data = r.json()
    token = data["access_token"]
    return token, user_id


# ---------- 场景：准备 group 和成员 ----------


def setup_group_with_members(ctx: Dict[str, Any]) -> bool:
    # 注册 & 登录 3 个用户
    ctx["leader_token"], ctx["leader_user_id"] = register_and_login(f"Alice Chen {RUN_ID}", "leader")
    ctx["member_token"], ctx["member_user_id"] = register_and_login(f"Bob Wang {RUN_ID}", "member")
    ctx["outsider_token"], ctx["outsider_user_id"] = register_and_login(f"Carol Liu {RUN_ID}", "outsider")

    # leader 创建 group
    headers_leader = {"Authorization": f"Bearer {ctx['leader_token']}"}
    r = requests.post(
        f"{BASE_URL}/api/groups",
        json={"name": f"Session Test Group {RUN_ID}"},
        headers=headers_leader,
    )
    if r.status_code != 201:
        return _log(False, "准备阶段：创建群组失败", {"status_code": r.status_code, "text": r.text})
    data = r.json()
    ctx["group_id"] = data["group"]["id"]

    # member 加入 group
    headers_member = {"Authorization": f"Bearer {ctx['member_token']}"}
    r = requests.post(f"{BASE_URL}/api/groups/{ctx['group_id']}/join", headers=headers_member)
    if r.status_code != 200:
        return _log(False, "准备阶段：成员加入群组失败", {"status_code": r.status_code, "body": r.text})

    return _log(True, "准备阶段：成功创建 group 并加入一个成员", ctx)


# ---------- 创建会话相关 ----------


def scenario_create_sessions(ctx: Dict[str, Any]) -> bool:
    ok = True

    # leader 创建第一个会话
    headers_leader = {"Authorization": f"Bearer {ctx['leader_token']}"}
    r = requests.post(
        f"{BASE_URL}/api/groups/{ctx['group_id']}/sessions",
        json={"session_title": "First Session"},
        headers=headers_leader,
    )
    if r.status_code != 201:
        return _log(False, "leader 创建会话失败（期望 201）", {"status_code": r.status_code, "text": r.text})
    data = r.json()
    ctx["session_id_1"] = data["id"]
    ok &= _log(True, "leader 创建会话成功", data)

    # member 创建第二个会话
    headers_member = {"Authorization": f"Bearer {ctx['member_token']}"}
    r = requests.post(
        f"{BASE_URL}/api/groups/{ctx['group_id']}/sessions",
        json={"session_title": "Second Session"},
        headers=headers_member,
    )
    if r.status_code != 201:
        return _log(False, "member 创建会话失败（期望 201）", {"status_code": r.status_code, "text": r.text})
    data = r.json()
    ctx["session_id_2"] = data["id"]
    ok &= _log(True, "member 创建会话成功", data)

    # outsider 尝试创建会话应失败
    headers_outsider = {"Authorization": f"Bearer {ctx['outsider_token']}"}
    r = requests.post(
        f"{BASE_URL}/api/groups/{ctx['group_id']}/sessions",
        json={"session_title": "Should Fail Session"},
        headers=headers_outsider,
    )
    ok &= _log(r.status_code == 403, "outsider 创建会话被禁止场景", {"status_code": r.status_code, "body": r.text})
    return ok


# ---------- 会话列表相关 ----------


def scenario_list_sessions(ctx: Dict[str, Any]) -> bool:
    headers_leader = {"Authorization": f"Bearer {ctx['leader_token']}"}

    # 默认不带 include_ended
    r = requests.get(f"{BASE_URL}/api/groups/{ctx['group_id']}/sessions", headers=headers_leader)
    if r.status_code != 200:
        return _log(False, "leader 列出会话失败（期望 200）", {"status_code": r.status_code, "text": r.text})
    sessions = r.json()
    ids = {s["id"] for s in sessions}
    ok = ctx["session_id_1"] in ids and ctx["session_id_2"] in ids
    ok &= _log(ok, "默认列表包含两个会话场景", sessions)

    # outsider 列出会话应被禁止
    headers_outsider = {"Authorization": f"Bearer {ctx['outsider_token']}"}
    r = requests.get(f"{BASE_URL}/api/groups/{ctx['group_id']}/sessions", headers=headers_outsider)
    ok &= _log(r.status_code == 403, "outsider 查看会话列表被禁止场景", {"status_code": r.status_code, "body": r.text})
    return ok


# ---------- 更新会话标题相关 ----------


def scenario_update_session_titles(ctx: Dict[str, Any]) -> bool:
    ok = True

    # leader 更新自己的会话标题
    headers_leader = {"Authorization": f"Bearer {ctx['leader_token']}"}
    r = requests.patch(
        f"{BASE_URL}/api/sessions/{ctx['session_id_1']}",
        json={"session_title": "Session 1 Renamed"},
        headers=headers_leader,
    )
    if r.status_code != 200:
        return _log(False, "leader 更新会话标题失败", {"status_code": r.status_code, "text": r.text})
    data = r.json()
    ok &= _log(data["session_title"] == "Session 1 Renamed", "leader 更新会话标题场景", data)

    # member 更新自己创建的会话标题
    headers_member = {"Authorization": f"Bearer {ctx['member_token']}"}
    r = requests.patch(
        f"{BASE_URL}/api/sessions/{ctx['session_id_2']}",
        json={"session_title": "Session 2 Renamed"},
        headers=headers_member,
    )
    if r.status_code != 200:
        return _log(False, "member 更新会话标题失败", {"status_code": r.status_code, "text": r.text})
    data = r.json()
    ok &= _log(data["session_title"] == "Session 2 Renamed", "member 更新会话标题场景", data)

    # outsider 更新任意会话标题应失败
    headers_outsider = {"Authorization": f"Bearer {ctx['outsider_token']}"}
    r = requests.patch(
        f"{BASE_URL}/api/sessions/{ctx['session_id_1']}",
        json={"session_title": "Should Not Apply"},
        headers=headers_outsider,
    )
    ok &= _log(r.status_code == 403, "outsider 更新会话标题被禁止场景", {"status_code": r.status_code, "body": r.text})

    # 更新不存在的会话
    r = requests.patch(
        f"{BASE_URL}/api/sessions/nonexistent-session",
        json={"session_title": "whatever"},
        headers=headers_leader,
    )
    ok &= _log(r.status_code == 404, "更新不存在会话返回 404 场景", {"status_code": r.status_code, "body": r.text})

    return ok


# ---------- 发起会话相关 ----------


def scenario_start_session(ctx: Dict[str, Any]) -> bool:
    ok = True
    headers_leader = {"Authorization": f"Bearer {ctx['leader_token']}"}
    headers_member = {"Authorization": f"Bearer {ctx['member_token']}"}
    headers_outsider = {"Authorization": f"Bearer {ctx['outsider_token']}"}

    # 1. 未登录发起会话 → 401
    r = requests.post(f"{BASE_URL}/api/sessions/{ctx['session_id_1']}/start")
    ok &= _log(r.status_code == 401, "未登录发起会话返回 401 场景", {"status_code": r.status_code})

    # 2. outsider 发起会话 → 403
    r = requests.post(f"{BASE_URL}/api/sessions/{ctx['session_id_1']}/start", headers=headers_outsider)
    ok &= _log(r.status_code == 403, "outsider 发起会话返回 403 场景", {"status_code": r.status_code, "body": r.text})

    # 3. 发起不存在的会话 → 404
    r = requests.post(f"{BASE_URL}/api/sessions/nonexistent-session/start", headers=headers_leader)
    ok &= _log(r.status_code == 404, "发起不存在会话返回 404 场景", {"status_code": r.status_code, "body": r.text})

    # 4. 正常发起 session_id_1（not_started）→ 200，status=ongoing，started_at 非 null
    r = requests.post(f"{BASE_URL}/api/sessions/{ctx['session_id_1']}/start", headers=headers_leader)
    if r.status_code != 200:
        return _log(False, "正常发起会话失败（期望 200）", {"status_code": r.status_code, "text": r.text})
    data = r.json()
    ok &= _log(
        data["status"] == "ongoing" and data["started_at"] is not None,
        "正常发起会话场景：status=ongoing，started_at 非 null",
        data,
    )

    # 5. 再次 start 同一个 ongoing 会话 → 400（状态不是 not_started）
    r = requests.post(f"{BASE_URL}/api/sessions/{ctx['session_id_1']}/start", headers=headers_leader)
    ok &= _log(r.status_code == 400, "重复发起 ongoing 会话返回 400 场景", {"status_code": r.status_code, "body": r.text})

    # 6. 同群组已有 ongoing（session_id_1），新建 session_id_3 并尝试 start → 409
    r = requests.post(
        f"{BASE_URL}/api/groups/{ctx['group_id']}/sessions",
        json={"session_title": "Third Session"},
        headers=headers_member,
    )
    if r.status_code != 201:
        return _log(False, "创建第三个会话失败", {"status_code": r.status_code, "text": r.text})
    ctx["session_id_3"] = r.json()["id"]
    r = requests.post(f"{BASE_URL}/api/sessions/{ctx['session_id_3']}/start", headers=headers_member)
    ok &= _log(r.status_code == 409, "群组已有 ongoing 会话时 start 返回 409 场景", {"status_code": r.status_code, "body": r.text})

    # 7. start 后 list 默认列表中该会话可见（status != ended）
    r = requests.get(f"{BASE_URL}/api/groups/{ctx['group_id']}/sessions", headers=headers_leader)
    if r.status_code != 200:
        return _log(False, "start 后列出会话失败", {"status_code": r.status_code, "text": r.text})
    ids = {s["id"] for s in r.json()}
    ok &= _log(ctx["session_id_1"] in ids, "start 后默认列表中会话可见场景", list(ids))

    # 8. start session_id_2（not_started，group 已有 ongoing session_id_1）→ 409
    r = requests.post(f"{BASE_URL}/api/sessions/{ctx['session_id_2']}/start", headers=headers_member)
    ok &= _log(r.status_code == 409, "另一 not_started 会话 start 时 409（互斥）场景", {"status_code": r.status_code, "body": r.text})

    return ok


# ---------- 结束 / 归档会话相关 ----------


def scenario_end_session(ctx: Dict[str, Any]) -> bool:
    ok = True

    # member 结束 session_1
    headers_member = {"Authorization": f"Bearer {ctx['member_token']}"}
    r = requests.post(
        f"{BASE_URL}/api/sessions/{ctx['session_id_1']}/end",
        headers=headers_member,
    )
    if r.status_code != 200:
        return _log(False, "member 结束会话失败", {"status_code": r.status_code, "text": r.text})
    ok &= _log(True, "member 结束会话场景", r.json())

    # 默认列表不再包含 session_1，只包含 session_2
    headers_leader = {"Authorization": f"Bearer {ctx['leader_token']}"}
    r = requests.get(f"{BASE_URL}/api/groups/{ctx['group_id']}/sessions", headers=headers_leader)
    if r.status_code != 200:
        return _log(False, "结束后 leader 列出会话失败", {"status_code": r.status_code, "text": r.text})
    sessions = r.json()
    ids = {s["id"] for s in sessions}
    ok &= _log(
        ctx["session_id_1"] not in ids and ctx["session_id_2"] in ids,
        "结束后默认列表仅包含未结束会话场景",
        sessions,
    )

    # include_ended=true 时能看到所有会话
    r = requests.get(
        f"{BASE_URL}/api/groups/{ctx['group_id']}/sessions",
        params={"include_ended": "true"},
        headers=headers_leader,
    )
    if r.status_code != 200:
        return _log(False, "include_ended=true 列出会话失败", {"status_code": r.status_code, "text": r.text})
    sessions = r.json()
    ids = {s["id"] for s in sessions}
    ok &= _log(
        ctx["session_id_1"] in ids and ctx["session_id_2"] in ids,
        "include_ended=true 列表包含所有会话场景",
        sessions,
    )

    # outsider 结束会话应失败
    headers_outsider = {"Authorization": f"Bearer {ctx['outsider_token']}"}
    r = requests.post(
        f"{BASE_URL}/api/sessions/{ctx['session_id_2']}/end",
        headers=headers_outsider,
    )
    ok &= _log(r.status_code == 403, "outsider 结束会话被禁止场景", {"status_code": r.status_code, "body": r.text})

    # 结束不存在的会话
    r = requests.post(
        f"{BASE_URL}/api/sessions/nonexistent-session/end",
        headers=headers_leader,
    )
    ok &= _log(r.status_code == 404, "结束不存在会话返回 404 场景", {"status_code": r.status_code, "body": r.text})

    return ok


# ---------- 转写列表相关（这里只检查权限 & 基本行为） ----------


def scenario_transcripts_permissions(ctx: Dict[str, Any]) -> bool:
    ok = True

    # 对已有的 session_2（未结束），成员应该可以查转写（可能为空 list，也算成功）
    headers_member = {"Authorization": f"Bearer {ctx['member_token']}"}
    r = requests.get(
        f"{BASE_URL}/api/sessions/{ctx['session_id_2']}/transcripts",
        headers=headers_member,
    )
    ok &= _log(r.status_code == 200, "群成员查看会话转写场景", {"status_code": r.status_code, "body": r.text})

    # outsider 查同一会话应 403
    headers_outsider = {"Authorization": f"Bearer {ctx['outsider_token']}"}
    r = requests.get(
        f"{BASE_URL}/api/sessions/{ctx['session_id_2']}/transcripts",
        headers=headers_outsider,
    )
    ok &= _log(r.status_code == 403, "outsider 查看会话转写被禁止场景", {"status_code": r.status_code, "body": r.text})

    # 查看不存在的会话转写应 404
    headers_leader = {"Authorization": f"Bearer {ctx['leader_token']}"}
    r = requests.get(
        f"{BASE_URL}/api/sessions/nonexistent-session/transcripts",
        headers=headers_leader,
    )
    ok &= _log(r.status_code == 404, "查看不存在会话转写返回 404 场景", {"status_code": r.status_code, "body": r.text})

    return ok


# ---------- 总入口 ----------


def run_all() -> bool:
    print("=== 开始 Sessions 会话相关功能测试 ===")
    ctx: Dict[str, Any] = {}

    ok = True
    ok &= setup_group_with_members(ctx)
    if not ok:
        print("准备阶段失败，后续场景跳过 ❌")
        return False

    ok &= scenario_create_sessions(ctx)
    ok &= scenario_list_sessions(ctx)
    ok &= scenario_update_session_titles(ctx)
    ok &= scenario_start_session(ctx)
    ok &= scenario_end_session(ctx)
    ok &= scenario_transcripts_permissions(ctx)

    print("\n=== Sessions 测试结果: {} ===".format("全部通过 ✅" if ok else "有失败 ❌"))
    return ok


if __name__ == "__main__":
    import sys
    sys.exit(0 if run_all() else 1)

