from __future__ import annotations

import uuid
from typing import Any, Dict

import requests

BASE_URL = "http://127.0.0.1:8000"

# 和 app.admin.deps 中的默认值保持一致
ADMIN_KEY = "TestAdminKey123"
ADMIN_HEADERS = {"X-Admin-Token": ADMIN_KEY}


def _log(ok: bool, message: str, extra: Any | None = None) -> bool:
    prefix = "✅" if ok else "❌"
    print(f"{prefix} {message}")
    if not ok and extra is not None:
        print("   详情:", extra)
    return ok


def register_and_login(label: str) -> Dict[str, Any]:
    """注册并登录一个用户，返回 dict：{ user, access_token }。"""
    email = f"admin_session_{label}_{uuid.uuid4().hex[:6]}@example.com"
    password = "test_password_123"

    r = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={
            "name": f"会话测试用户-{label}",
            "email": email,
            "password": password,
            "device_token": f"device-session-{label}",
        },
    )
    r.raise_for_status()
    user = r.json()

    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
    )
    r.raise_for_status()
    data = r.json()
    token = data["access_token"]

    return {"user": user, "access_token": token}


def create_group(access_token: str, name: str) -> Dict[str, Any]:
    headers = {"Authorization": f"Bearer {access_token}"}
    r = requests.post(
        f"{BASE_URL}/api/groups",
        json={"name": name},
        headers=headers,
    )
    r.raise_for_status()
    return r.json()


def create_session(access_token: str, group_id: str, title: str) -> Dict[str, Any]:
    headers = {"Authorization": f"Bearer {access_token}"}
    r = requests.post(
        f"{BASE_URL}/api/groups/{group_id}/sessions",
        json={"session_title": title},
        headers=headers,
    )
    r.raise_for_status()
    return r.json()


def end_session(access_token: str, session_id: str) -> Dict[str, Any]:
    headers = {"Authorization": f"Bearer {access_token}"}
    r = requests.post(
        f"{BASE_URL}/api/sessions/{session_id}/end",
        headers=headers,
    )
    r.raise_for_status()
    return r.json()


# ---------- 场景：准备 chat_sessions ----------


def setup_chat_sessions(ctx: Dict[str, Any]) -> bool:
    """
    注册一个用户，创建群，在群下创建两个会话，并结束其中一个，制造 active / inactive 场景。
    """
    info = register_and_login("owner")
    access_token = info["access_token"]

    group_detail = create_group(access_token, name="Admin 会话测试群")
    group_id = group_detail["group"]["id"]
    ctx["group_id"] = group_id

    # 创建两个会话
    s1 = create_session(access_token, group_id, title="第一次会话")
    s2 = create_session(access_token, group_id, title="第二次会话")
    session_id_1 = s1["id"]
    session_id_2 = s2["id"]

    ctx["session_id_1"] = session_id_1
    ctx["session_id_2"] = session_id_2

    # 结束第一个会话
    end_session(access_token, session_id_1)

    return _log(True, "准备阶段：成功创建 2 个会话，并结束其中 1 个", {"group_id": group_id, "session1": s1, "session2": s2})


# ---------- 场景：管理员分页列出会话 ----------


def scenario_admin_list_chat_sessions_basic(ctx: Dict[str, Any]) -> bool:
    r = requests.get(
        f"{BASE_URL}/api/admin/chat-sessions",
        params={"page": 1, "page_size": 10},
        headers=ADMIN_HEADERS,
    )
    if r.status_code != 200:
        return _log(False, "admin 分页列出会话失败（期望 200）", {"status_code": r.status_code, "body": r.text})

    data = r.json()
    ok = isinstance(data.get("items"), list) and isinstance(data.get("meta"), dict)

    ids = {item["id"] for item in data["items"]}
    ok = ok and (ctx["session_id_1"] in ids or ctx["session_id_2"] in ids)

    return _log(ok, "admin 基础分页列出会话场景", data)


# ---------- 场景：管理员按条件过滤会话 ----------


def scenario_admin_list_chat_sessions_filters(ctx: Dict[str, Any]) -> bool:
    ok = True
    group_id = ctx["group_id"]

    # 按 group_id 过滤
    r = requests.get(
        f"{BASE_URL}/api/admin/chat-sessions",
        params={"group_id": group_id, "page": 1, "page_size": 20},
        headers=ADMIN_HEADERS,
    )
    if r.status_code != 200:
        return _log(False, "admin 按 group_id 过滤会话失败（期望 200）", {"status_code": r.status_code, "body": r.text})
    data = r.json()
    ok &= _log(
        all(item["group_id"] == group_id for item in data["items"]) and len(data["items"]) >= 2,
        "admin 按 group_id 过滤会话场景",
        data,
    )

    # 按 is_active=true 过滤（应该只包含未结束的会话）
    r2 = requests.get(
        f"{BASE_URL}/api/admin/chat-sessions",
        params={"group_id": group_id, "is_active": True, "page": 1, "page_size": 20},
        headers=ADMIN_HEADERS,
    )
    if r2.status_code != 200:
        return _log(False, "admin 按 is_active=true 过滤会话失败（期望 200）", {"status_code": r2.status_code, "body": r2.text})
    data2 = r2.json()
    ids2 = {item["id"] for item in data2["items"]}
    ok &= _log(
        ctx["session_id_2"] in ids2 and ctx["session_id_1"] not in ids2,
        "admin 按 is_active=true 过滤会话场景",
        data2,
    )

    # 按 is_active=false 过滤（应该包含已结束的会话）
    r3 = requests.get(
        f"{BASE_URL}/api/admin/chat-sessions",
        params={"group_id": group_id, "is_active": False, "page": 1, "page_size": 20},
        headers=ADMIN_HEADERS,
    )
    if r3.status_code != 200:
        return _log(False, "admin 按 is_active=false 过滤会话失败（期望 200）", {"status_code": r3.status_code, "body": r3.text})
    data3 = r3.json()
    ids3 = {item["id"] for item in data3["items"]}
    ok &= _log(
        ctx["session_id_1"] in ids3,
        "admin 按 is_active=false 过滤会话场景",
        data3,
    )

    # 按 session_title 模糊搜索
    r4 = requests.get(
        f"{BASE_URL}/api/admin/chat-sessions",
        params={"session_title": "第一次", "page": 1, "page_size": 10},
        headers=ADMIN_HEADERS,
    )
    if r4.status_code != 200:
        return _log(False, "admin 按 session_title 过滤会话失败（期望 200）", {"status_code": r4.status_code, "body": r4.text})
    data4 = r4.json()
    ids4 = {item["id"] for item in data4["items"]}
    ok &= _log(
        ctx["session_id_1"] in ids4,
        "admin 按 session_title 模糊过滤会话场景",
        data4,
    )

    return ok


# ---------- 场景：获取会话详情 ----------


def scenario_admin_get_chat_session_detail(ctx: Dict[str, Any]) -> bool:
    sid = ctx["session_id_2"]
    r = requests.get(
        f"{BASE_URL}/api/admin/chat-sessions/{sid}",
        headers=ADMIN_HEADERS,
    )
    if r.status_code != 200:
        return _log(False, "admin 获取会话详情失败（期望 200）", {"status_code": r.status_code, "body": r.text})

    data = r.json()
    ok = data["id"] == sid and data["group_id"] == ctx["group_id"]
    return _log(ok, "admin 获取会话详情场景", data)


def scenario_admin_get_chat_session_not_found() -> bool:
    r = requests.get(
        f"{BASE_URL}/api/admin/chat-sessions/s_non_exist_12345",
        headers=ADMIN_HEADERS,
    )
    ok = r.status_code == 404
    return _log(ok, "admin 获取不存在会话返回 404 场景", {"status_code": r.status_code, "body": r.text})


# ---------- 场景：更新会话标题 ----------


def scenario_admin_update_chat_session_title(ctx: Dict[str, Any]) -> bool:
    sid = ctx["session_id_2"]
    new_title = "管理员改名后的会话"

    r = requests.patch(
        f"{BASE_URL}/api/admin/chat-sessions/{sid}",
        json={"session_title": new_title},
        headers=ADMIN_HEADERS,
    )
    if r.status_code != 200:
        return _log(False, "admin 更新会话标题失败（期望 200）", {"status_code": r.status_code, "body": r.text})

    data = r.json()
    ok = data["session_title"] == new_title
    ok &= _log(ok, "admin 更新会话标题场景", data)

    # 再获取详情确认
    r2 = requests.get(
        f"{BASE_URL}/api/admin/chat-sessions/{sid}",
        headers=ADMIN_HEADERS,
    )
    if r2.status_code != 200:
        return _log(False, "admin 更新标题后再次获取会话详情失败（期望 200）", {"status_code": r2.status_code, "body": r2.text})
    data2 = r2.json()
    ok &= _log(data2["session_title"] == new_title, "admin 更新标题后详情校验场景", data2)
    return ok


# ---------- 场景：更新 is_active / ended_at ----------


def scenario_admin_update_chat_session_flags(ctx: Dict[str, Any]) -> bool:
    sid = ctx["session_id_2"]

    r = requests.patch(
        f"{BASE_URL}/api/admin/chat-sessions/{sid}",
        json={
            "is_active": False,
            "ended_at": "2026-03-04T12:00:00Z",
        },
        headers=ADMIN_HEADERS,
    )
    if r.status_code != 200:
        return _log(False, "admin 更新会话 is_active/ended_at 失败（期望 200）", {"status_code": r.status_code, "body": r.text})

    data = r.json()
    ok = (data.get("is_active") is False) and (data.get("ended_at") is not None)
    ok &= _log(ok, "admin 更新会话 is_active/ended_at 场景", data)

    # 再按 is_active=false 过滤时应能看到该会话
    r2 = requests.get(
        f"{BASE_URL}/api/admin/chat-sessions",
        params={"group_id": ctx["group_id"], "is_active": False, "page": 1, "page_size": 20},
        headers=ADMIN_HEADERS,
    )
    if r2.status_code != 200:
        return _log(False, "admin 更新 flags 后按 is_active=false 过滤失败（期望 200）", {"status_code": r2.status_code, "body": r2.text})
    data2 = r2.json()
    ids2 = {item["id"] for item in data2["items"]}
    ok &= _log(
        sid in ids2,
        "admin 更新 flags 后按 is_active=false 过滤包含该会话场景",
        data2,
    )
    return ok


def scenario_admin_update_chat_session_no_fields(ctx: Dict[str, Any]) -> bool:
    sid = ctx["session_id_1"]
    r = requests.patch(
        f"{BASE_URL}/api/admin/chat-sessions/{sid}",
        json={},
        headers=ADMIN_HEADERS,
    )
    ok = r.status_code == 400
    return _log(ok, "admin 更新会话但没有任何字段返回 400 场景", {"status_code": r.status_code, "body": r.text})


# ---------- 场景：删除会话 ----------


def scenario_admin_delete_chat_session_success(ctx: Dict[str, Any]) -> bool:
    # 使用业务接口再创建一个临时会话，仅用于删除测试
    info = register_and_login("temp_session")
    access_token = info["access_token"]
    group_detail = create_group(access_token, name="临时会话群")
    group_id = group_detail["group"]["id"]
    session_detail = create_session(access_token, group_id, title="临时会话")
    sid = session_detail["id"]

    r = requests.delete(
        f"{BASE_URL}/api/admin/chat-sessions/{sid}",
        headers=ADMIN_HEADERS,
    )
    if r.status_code != 204:
        return _log(False, "admin 删除会话失败（期望 204）", {"status_code": r.status_code, "body": r.text})

    # 再获取详情应为 404
    r2 = requests.get(
        f"{BASE_URL}/api/admin/chat-sessions/{sid}",
        headers=ADMIN_HEADERS,
    )
    ok = r2.status_code == 404
    return _log(ok, "admin 删除会话后再次获取返回 404 场景", {"status_code": r2.status_code, "body": r2.text})


def scenario_admin_delete_chat_session_not_found() -> bool:
    r = requests.delete(
        f"{BASE_URL}/api/admin/chat-sessions/s_non_exist_6789",
        headers=ADMIN_HEADERS,
    )
    ok = r.status_code == 404
    return _log(ok, "admin 删除不存在会话返回 404 场景", {"status_code": r.status_code, "body": r.text})


# ---------- 场景：管理员 token 缺失 / 错误 ----------


def scenario_admin_missing_or_wrong_token() -> bool:
    ok = True

    # 不带任何 X-Admin-Token
    r = requests.get(f"{BASE_URL}/api/admin/chat-sessions")
    ok &= _log(
        r.status_code == 403,
        "缺少 X-Admin-Token 访问后台会话接口被禁止场景",
        {"status_code": r.status_code, "body": r.text},
    )

    # 带错误的 token
    r = requests.get(
        f"{BASE_URL}/api/admin/chat-sessions",
        headers={"X-Admin-Token": "WrongKey"},
    )
    ok &= _log(
        r.status_code == 403,
        "错误 X-Admin-Token 访问后台会话接口被禁止场景",
        {"status_code": r.status_code, "body": r.text},
    )

    return ok


# ---------- 总入口 ----------


def run_all() -> None:
    print("=== 开始 Admin Chat Sessions 后台会话接口测试 ===")
    ctx: Dict[str, Any] = {}

    ok = True
    ok &= setup_chat_sessions(ctx)
    ok &= scenario_admin_list_chat_sessions_basic(ctx)
    ok &= scenario_admin_list_chat_sessions_filters(ctx)
    ok &= scenario_admin_get_chat_session_detail(ctx)
    ok &= scenario_admin_get_chat_session_not_found()
    ok &= scenario_admin_update_chat_session_title(ctx)
    ok &= scenario_admin_update_chat_session_flags(ctx)
    ok &= scenario_admin_update_chat_session_no_fields(ctx)
    ok &= scenario_admin_delete_chat_session_success(ctx)
    ok &= scenario_admin_delete_chat_session_not_found()
    ok &= scenario_admin_missing_or_wrong_token()

    print("\n=== Admin Chat Sessions 测试结果: {} ===".format("全部通过 ✅" if ok else "有失败 ❌"))


if __name__ == "__main__":
    run_all()

