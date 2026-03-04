from __future__ import annotations

import uuid
from typing import Any, Dict, Tuple

import requests

BASE_URL = "http://127.0.0.1:8000"

# 和 app.admin.deps 中的默认值保持一致；
# 如需修改，请同时修改 app/admin/deps.py 中的默认 ADMIN_API_KEY。
ADMIN_KEY = "TestAdminKey123"
ADMIN_HEADERS = {"X-Admin-Token": ADMIN_KEY}


def _log(ok: bool, message: str, extra: Any | None = None) -> bool:
    prefix = "✅" if ok else "❌"
    print(f"{prefix} {message}")
    if not ok and extra is not None:
        print("   详情:", extra)
    return ok


def register_dummy_user(label: str) -> Dict[str, Any]:
    """通过业务接口注册一个普通用户，返回完整用户 JSON。"""
    email = f"admin_test_{label}_{uuid.uuid4().hex[:6]}@example.com"
    password = "test_password_123"

    r = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={
            "name": f"用户-{label}",
            "email": email,
            "password": password,
            "device_token": f"device-{label}",
        },
    )
    r.raise_for_status()
    return r.json()


# ---------- 场景：基础准备 ----------


def setup_users(ctx: Dict[str, Any]) -> bool:
    """注册几个测试用户，供后续 admin 场景使用。"""
    users: list[Dict[str, Any]] = []
    for label in ["A", "B", "C"]:
        user = register_dummy_user(label)
        users.append(user)

    ctx["users"] = users
    _log(True, "准备阶段：成功注册 3 个测试用户", users)
    return True


# ---------- 场景：管理员分页列出用户 ----------


def scenario_admin_list_users_basic(ctx: Dict[str, Any]) -> bool:
    r = requests.get(
        f"{BASE_URL}/api/admin/users",
        params={"page": 1, "page_size": 10},
        headers=ADMIN_HEADERS,
    )
    if r.status_code != 200:
        return _log(False, "admin 列出用户失败（期望 200）", {"status_code": r.status_code, "body": r.text})

    data = r.json()
    ok = isinstance(data.get("items"), list) and isinstance(data.get("meta"), dict)

    # 至少包含我们刚刚注册的某一个用户（通过 email 检查）
    emails = {u["email"] for u in ctx["users"]}
    returned_emails = {item["email"] for item in data["items"]}
    ok = ok and bool(emails & returned_emails)

    return _log(ok, "admin 基础分页列出用户场景", data)


# ---------- 场景：管理员按条件过滤用户 ----------


def scenario_admin_list_users_with_filters(ctx: Dict[str, Any]) -> bool:
    ok = True
    target_user = ctx["users"][0]
    email_part = target_user["email"].split("@")[0][5:]  # 取一部分做模糊匹配
    name_part = target_user["name"][1:] if len(target_user["name"]) > 1 else target_user["name"]

    # 按 email 过滤
    r = requests.get(
        f"{BASE_URL}/api/admin/users",
        params={"page": 1, "page_size": 10, "email": email_part},
        headers=ADMIN_HEADERS,
    )
    if r.status_code != 200:
        return _log(False, "admin 按 email 过滤用户失败（期望 200）", {"status_code": r.status_code, "body": r.text})
    data = r.json()
    returned_emails = {item["email"] for item in data["items"]}
    ok &= _log(target_user["email"] in returned_emails, "admin 按 email 过滤用户场景", data)

    # 按 name 过滤
    r = requests.get(
        f"{BASE_URL}/api/admin/users",
        params={"page": 1, "page_size": 10, "name": name_part},
        headers=ADMIN_HEADERS,
    )
    if r.status_code != 200:
        return _log(False, "admin 按 name 过滤用户失败（期望 200）", {"status_code": r.status_code, "body": r.text})
    data = r.json()
    returned_ids = {item["id"] for item in data["items"]}
    ok &= _log(target_user["id"] in returned_ids, "admin 按 name 过滤用户场景", data)

    return ok


# ---------- 场景：获取单个用户详情 ----------


def scenario_admin_get_user_detail(ctx: Dict[str, Any]) -> bool:
    target_user = ctx["users"][1]
    r = requests.get(
        f"{BASE_URL}/api/admin/users/{target_user['id']}",
        headers=ADMIN_HEADERS,
    )
    if r.status_code != 200:
        return _log(False, "admin 获取用户详情失败（期望 200）", {"status_code": r.status_code, "body": r.text})

    data = r.json()
    ok = data["id"] == target_user["id"] and data["email"] == target_user["email"]
    return _log(ok, "admin 获取用户详情场景", data)


def scenario_admin_get_user_not_found() -> bool:
    r = requests.get(
        f"{BASE_URL}/api/admin/users/unexist-user-123",
        headers=ADMIN_HEADERS,
    )
    ok = r.status_code == 404
    return _log(ok, "admin 获取不存在用户返回 404 场景", {"status_code": r.status_code, "body": r.text})


# ---------- 场景：更新用户 ----------


def scenario_admin_update_user_success(ctx: Dict[str, Any]) -> bool:
    target_user = ctx["users"][2]
    new_name = "管理员修改后的名字"
    new_token = "admin_modified_token"

    r = requests.patch(
        f"{BASE_URL}/api/admin/users/{target_user['id']}",
        json={"name": new_name, "device_token": new_token},
        headers=ADMIN_HEADERS,
    )
    if r.status_code != 200:
        return _log(False, "admin 更新用户失败（期望 200）", {"status_code": r.status_code, "body": r.text})

    data = r.json()
    ok = data["name"] == new_name and data.get("device_token") == new_token
    ok &= _log(ok, "admin 更新用户成功场景", data)

    # 再查一次详情确认
    r2 = requests.get(
        f"{BASE_URL}/api/admin/users/{target_user['id']}",
        headers=ADMIN_HEADERS,
    )
    if r2.status_code != 200:
        return _log(False, "admin 更新后再次获取用户详情失败（期望 200）", {"status_code": r2.status_code, "body": r2.text})
    data2 = r2.json()
    ok &= _log(
        data2["name"] == new_name and data2.get("device_token") == new_token,
        "admin 更新用户后详情校验场景",
        data2,
    )
    return ok


def scenario_admin_update_user_no_fields(ctx: Dict[str, Any]) -> bool:
    target_user = ctx["users"][0]
    r = requests.patch(
        f"{BASE_URL}/api/admin/users/{target_user['id']}",
        json={},
        headers=ADMIN_HEADERS,
    )
    ok = r.status_code == 400
    return _log(ok, "admin 更新用户但没有任何字段返回 400 场景", {"status_code": r.status_code, "body": r.text})


# ---------- 场景：删除用户 ----------


def scenario_admin_delete_user_success() -> bool:
    # 先注册一个只用于删除测试的用户
    user = register_dummy_user("ToDelete")
    user_id = user["id"]

    r = requests.delete(
        f"{BASE_URL}/api/admin/users/{user_id}",
        headers=ADMIN_HEADERS,
    )
    if r.status_code != 204:
        return _log(False, "admin 删除用户失败（期望 204）", {"status_code": r.status_code, "body": r.text})

    # 再查一次应该是 404
    r2 = requests.get(
        f"{BASE_URL}/api/admin/users/{user_id}",
        headers=ADMIN_HEADERS,
    )
    ok = r2.status_code == 404
    return _log(ok, "admin 删除用户后再次获取返回 404 场景", {"status_code": r2.status_code, "body": r2.text})


def scenario_admin_delete_user_not_found() -> bool:
    r = requests.delete(
        f"{BASE_URL}/api/admin/users/unexist-user-456",
        headers=ADMIN_HEADERS,
    )
    ok = r.status_code == 404
    return _log(ok, "admin 删除不存在用户返回 404 场景", {"status_code": r.status_code, "body": r.text})


# ---------- 场景：管理员 token 缺失 / 错误 ----------


def scenario_admin_missing_or_wrong_token() -> bool:
    ok = True

    # 不带任何 X-Admin-Token
    r = requests.get(f"{BASE_URL}/api/admin/users")
    ok &= _log(r.status_code == 403, "缺少 X-Admin-Token 访问后台被禁止场景", {"status_code": r.status_code, "body": r.text})

    # 带错误的 token
    r = requests.get(
        f"{BASE_URL}/api/admin/users",
        headers={"X-Admin-Token": "WrongKey"},
    )
    ok &= _log(r.status_code == 403, "错误 X-Admin-Token 访问后台被禁止场景", {"status_code": r.status_code, "body": r.text})

    return ok


# ---------- 总入口 ----------


def run_all() -> None:
    print("=== 开始 Admin Users 后台接口测试 ===")
    ctx: Dict[str, Any] = {}

    ok = True
    ok &= setup_users(ctx)
    ok &= scenario_admin_list_users_basic(ctx)
    ok &= scenario_admin_list_users_with_filters(ctx)
    ok &= scenario_admin_get_user_detail(ctx)
    ok &= scenario_admin_get_user_not_found()
    ok &= scenario_admin_update_user_success(ctx)
    ok &= scenario_admin_update_user_no_fields(ctx)
    ok &= scenario_admin_delete_user_success()
    ok &= scenario_admin_delete_user_not_found()
    ok &= scenario_admin_missing_or_wrong_token()

    print("\n=== Admin Users 测试结果: {} ===".format("全部通过 ✅" if ok else "有失败 ❌"))


if __name__ == "__main__":
    run_all()

