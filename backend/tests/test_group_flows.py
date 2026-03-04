from __future__ import annotations

import uuid
from typing import Any, Dict, Tuple

import requests

BASE_URL = "http://127.0.0.1:8000"


def _log(ok: bool, message: str, extra: Any | None = None) -> bool:
    prefix = "✅" if ok else "❌"
    print(f"{prefix} {message}")
    if not ok and extra is not None:
        print("   详情:", extra)
    return ok


def register_and_login(name: str, email_suffix: str) -> Tuple[str, str]:
    """注册一个用户并登录，返回 (access_token, user_id)。"""
    email = f"test_{email_suffix}_{uuid.uuid4().hex[:6]}@example.com"
    password = "test_password_123"

    r = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={
            "name": name,
            "email": email,
            "password": password,
            "device_token": "test_device_token",
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


def scenario_create_group_as_leader(ctx: Dict[str, Any]) -> bool:
    headers = {"Authorization": f"Bearer {ctx['leader_token']}"}
    r = requests.post(
        f"{BASE_URL}/api/groups",
        json={"name": "初始组名"},
        headers=headers,
    )
    if r.status_code != 201:
        # 不尝试解析 JSON，直接输出原始响应，方便排查问题
        return _log(
            False,
            "创建群组失败（期望 201）",
            {"status_code": r.status_code, "text": r.text},
        )

    data = r.json()
    ctx["group_id"] = data["group"]["id"]
    ok = (
        data["group"]["name"] == "初始组名"
        and data["member_count"] == 1
        and data["my_role"] == "leader"
    )
    return _log(ok, "leader 创建群组场景", data)


def scenario_list_my_groups_leader(ctx: Dict[str, Any]) -> bool:
    headers = {"Authorization": f"Bearer {ctx['leader_token']}"}
    r = requests.get(f"{BASE_URL}/api/groups/my", headers=headers)
    if r.status_code != 200:
        return _log(False, "leader 查看自己所在群组失败（期望 200）", r.json())

    groups = r.json()
    found = next((g for g in groups if g["id"] == ctx["group_id"]), None)
    ok = bool(found) and found["my_role"] == "leader"
    return _log(ok, "leader /groups/my 场景", groups)


def scenario_member_join_group(ctx: Dict[str, Any], token_key: str, expected_count: int) -> bool:
    headers = {"Authorization": f"Bearer {ctx[token_key]}"}
    r = requests.post(f"{BASE_URL}/api/groups/{ctx['group_id']}/join", headers=headers)
    if r.status_code != 200:
        return _log(False, f"{token_key} 加入群组失败（期望 200）", r.json())

    data = r.json()
    ok = data["member_count"] == expected_count
    return _log(ok, f"{token_key} 加入群组后人数检查场景", data)


def scenario_group_full(ctx: Dict[str, Any]) -> bool:
    headers = {"Authorization": f"Bearer {ctx['fourth_token']}"}
    r = requests.post(f"{BASE_URL}/api/groups/{ctx['group_id']}/join", headers=headers)
    ok = r.status_code == 409
    return _log(ok, "第四个用户加入人数已满场景", {"status_code": r.status_code, "body": r.json()})


def scenario_member_leave(ctx: Dict[str, Any]) -> bool:
    headers = {"Authorization": f"Bearer {ctx['second_token']}"}
    r = requests.post(f"{BASE_URL}/api/groups/{ctx['group_id']}/leave", headers=headers)
    if r.status_code != 200:
        return _log(False, "second 成员退出群组失败（期望 200）", r.json())

    headers_leader = {"Authorization": f"Bearer {ctx['leader_token']}"}
    r2 = requests.get(f"{BASE_URL}/api/groups/{ctx['group_id']}", headers=headers_leader)
    if r2.status_code != 200:
        return _log(False, "leader 查看群组详情失败（期望 200）", r2.json())

    data = r2.json()
    ok = data["member_count"] == 2  # leader + third
    return _log(ok, "成员退出后人数检查场景", data)


def scenario_rename_group_by_leader(ctx: Dict[str, Any]) -> bool:
    headers = {"Authorization": f"Bearer {ctx['leader_token']}"}
    r = requests.patch(
        f"{BASE_URL}/api/groups/{ctx['group_id']}",
        json={"name": "新的组名"},
        headers=headers,
    )
    if r.status_code != 200:
        return _log(False, "leader 修改组名失败（期望 200）", r.json())

    data = r.json()
    ok = data["group"]["name"] == "新的组名"
    return _log(ok, "leader 修改组名场景", data)


def scenario_rename_group_by_member_forbidden(ctx: Dict[str, Any]) -> bool:
    headers = {"Authorization": f"Bearer {ctx['third_token']}"}
    r = requests.patch(
        f"{BASE_URL}/api/groups/{ctx['group_id']}",
        json={"name": "不应该生效的名字"},
        headers=headers,
    )
    ok = r.status_code == 403
    return _log(ok, "非 leader 修改组名被禁止场景", {"status_code": r.status_code, "body": r.json()})


def scenario_kick_member_by_leader(ctx: Dict[str, Any]) -> bool:
    headers = {"Authorization": f"Bearer {ctx['leader_token']}"}
    r = requests.post(
        f"{BASE_URL}/api/groups/{ctx['group_id']}/members/{ctx['third_user_id']}/kick",
        headers=headers,
    )
    if r.status_code != 200:
        return _log(False, "leader 踢出成员失败（期望 200）", r.json())

    data = r.json()
    member_ids = [m["user_id"] for m in data["members"]]
    ok = (ctx["third_user_id"] not in member_ids) and data["member_count"] == 1
    return _log(ok, "leader 踢出成员后人数与成员列表检查场景", data)


def scenario_kick_member_by_non_leader_forbidden(ctx: Dict[str, Any]) -> bool:
    headers = {"Authorization": f"Bearer {ctx['third_token']}"}
    r = requests.post(
        f"{BASE_URL}/api/groups/{ctx['group_id']}/members/{ctx['leader_user_id']}/kick",
        headers=headers,
    )
    ok = r.status_code == 403
    return _log(ok, "非 leader 踢人被禁止场景", {"status_code": r.status_code, "body": r.json()})


def run_all() -> None:
    print("=== 开始 Group 组队相关功能测试 ===")

    ctx: Dict[str, Any] = {}

    ctx["leader_token"], ctx["leader_user_id"] = register_and_login("组长用户", "leader")
    ctx["second_token"], ctx["second_user_id"] = register_and_login("第二成员", "second")
    ctx["third_token"], ctx["third_user_id"] = register_and_login("第三成员", "third")
    ctx["fourth_token"], ctx["fourth_user_id"] = register_and_login("第四成员", "fourth")

    ok = True
    ok &= scenario_create_group_as_leader(ctx)
    ok &= scenario_list_my_groups_leader(ctx)
    ok &= scenario_member_join_group(ctx, "second_token", expected_count=2)
    ok &= scenario_member_join_group(ctx, "third_token", expected_count=3)
    ok &= scenario_group_full(ctx)
    ok &= scenario_member_leave(ctx)
    ok &= scenario_rename_group_by_leader(ctx)
    ok &= scenario_rename_group_by_member_forbidden(ctx)
    ok &= scenario_kick_member_by_leader(ctx)
    ok &= scenario_kick_member_by_non_leader_forbidden(ctx)

    print("\n=== Group 测试结果: {} ===".format("全部通过 ✅" if ok else "有失败 ❌"))


if __name__ == "__main__":
    run_all()

