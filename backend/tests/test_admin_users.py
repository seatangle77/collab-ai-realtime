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
    # 用 email 过滤出准备阶段用户，避免 created_at 排序导致不在首页（注册现用 UTC 存库）
    r = requests.get(
        f"{BASE_URL}/api/admin/users",
        params={"page": 1, "page_size": 10, "email": "admin_test_"},
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


# ---------- 场景：用户所在小组信息与按小组名称过滤 ----------


def _create_admin_group(name: str) -> Dict[str, Any]:
    r = requests.post(
        f"{BASE_URL}/api/admin/groups",
        json={"name": name},
        headers=ADMIN_HEADERS,
    )
    r.raise_for_status()
    return r.json()


def _create_admin_membership(group_id: str, user_id: str, role: str = "member", status: str = "active") -> Dict[str, Any]:
    r = requests.post(
        f"{BASE_URL}/api/admin/memberships",
        json={
            "group_id": group_id,
            "user_id": user_id,
            "role": role,
            "status": status,
        },
        headers=ADMIN_HEADERS,
    )
    r.raise_for_status()
    return r.json()


def scenario_admin_users_group_info_and_group_name_filters(ctx: Dict[str, Any]) -> bool:
    """
    验证：
    1）列表返回的用户对象中包含 group_ids/group_names 字段且类型正确；
    2）有 active 成员关系的用户能正确聚合所属小组 ID/名称；
    3）status!=active 的成员关系不会出现在聚合结果中；
    4）按 group_name 过滤时，能返回正确用户集合；不存在的小组名返回空结果；
    5）按 group_id 精确过滤时，只返回该群中 active 成员对应的用户。
    """
    ok = True

    users = ctx["users"]
    if len(users) < 3:
        return _log(False, "场景前置：ctx['users'] 数量不足 3 个", ctx)

    user0 = users[0]
    user1 = users[1]
    user2 = users[2]

    # 准备两个小组
    group1_name = f"用户管理测试群-Alpha-{uuid.uuid4().hex[:4]}"
    group2_name = f"用户管理测试群-Beta-{uuid.uuid4().hex[:4]}"

    try:
        g1 = _create_admin_group(group1_name)
        g2 = _create_admin_group(group2_name)
    except requests.HTTPError as exc:  # noqa: BLE001
        return _log(False, "admin 创建测试群组失败", str(exc))

    g1_id = g1["id"]
    g2_id = g2["id"]

    # 为 user0 创建两个 active 成员关系：g1 + g2
    # 为 user1 创建一个 active 成员关系：g1
    # 为 user1 在 g2 创建一个非 active 成员关系（left），用于验证不会出现在聚合中
    try:
        _create_admin_membership(g1_id, user0["id"], status="active")
        _create_admin_membership(g2_id, user0["id"], status="active")
        _create_admin_membership(g1_id, user1["id"], status="active")
        _create_admin_membership(g2_id, user1["id"], status="left")
    except requests.HTTPError as exc:  # noqa: BLE001
        return _log(False, "admin 创建测试成员关系失败", str(exc))

    # 1）基础列表中应返回 group_ids/group_names，并且聚合结果符合预期（用 email 过滤出准备阶段用户）
    r_list = requests.get(
        f"{BASE_URL}/api/admin/users",
        params={"page": 1, "page_size": 50, "email": "admin_test_"},
        headers=ADMIN_HEADERS,
    )
    if r_list.status_code != 200:
        return _log(
            False,
            "admin 列出用户（带小组信息）失败（期望 200）",
            {"status_code": r_list.status_code, "body": r_list.text},
        )
    data_list = r_list.json()

    def _find_user_item(user_id: str) -> Dict[str, Any] | None:
        for item in data_list.get("items", []):
            if item.get("id") == user_id:
                return item
        return None

    item0 = _find_user_item(user0["id"])
    item1 = _find_user_item(user1["id"])
    item2 = _find_user_item(user2["id"])

    if not (item0 and item1 and item2):
        return _log(
            False,
            "admin 用户列表中未找到准备阶段创建的用户",
            data_list,
        )

    # 字段存在且为 list
    for it, label in [(item0, "user0"), (item1, "user1"), (item2, "user2")]:
        if not isinstance(it.get("group_ids"), list) or not isinstance(it.get("group_names"), list):
            return _log(False, f"{label} 缺少 group_ids/group_names 字段或类型错误", it)

    # user0：应包含 g1/g2；user1：只包含 g1；user2：没有任何小组
    ok &= g1_id in item0["group_ids"] and group1_name in item0["group_names"]
    ok &= g2_id in item0["group_ids"] and group2_name in item0["group_names"]

    ok &= g1_id in item1["group_ids"] and group1_name in item1["group_names"]
    ok &= g2_id not in item1["group_ids"] and group2_name not in item1["group_names"]

    ok &= item2["group_ids"] == [] and item2["group_names"] == []

    ok &= _log(ok, "admin 用户列表返回 group_ids/group_names 聚合结果场景", data_list)

    # 2）按 group_name=group1_name 过滤，预期 user0/user1 都在结果中
    r_g1 = requests.get(
        f"{BASE_URL}/api/admin/users",
        params={"page": 1, "page_size": 50, "group_name": group1_name},
        headers=ADMIN_HEADERS,
    )
    if r_g1.status_code != 200:
        return _log(
            False,
            "admin 按 group_name=group1 过滤用户失败（期望 200）",
            {"status_code": r_g1.status_code, "body": r_g1.text},
        )
    data_g1 = r_g1.json()
    ids_g1 = {item["id"] for item in data_g1.get("items", [])}
    ok &= _log(
        user0["id"] in ids_g1 and user1["id"] in ids_g1,
        "admin 按 group_name=group1 过滤用户场景",
        data_g1,
    )

    # 3）按 group_name=group2_name 过滤，预期只有 user0 在结果中（user1 在 g2 仅有 left 成员关系）
    r_g2 = requests.get(
        f"{BASE_URL}/api/admin/users",
        params={"page": 1, "page_size": 50, "group_name": group2_name},
        headers=ADMIN_HEADERS,
    )
    if r_g2.status_code != 200:
        return _log(
            False,
            "admin 按 group_name=group2 过滤用户失败（期望 200）",
            {"status_code": r_g2.status_code, "body": r_g2.text},
        )
    data_g2 = r_g2.json()
    ids_g2 = {item["id"] for item in data_g2.get("items", [])}
    ok &= _log(
        user0["id"] in ids_g2 and user1["id"] not in ids_g2,
        "admin 按 group_name=group2 过滤用户（仅包含 active 成员）场景",
        data_g2,
    )

    # 4）使用一个不存在的小组名称过滤，预期不返回上述三个用户
    bad_keyword = f"不存在小组_{uuid.uuid4().hex[:8]}"
    r_bad = requests.get(
        f"{BASE_URL}/api/admin/users",
        params={"page": 1, "page_size": 10, "group_name": bad_keyword},
        headers=ADMIN_HEADERS,
    )
    if r_bad.status_code != 200:
        return _log(
            False,
            "admin 按不存在的小组名称过滤用户失败（期望 200）",
            {"status_code": r_bad.status_code, "body": r_bad.text},
        )
    data_bad = r_bad.json()
    bad_ids = {item["id"] for item in data_bad.get("items", [])}
    ok &= _log(
        user0["id"] not in bad_ids and user1["id"] not in bad_ids and user2["id"] not in bad_ids,
        "admin 按不存在的小组名称过滤用户返回空结果（或不包含目标用户）场景",
        data_bad,
    )

    # 5）按 group_id 精确过滤
    # 5.1 group_id=g1_id：预期 user0/user1 都在结果中，user2 不在
    r_gid1 = requests.get(
        f"{BASE_URL}/api/admin/users",
        params={"page": 1, "page_size": 50, "group_id": g1_id},
        headers=ADMIN_HEADERS,
    )
    if r_gid1.status_code != 200:
        return _log(
            False,
            "admin 按 group_id=g1 过滤用户失败（期望 200）",
            {"status_code": r_gid1.status_code, "body": r_gid1.text},
        )
    data_gid1 = r_gid1.json()
    ids_gid1 = {item["id"] for item in data_gid1.get("items", [])}
    ok &= _log(
        user0["id"] in ids_gid1 and user1["id"] in ids_gid1 and user2["id"] not in ids_gid1,
        "admin 按 group_id=g1 过滤用户（返回该群 active 成员）场景",
        data_gid1,
    )

    # 5.2 group_id=g2_id：预期只有 user0 在结果中（user1 在 g2 只有 left 关系）
    r_gid2 = requests.get(
        f"{BASE_URL}/api/admin/users",
        params={"page": 1, "page_size": 50, "group_id": g2_id},
        headers=ADMIN_HEADERS,
    )
    if r_gid2.status_code != 200:
        return _log(
            False,
            "admin 按 group_id=g2 过滤用户失败（期望 200）",
            {"status_code": r_gid2.status_code, "body": r_gid2.text},
        )
    data_gid2 = r_gid2.json()
    ids_gid2 = {item["id"] for item in data_gid2.get("items", [])}
    ok &= _log(
        user0["id"] in ids_gid2 and user1["id"] not in ids_gid2 and user2["id"] not in ids_gid2,
        "admin 按 group_id=g2 过滤用户（仅包含 active 成员）场景",
        data_gid2,
    )

    # 5.3 使用一个不存在的 group_id 过滤，预期不返回上述三个用户
    non_exist_gid = f"g_non_exist_{uuid.uuid4().hex[:8]}"
    r_gid_bad = requests.get(
        f"{BASE_URL}/api/admin/users",
        params={"page": 1, "page_size": 10, "group_id": non_exist_gid},
        headers=ADMIN_HEADERS,
    )
    if r_gid_bad.status_code != 200:
        return _log(
            False,
            "admin 按不存在的 group_id 过滤用户失败（期望 200）",
            {"status_code": r_gid_bad.status_code, "body": r_gid_bad.text},
        )
    data_gid_bad = r_gid_bad.json()
    ids_gid_bad = {item["id"] for item in data_gid_bad.get("items", [])}
    ok &= _log(
        user0["id"] not in ids_gid_bad and user1["id"] not in ids_gid_bad and user2["id"] not in ids_gid_bad,
        "admin 按不存在的 group_id 过滤用户返回空结果（或不包含目标用户）场景",
        data_gid_bad,
    )

    return ok


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


# ---------- 场景：批量删除用户 ----------


def scenario_admin_batch_delete_users_success() -> bool:
    u1 = register_dummy_user("BatchDel1")
    u2 = register_dummy_user("BatchDel2")
    ids = [u1["id"], u2["id"]]

    r = requests.post(
        f"{BASE_URL}/api/admin/users/batch-delete",
        json={"ids": ids},
        headers=ADMIN_HEADERS,
    )
    if r.status_code != 200:
        return _log(False, "admin 批量删除用户失败（期望 200）", {"status_code": r.status_code, "body": r.text})
    data = r.json()
    if data.get("deleted") != 2:
        return _log(False, "admin 批量删除用户应返回 deleted=2", data)

    for uid in ids:
        r2 = requests.get(f"{BASE_URL}/api/admin/users/{uid}", headers=ADMIN_HEADERS)
        if r2.status_code != 404:
            return _log(False, f"批量删除后用户 {uid} 应 404", {"status_code": r2.status_code})
    return _log(True, "admin 批量删除用户成功场景")


def scenario_admin_batch_delete_users_empty_ids() -> bool:
    r = requests.post(
        f"{BASE_URL}/api/admin/users/batch-delete",
        json={"ids": []},
        headers=ADMIN_HEADERS,
    )
    ok = r.status_code == 422
    return _log(ok, "admin 批量删除用户 ids 为空返回 422 场景", {"status_code": r.status_code, "body": r.text})


def scenario_admin_batch_delete_users_partial() -> bool:
    u = register_dummy_user("BatchDelPartial")
    r = requests.post(
        f"{BASE_URL}/api/admin/users/batch-delete",
        json={"ids": [u["id"], "non-existent-uuid-1111"]},
        headers=ADMIN_HEADERS,
    )
    if r.status_code != 200:
        return _log(False, "admin 批量删除用户（含不存在的 id）应返回 200", {"status_code": r.status_code, "body": r.text})
    data = r.json()
    if data.get("deleted") != 1:
        return _log(False, "admin 批量删除仅删除存在的 1 条", data)
    return _log(True, "admin 批量删除用户部分存在部分不存在场景")


def scenario_admin_batch_delete_users_too_many() -> bool:
    """单次超过 100 条 ids 应返回 422。"""
    r = requests.post(
        f"{BASE_URL}/api/admin/users/batch-delete",
        json={"ids": [f"id-{i}" for i in range(101)]},
        headers=ADMIN_HEADERS,
    )
    ok = r.status_code == 422
    return _log(ok, "admin 批量删除用户 ids 超过 100 返回 422 场景", {"status_code": r.status_code, "body": r.text})


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


def run_all() -> bool:
    print("=== 开始 Admin Users 后台接口测试 ===")
    ctx: Dict[str, Any] = {}

    ok = True
    ok &= setup_users(ctx)
    ok &= scenario_admin_list_users_basic(ctx)
    ok &= scenario_admin_users_group_info_and_group_name_filters(ctx)
    ok &= scenario_admin_list_users_with_filters(ctx)
    ok &= scenario_admin_get_user_detail(ctx)
    ok &= scenario_admin_get_user_not_found()
    ok &= scenario_admin_update_user_success(ctx)
    ok &= scenario_admin_update_user_no_fields(ctx)
    ok &= scenario_admin_delete_user_success()
    ok &= scenario_admin_delete_user_not_found()
    ok &= scenario_admin_batch_delete_users_success()
    ok &= scenario_admin_batch_delete_users_empty_ids()
    ok &= scenario_admin_batch_delete_users_partial()
    ok &= scenario_admin_batch_delete_users_too_many()
    ok &= scenario_admin_missing_or_wrong_token()

    print("\n=== Admin Users 测试结果: {} ===".format("全部通过 ✅" if ok else "有失败 ❌"))
    return ok


if __name__ == "__main__":
    import sys
    sys.exit(0 if run_all() else 1)

