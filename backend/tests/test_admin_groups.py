from __future__ import annotations

import uuid
from typing import Any, Dict, List

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


def register_and_login_for_groups(label: str) -> Dict[str, Any]:
    """注册并登录一个用户，返回 dict，其中包含 id 和 access_token。"""
    email = f"admin_group_{label}_{uuid.uuid4().hex[:6]}@example.com"
    password = "test_password_123"

    r = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={
            "name": f"群组测试用户-{label}",
            "email": email,
            "password": password,
            "device_token": f"device-group-{label}",
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


def create_group_as_user(access_token: str, name: str) -> Dict[str, Any]:
    """使用业务接口创建一个群组，返回群组详情。"""
    headers = {"Authorization": f"Bearer {access_token}"}
    r = requests.post(
        f"{BASE_URL}/api/groups",
        json={"name": name},
        headers=headers,
    )
    r.raise_for_status()
    return r.json()


# ---------- 场景：准备测试群 ----------


def setup_groups(ctx: Dict[str, Any]) -> bool:
    """注册一个用户，并创建若干群组，供后续 admin 场景使用。"""
    auth_info = register_and_login_for_groups("creator")
    ctx["creator_token"] = auth_info["access_token"]

    groups: List[Dict[str, Any]] = []
    for i in range(1, 4):
        group_detail = create_group_as_user(
            auth_info["access_token"],
            name=f"管理测试群-{i}",
        )
        groups.append(group_detail["group"])

    ctx["groups"] = groups
    return _log(True, "准备阶段：成功创建 3 个测试群组", groups)


# ---------- 场景：管理员分页列出群 ----------


def scenario_admin_list_groups_basic(ctx: Dict[str, Any]) -> bool:
    r = requests.get(
        f"{BASE_URL}/api/admin/groups",
        params={"page": 1, "page_size": 10},
        headers=ADMIN_HEADERS,
    )
    if r.status_code != 200:
        return _log(False, "admin 列出群组失败（期望 200）", {"status_code": r.status_code, "body": r.text})

    data = r.json()
    ok = isinstance(data.get("items"), list) and isinstance(data.get("meta"), dict)

    # 至少包含我们刚刚创建的某一个群
    created_ids = {g["id"] for g in ctx["groups"]}
    returned_ids = {item["id"] for item in data["items"]}
    ok = ok and bool(created_ids & returned_ids)

    return _log(ok, "admin 基础分页列出群组场景", data)


# ---------- 场景：管理员按条件过滤群 ----------


def scenario_admin_list_groups_with_filters(ctx: Dict[str, Any]) -> bool:
    ok = True

    target_group = ctx["groups"][0]
    name_part = target_group["name"][3:] if len(target_group["name"]) > 3 else target_group["name"]

    # 按 name 模糊过滤
    r = requests.get(
        f"{BASE_URL}/api/admin/groups",
        params={"page": 1, "page_size": 10, "name": name_part},
        headers=ADMIN_HEADERS,
    )
    if r.status_code != 200:
        return _log(False, "admin 按 name 过滤群组失败（期望 200）", {"status_code": r.status_code, "body": r.text})
    data = r.json()
    returned_ids = {item["id"] for item in data["items"]}
    ok &= _log(target_group["id"] in returned_ids, "admin 按 name 过滤群组场景", data)

    # 为了测试 is_active 过滤：先把其中一个群设为 inactive
    gid_to_toggle = ctx["groups"][1]["id"]
    r2 = requests.patch(
        f"{BASE_URL}/api/admin/groups/{gid_to_toggle}",
        json={"is_active": False},
        headers=ADMIN_HEADERS,
    )
    if r2.status_code != 200:
        return _log(False, "admin 将群组设为 inactive 失败（期望 200）", {"status_code": r2.status_code, "body": r2.text})

    # is_active=true 列表中不应包含该群
    r3 = requests.get(
        f"{BASE_URL}/api/admin/groups",
        params={"page": 1, "page_size": 20, "is_active": True},
        headers=ADMIN_HEADERS,
    )
    if r3.status_code != 200:
        return _log(False, "admin 按 is_active=true 过滤群组失败（期望 200）", {"status_code": r3.status_code, "body": r3.text})
    data3 = r3.json()
    active_ids = {item["id"] for item in data3["items"]}
    ok &= _log(
        gid_to_toggle not in active_ids,
        "admin 按 is_active=true 过滤群组（不包含 inactive 群）场景",
        data3,
    )

    # is_active=false 列表中应包含该群
    r4 = requests.get(
        f"{BASE_URL}/api/admin/groups",
        params={"page": 1, "page_size": 20, "is_active": False},
        headers=ADMIN_HEADERS,
    )
    if r4.status_code != 200:
        return _log(False, "admin 按 is_active=false 过滤群组失败（期望 200）", {"status_code": r4.status_code, "body": r4.text})
    data4 = r4.json()
    inactive_ids = {item["id"] for item in data4["items"]}
    ok &= _log(
        gid_to_toggle in inactive_ids,
        "admin 按 is_active=false 过滤群组（包含 inactive 群）场景",
        data4,
    )

    return ok


# ---------- 场景：管理员创建群 ----------


def scenario_admin_create_group_success(ctx: Dict[str, Any]) -> bool:
    name = "后台创建群-成功场景"
    r = requests.post(
        f"{BASE_URL}/api/admin/groups",
        json={"name": name},
        headers=ADMIN_HEADERS,
    )
    if r.status_code != 201:
        return _log(
            False,
            "admin 创建群组失败（期望 201）",
            {"status_code": r.status_code, "body": r.text},
        )

    data = r.json()
    ok = isinstance(data.get("id"), str) and data.get("name") == name and data.get("is_active") is True
    ok &= _log(ok, "admin 创建群组成功场景", data)

    # 记录下来，供后续校验或排查
    ctx.setdefault("admin_groups", []).append(data)

    # 再通过详情接口确认
    gid = data["id"]
    r2 = requests.get(
        f"{BASE_URL}/api/admin/groups/{gid}",
        headers=ADMIN_HEADERS,
    )
    if r2.status_code != 200:
        return _log(
            False,
            "admin 创建后获取群组详情失败（期望 200）",
            {"status_code": r2.status_code, "body": r2.text},
        )
    data2 = r2.json()
    ok &= _log(
        data2["id"] == gid and data2["name"] == name and data2["is_active"] is True,
        "admin 创建群组后详情校验场景",
        data2,
    )
    return ok


def scenario_admin_create_group_with_inactive() -> bool:
    """
    显式传 is_active=false 创建群组，并通过列表过滤校验其状态。
    """
    name = "后台创建群-初始停用"
    r = requests.post(
        f"{BASE_URL}/api/admin/groups",
        json={"name": name, "is_active": False},
        headers=ADMIN_HEADERS,
    )
    if r.status_code != 201:
        return _log(
            False,
            "admin 创建初始为 inactive 的群组失败（期望 201）",
            {"status_code": r.status_code, "body": r.text},
        )

    data = r.json()
    gid = data["id"]
    ok = data["name"] == name and data["is_active"] is False
    ok &= _log(ok, "admin 创建初始为 inactive 的群组场景", data)

    # is_active=true 列表中不应包含该群
    r_active = requests.get(
        f"{BASE_URL}/api/admin/groups",
        params={"page": 1, "page_size": 50, "is_active": True},
        headers=ADMIN_HEADERS,
    )
    if r_active.status_code != 200:
        return _log(
            False,
            "admin 按 is_active=true 过滤时请求失败（期望 200）",
            {"status_code": r_active.status_code, "body": r_active.text},
        )
    active_ids = {item["id"] for item in r_active.json()["items"]}
    ok &= _log(
        gid not in active_ids,
        "admin 创建为 inactive 的群组在 is_active=true 列表中不可见场景",
        r_active.json(),
    )

    # is_active=false 列表中应包含该群
    r_inactive = requests.get(
        f"{BASE_URL}/api/admin/groups",
        params={"page": 1, "page_size": 50, "is_active": False},
        headers=ADMIN_HEADERS,
    )
    if r_inactive.status_code != 200:
        return _log(
            False,
            "admin 按 is_active=false 过滤时请求失败（期望 200）",
            {"status_code": r_inactive.status_code, "body": r_inactive.text},
        )
    inactive_ids = {item["id"] for item in r_inactive.json()["items"]}
    ok &= _log(
        gid in inactive_ids,
        "admin 创建为 inactive 的群组在 is_active=false 列表中可见场景",
        r_inactive.json(),
    )

    return ok


def scenario_admin_create_group_missing_name() -> bool:
    """
    缺少必填字段 name，应触发请求体验证错误。
    FastAPI/Pydantic 对缺失必填字段默认返回 422。
    """
    r = requests.post(
        f"{BASE_URL}/api/admin/groups",
        json={},
        headers=ADMIN_HEADERS,
    )
    ok = r.status_code == 422
    return _log(
        ok,
        "admin 创建群组但缺少 name 字段返回 422 场景",
        {"status_code": r.status_code, "body": r.text},
    )


# ---------- 场景：获取群详情 ----------


def scenario_admin_get_group_detail(ctx: Dict[str, Any]) -> bool:
    target_group = ctx["groups"][0]
    gid = target_group["id"]

    r = requests.get(
        f"{BASE_URL}/api/admin/groups/{gid}",
        headers=ADMIN_HEADERS,
    )
    if r.status_code != 200:
        return _log(False, "admin 获取群组详情失败（期望 200）", {"status_code": r.status_code, "body": r.text})

    data = r.json()
    ok = data["id"] == gid and data["name"] == target_group["name"]
    return _log(ok, "admin 获取群组详情场景", data)


def scenario_admin_get_group_not_found() -> bool:
    r = requests.get(
        f"{BASE_URL}/api/admin/groups/g_non_exist_12345",
        headers=ADMIN_HEADERS,
    )
    ok = r.status_code == 404
    return _log(ok, "admin 获取不存在群组返回 404 场景", {"status_code": r.status_code, "body": r.text})


# ---------- 场景：更新群 ----------


def scenario_admin_update_group_success(ctx: Dict[str, Any]) -> bool:
    target_group = ctx["groups"][2]
    gid = target_group["id"]
    new_name = "管理员修改后的群名"

    r = requests.patch(
        f"{BASE_URL}/api/admin/groups/{gid}",
        json={"name": new_name},
        headers=ADMIN_HEADERS,
    )
    if r.status_code != 200:
        return _log(False, "admin 更新群组名称失败（期望 200）", {"status_code": r.status_code, "body": r.text})

    data = r.json()
    ok = data["name"] == new_name
    ok &= _log(ok, "admin 更新群组名称场景", data)

    # 再获取详情确认
    r2 = requests.get(
        f"{BASE_URL}/api/admin/groups/{gid}",
        headers=ADMIN_HEADERS,
    )
    if r2.status_code != 200:
        return _log(False, "admin 更新后再次获取群组详情失败（期望 200）", {"status_code": r2.status_code, "body": r2.text})
    data2 = r2.json()
    ok &= _log(data2["name"] == new_name, "admin 更新群组名称后详情校验场景", data2)
    return ok


def scenario_admin_update_group_toggle_active(ctx: Dict[str, Any]) -> bool:
    # 选第一个群做状态切换
    target_group = ctx["groups"][0]
    gid = target_group["id"]

    ok = True

    # 先设为 false
    r = requests.patch(
        f"{BASE_URL}/api/admin/groups/{gid}",
        json={"is_active": False},
        headers=ADMIN_HEADERS,
    )
    if r.status_code != 200:
        return _log(False, "admin 将群组设为 inactive 失败（期望 200）", {"status_code": r.status_code, "body": r.text})
    data = r.json()
    ok &= _log(data["is_active"] is False, "admin 将群组设为 inactive 场景", data)

    # 再设回 true
    r2 = requests.patch(
        f"{BASE_URL}/api/admin/groups/{gid}",
        json={"is_active": True},
        headers=ADMIN_HEADERS,
    )
    if r2.status_code != 200:
        return _log(False, "admin 将群组设回 active 失败（期望 200）", {"status_code": r2.status_code, "body": r2.text})
    data2 = r2.json()
    ok &= _log(data2["is_active"] is True, "admin 将群组设回 active 场景", data2)

    return ok


def scenario_admin_update_group_no_fields(ctx: Dict[str, Any]) -> bool:
    target_group = ctx["groups"][0]
    gid = target_group["id"]

    r = requests.patch(
        f"{BASE_URL}/api/admin/groups/{gid}",
        json={},
        headers=ADMIN_HEADERS,
    )
    ok = r.status_code == 400
    return _log(ok, "admin 更新群组但没有任何字段返回 400 场景", {"status_code": r.status_code, "body": r.text})


# ---------- 场景：删除群 ----------


def scenario_admin_delete_group_success(ctx: Dict[str, Any]) -> bool:
    # 单独创建一个用于删除测试的群
    creator_token = ctx["creator_token"]
    group_detail = create_group_as_user(creator_token, name="待删除测试群")
    gid = group_detail["group"]["id"]

    r = requests.delete(
        f"{BASE_URL}/api/admin/groups/{gid}",
        headers=ADMIN_HEADERS,
    )
    if r.status_code != 204:
        return _log(False, "admin 删除群组失败（期望 204）", {"status_code": r.status_code, "body": r.text})

    # 再获取详情应该 404
    r2 = requests.get(
        f"{BASE_URL}/api/admin/groups/{gid}",
        headers=ADMIN_HEADERS,
    )
    ok = r2.status_code == 404
    return _log(ok, "admin 删除群组后再次获取返回 404 场景", {"status_code": r2.status_code, "body": r2.text})


def scenario_admin_delete_group_not_found() -> bool:
    r = requests.delete(
        f"{BASE_URL}/api/admin/groups/g_non_exist_6789",
        headers=ADMIN_HEADERS,
    )
    ok = r.status_code == 404
    return _log(ok, "admin 删除不存在群组返回 404 场景", {"status_code": r.status_code, "body": r.text})


# ---------- 场景：管理员 token 缺失 / 错误 ----------


def scenario_admin_missing_or_wrong_token() -> bool:
    ok = True

    # 不带任何 X-Admin-Token
    r = requests.get(f"{BASE_URL}/api/admin/groups")
    ok &= _log(
        r.status_code == 403,
        "缺少 X-Admin-Token 访问后台群组接口被禁止场景",
        {"status_code": r.status_code, "body": r.text},
    )

    # 不带 X-Admin-Token 调用创建群组接口
    r_create = requests.post(
        f"{BASE_URL}/api/admin/groups",
        json={"name": "no-token-admin-group"},
    )
    ok &= _log(
        r_create.status_code == 403,
        "缺少 X-Admin-Token 调用 admin 创建群组接口被禁止场景",
        {"status_code": r_create.status_code, "body": r_create.text},
    )

    # 带错误的 token
    r = requests.get(
        f"{BASE_URL}/api/admin/groups",
        headers={"X-Admin-Token": "WrongKey"},
    )
    ok &= _log(
        r.status_code == 403,
        "错误 X-Admin-Token 访问后台群组接口被禁止场景",
        {"status_code": r.status_code, "body": r.text},
    )

    # 带错误 token 调用创建群组接口
    r_create_wrong = requests.post(
        f"{BASE_URL}/api/admin/groups",
        json={"name": "wrong-token-admin-group"},
        headers={"X-Admin-Token": "WrongKey"},
    )
    ok &= _log(
        r_create_wrong.status_code == 403,
        "错误 X-Admin-Token 调用 admin 创建群组接口被禁止场景",
        {"status_code": r_create_wrong.status_code, "body": r_create_wrong.text},
    )

    return ok


# ---------- 总入口 ----------


def run_all() -> None:
    print("=== 开始 Admin Groups 后台接口测试 ===")
    ctx: Dict[str, Any] = {}

    ok = True
    ok &= setup_groups(ctx)
    ok &= scenario_admin_list_groups_basic(ctx)
    ok &= scenario_admin_list_groups_with_filters(ctx)
    ok &= scenario_admin_create_group_success(ctx)
    ok &= scenario_admin_create_group_with_inactive()
    ok &= scenario_admin_create_group_missing_name()
    ok &= scenario_admin_get_group_detail(ctx)
    ok &= scenario_admin_get_group_not_found()
    ok &= scenario_admin_update_group_success(ctx)
    ok &= scenario_admin_update_group_toggle_active(ctx)
    ok &= scenario_admin_update_group_no_fields(ctx)
    ok &= scenario_admin_delete_group_success(ctx)
    ok &= scenario_admin_delete_group_not_found()
    ok &= scenario_admin_missing_or_wrong_token()

    print("\n=== Admin Groups 测试结果: {} ===".format("全部通过 ✅" if ok else "有失败 ❌"))


if __name__ == "__main__":
    run_all()

