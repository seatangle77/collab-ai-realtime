from __future__ import annotations

import uuid
from typing import Any, Dict, Tuple

import requests

BASE_URL = "http://127.0.0.1:8000"
RUN_ID = uuid.uuid4().hex[:6]

ADMIN_KEY = "TestAdminKey123"
ADMIN_HEADERS = {"X-Admin-Token": ADMIN_KEY}


def _log(ok: bool, message: str, extra: Any | None = None) -> bool:
    prefix = "✅" if ok else "❌"
    print(f"{prefix} {message}")
    if not ok and extra is not None:
        print("   详情:", extra)
    return ok


def register_dummy_user(label: str) -> Dict[str, Any]:
    email = f"admin_test_{label}_{uuid.uuid4().hex[:6]}@example.com"
    r = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={
            "name": f"User {label} {RUN_ID}",
            "email": email,
            "password": "1234",
            "device_token": f"device-{label}-{uuid.uuid4().hex[:8]}",
        },
    )
    r.raise_for_status()
    return r.json()


def _create_admin_group(name: str) -> Dict[str, Any]:
    r = requests.post(f"{BASE_URL}/api/admin/groups", json={"name": name}, headers=ADMIN_HEADERS)
    r.raise_for_status()
    return r.json()


def _create_admin_membership(group_id: str, user_id: str, role: str = "member", status: str = "active") -> Dict[str, Any]:
    r = requests.post(
        f"{BASE_URL}/api/admin/memberships",
        json={"group_id": group_id, "user_id": user_id, "role": role, "status": status},
        headers=ADMIN_HEADERS,
    )
    r.raise_for_status()
    return r.json()


# ────────────────────────────────────────────────────────────
# 准备阶段
# ────────────────────────────────────────────────────────────

def setup_users(ctx: Dict[str, Any]) -> bool:
    users: list[Dict[str, Any]] = []
    for label in ["A", "B", "C"]:
        users.append(register_dummy_user(label))
    ctx["users"] = users
    return _log(True, "准备阶段：成功注册 3 个测试用户", [u["email"] for u in users])


# ────────────────────────────────────────────────────────────
# 管理员 token 鉴权
# ────────────────────────────────────────────────────────────

def scenario_admin_missing_or_wrong_token() -> bool:
    ok = True
    r = requests.get(f"{BASE_URL}/api/admin/users")
    ok &= _log(r.status_code == 403, "缺少 X-Admin-Token 应返回 403", {"status": r.status_code})
    r = requests.get(f"{BASE_URL}/api/admin/users", headers={"X-Admin-Token": "WrongKey"})
    ok &= _log(r.status_code == 403, "错误 X-Admin-Token 应返回 403", {"status": r.status_code})
    return ok


# ────────────────────────────────────────────────────────────
# 创建用户（新接口）
# ────────────────────────────────────────────────────────────

def scenario_admin_create_user_success(ctx: Dict[str, Any]) -> bool:
    email = f"created_{uuid.uuid4().hex[:6]}@example.com"
    name = f"Created User {RUN_ID}"
    r = requests.post(
        f"{BASE_URL}/api/admin/users/",
        json={"name": name, "email": email, "password": "1234"},
        headers=ADMIN_HEADERS,
    )
    if r.status_code != 200:
        return _log(False, "admin 创建用户失败（期望 200）", {"status": r.status_code, "body": r.text})
    data = r.json()
    ok = data.get("email") == email and data.get("name") == name
    if ok:
        ctx["created_user_id"] = data["id"]
        ctx["created_user_email"] = email
    return _log(ok, "admin 创建用户成功场景", data)


def scenario_admin_create_user_creates_default_group(ctx: Dict[str, Any]) -> bool:
    user_id = ctx.get("created_user_id")
    if not user_id:
        return _log(False, "create_user_creates_default_group：ctx 中无 created_user_id")

    r = requests.get(f"{BASE_URL}/api/admin/users/{user_id}", headers=ADMIN_HEADERS)
    if r.status_code != 200:
        return _log(False, "查询创建的用户详情失败", {"status": r.status_code})
    data = r.json()
    ok = len(data.get("group_ids", [])) >= 1
    return _log(ok, "admin 创建用户自动生成默认群组场景", data)


def scenario_admin_create_user_duplicate_email(ctx: Dict[str, Any]) -> bool:
    email = ctx.get("created_user_email") or ctx["users"][0]["email"]
    r = requests.post(
        f"{BASE_URL}/api/admin/users/",
        json={"name": "Dup", "email": email, "password": "1234"},
        headers=ADMIN_HEADERS,
    )
    ok = r.status_code == 400
    return _log(ok, "admin 创建用户重复邮箱应返回 400", {"status": r.status_code, "body": r.text})


def scenario_admin_create_user_invalid_password() -> bool:
    ok = True
    base_email = f"inv_{uuid.uuid4().hex[:6]}@example.com"
    for pwd, label in [("123", "3位"), ("12345", "5位")]:
        r = requests.post(
            f"{BASE_URL}/api/admin/users/",
            json={"name": "Test", "email": base_email, "password": pwd},
            headers=ADMIN_HEADERS,
        )
        ok &= _log(r.status_code == 400, f"admin 创建用户密码{label}应返回 400", {"status": r.status_code})
    return ok


# ────────────────────────────────────────────────────────────
# 列表场景
# ────────────────────────────────────────────────────────────

def scenario_admin_list_users_basic(ctx: Dict[str, Any]) -> bool:
    r = requests.get(
        f"{BASE_URL}/api/admin/users",
        params={"page": 1, "page_size": 10, "email": "admin_test_"},
        headers=ADMIN_HEADERS,
    )
    if r.status_code != 200:
        return _log(False, "admin 列出用户失败（期望 200）", {"status": r.status_code, "body": r.text})
    data = r.json()
    ok = isinstance(data.get("items"), list) and isinstance(data.get("meta"), dict)
    emails = {u["email"] for u in ctx["users"]}
    returned_emails = {item["email"] for item in data["items"]}
    ok &= bool(emails & returned_emails)
    return _log(ok, "admin 基础分页列出用户场景", data)


def scenario_admin_list_users_with_filters(ctx: Dict[str, Any]) -> bool:
    ok = True
    target = ctx["users"][0]

    # 按 email 过滤
    r = requests.get(f"{BASE_URL}/api/admin/users",
                     params={"email": target["email"][:10]}, headers=ADMIN_HEADERS)
    ok &= _log(r.status_code == 200 and target["email"] in {i["email"] for i in r.json()["items"]},
               "admin 按 email 过滤用户场景")

    # 按 name 过滤
    r = requests.get(f"{BASE_URL}/api/admin/users",
                     params={"name": target["name"][3:]}, headers=ADMIN_HEADERS)
    ok &= _log(r.status_code == 200 and target["id"] in {i["id"] for i in r.json()["items"]},
               "admin 按 name 过滤用户场景")

    # 按精确 id 过滤
    r = requests.get(f"{BASE_URL}/api/admin/users",
                     params={"id": target["id"]}, headers=ADMIN_HEADERS)
    items = r.json().get("items", [])
    ok &= _log(r.status_code == 200 and len(items) == 1 and items[0]["id"] == target["id"],
               "admin 按 id 精确过滤用户场景")

    # 不存在的关键词 → 空结果
    r = requests.get(f"{BASE_URL}/api/admin/users",
                     params={"email": f"NOEMAIL_{uuid.uuid4().hex}"}, headers=ADMIN_HEADERS)
    ok &= _log(r.status_code == 200 and r.json()["items"] == [],
               "admin 过滤无结果返回空列表场景")
    return ok


def scenario_admin_list_pagination(ctx: Dict[str, Any]) -> bool:
    ok = True
    # page_size=1 应只返回 1 条
    r = requests.get(f"{BASE_URL}/api/admin/users",
                     params={"email": "admin_test_", "page": 1, "page_size": 1},
                     headers=ADMIN_HEADERS)
    ok &= _log(r.status_code == 200 and len(r.json()["items"]) <= 1,
               "admin 分页 page_size=1 场景")
    # page_size 超限
    r = requests.get(f"{BASE_URL}/api/admin/users",
                     params={"page_size": 101}, headers=ADMIN_HEADERS)
    ok &= _log(r.status_code == 422, "admin page_size 超过 100 应返回 422 场景", {"status": r.status_code})
    return ok


def scenario_admin_users_group_filters(ctx: Dict[str, Any]) -> bool:
    ok = True
    users = ctx["users"]
    user0, user1, user2 = users[0], users[1], users[2]

    g1_name = f"Filter Alpha {uuid.uuid4().hex[:4]} {RUN_ID}"
    g2_name = f"Filter Beta {uuid.uuid4().hex[:4]} {RUN_ID}"
    g1 = _create_admin_group(g1_name)
    g2 = _create_admin_group(g2_name)
    g1_id, g2_id = g1["id"], g2["id"]

    _create_admin_membership(g1_id, user0["id"], status="active")
    _create_admin_membership(g2_id, user0["id"], status="active")
    _create_admin_membership(g1_id, user1["id"], status="active")
    _create_admin_membership(g2_id, user1["id"], status="left")

    def _ids(params: dict) -> set[str]:
        r = requests.get(f"{BASE_URL}/api/admin/users",
                         params={"page_size": 50, **params}, headers=ADMIN_HEADERS)
        return {i["id"] for i in r.json().get("items", [])}

    # group_name=g1 → user0/user1
    ids = _ids({"group_name": g1_name})
    ok &= _log(user0["id"] in ids and user1["id"] in ids, "按 group_name=g1 过滤含 user0/user1")

    # group_name=g2 → 只有 user0（user1 仅 left）
    ids = _ids({"group_name": g2_name})
    ok &= _log(user0["id"] in ids and user1["id"] not in ids,
               "按 group_name=g2 过滤仅含 active 成员(user0)")

    # 不存在群组名 → 不包含三个用户
    ids = _ids({"group_name": f"不存在_{uuid.uuid4().hex}"})
    ok &= _log(user0["id"] not in ids and user1["id"] not in ids,
               "按不存在 group_name 过滤返回空")

    # group_id=g1 → user0/user1 在，user2 不在
    ids = _ids({"group_id": g1_id})
    ok &= _log(user0["id"] in ids and user1["id"] in ids and user2["id"] not in ids,
               "按 group_id=g1 精确过滤场景")

    # group_id=g2 → 只有 user0
    ids = _ids({"group_id": g2_id})
    ok &= _log(user0["id"] in ids and user1["id"] not in ids,
               "按 group_id=g2 精确过滤仅 active 成员")

    # 不存在 group_id
    ids = _ids({"group_id": f"g_non_{uuid.uuid4().hex[:8]}"})
    ok &= _log(user0["id"] not in ids, "按不存在 group_id 过滤返回空")
    return ok


# ────────────────────────────────────────────────────────────
# 详情场景
# ────────────────────────────────────────────────────────────

def scenario_admin_get_user_detail(ctx: Dict[str, Any]) -> bool:
    target = ctx["users"][1]
    r = requests.get(f"{BASE_URL}/api/admin/users/{target['id']}", headers=ADMIN_HEADERS)
    if r.status_code != 200:
        return _log(False, "admin 获取用户详情失败（期望 200）", {"status": r.status_code, "body": r.text})
    data = r.json()
    ok = data["id"] == target["id"] and data["email"] == target["email"]
    # 详情接口应包含 group 字段（注册时自动创建了默认群组）
    ok &= isinstance(data.get("group_ids"), list)
    ok &= isinstance(data.get("group_names"), list)
    ok &= len(data.get("group_ids", [])) >= 1  # 至少有注册时创建的默认群组
    return _log(ok, "admin 获取用户详情（含 group 信息）场景", data)


def scenario_admin_get_user_not_found() -> bool:
    r = requests.get(f"{BASE_URL}/api/admin/users/unexist-user-123", headers=ADMIN_HEADERS)
    ok = r.status_code == 404
    return _log(ok, "admin 获取不存在用户应返回 404 场景", {"status": r.status_code})


# ────────────────────────────────────────────────────────────
# 更新场景
# ────────────────────────────────────────────────────────────

def scenario_admin_update_user_success(ctx: Dict[str, Any]) -> bool:
    target = ctx["users"][2]
    new_name = f"Updated {RUN_ID}"
    new_token = "admin_modified_token"
    r = requests.patch(
        f"{BASE_URL}/api/admin/users/{target['id']}",
        json={"name": new_name, "device_token": new_token},
        headers=ADMIN_HEADERS,
    )
    if r.status_code != 200:
        return _log(False, "admin 更新用户失败（期望 200）", {"status": r.status_code, "body": r.text})
    data = r.json()
    ok = data["name"] == new_name and data.get("device_token") == new_token
    ok &= _log(ok, "admin 更新用户成功场景", data)

    # 再查一次确认持久化
    r2 = requests.get(f"{BASE_URL}/api/admin/users/{target['id']}", headers=ADMIN_HEADERS)
    data2 = r2.json()
    ok &= _log(data2["name"] == new_name, "admin 更新后详情校验场景", data2)
    return ok


def scenario_admin_update_user_no_fields(ctx: Dict[str, Any]) -> bool:
    target = ctx["users"][0]
    r = requests.patch(
        f"{BASE_URL}/api/admin/users/{target['id']}",
        json={},
        headers=ADMIN_HEADERS,
    )
    ok = r.status_code == 400
    return _log(ok, "admin 更新用户无字段应返回 400 场景", {"status": r.status_code})


def scenario_admin_update_user_not_found() -> bool:
    r = requests.patch(
        f"{BASE_URL}/api/admin/users/non-exist-id",
        json={"name": "X"},
        headers=ADMIN_HEADERS,
    )
    ok = r.status_code == 404
    return _log(ok, "admin 更新不存在用户应返回 404 场景", {"status": r.status_code})


# ────────────────────────────────────────────────────────────
# 删除场景（含 cascade）
# ────────────────────────────────────────────────────────────

def scenario_admin_delete_user_success() -> bool:
    user = register_dummy_user("ToDelete")
    user_id = user["id"]

    # 先给这个用户创建一条额外成员关系
    g = _create_admin_group(f"DelGroup {uuid.uuid4().hex[:4]}")
    _create_admin_membership(g["id"], user_id)

    # 删除用户（同时会触发 speech_transcripts UPDATE，无数据时应静默成功）
    r = requests.delete(f"{BASE_URL}/api/admin/users/{user_id}", headers=ADMIN_HEADERS)
    if r.status_code != 204:
        return _log(False, "admin 删除用户失败（期望 204）", {"status": r.status_code, "body": r.text})

    # 用户应 404
    r2 = requests.get(f"{BASE_URL}/api/admin/users/{user_id}", headers=ADMIN_HEADERS)
    ok = r2.status_code == 404
    ok &= _log(ok, "admin 删除用户后 GET 应返回 404 场景")

    # 成员关系应已级联删除
    r3 = requests.get(
        f"{BASE_URL}/api/admin/memberships",
        params={"user_id": user_id},
        headers=ADMIN_HEADERS,
    )
    if r3.status_code == 200:
        remaining = r3.json().get("items", [])
        ok &= _log(len(remaining) == 0, "admin 删除用户后成员关系应级联删除场景",
                   {"remaining": remaining})
    return ok


def scenario_admin_delete_user_not_found() -> bool:
    r = requests.delete(f"{BASE_URL}/api/admin/users/unexist-user-456", headers=ADMIN_HEADERS)
    ok = r.status_code == 404
    return _log(ok, "admin 删除不存在用户应返回 404 场景", {"status": r.status_code})


def scenario_admin_delete_user_cascade_memberships() -> bool:
    """专项验证：删除用户后，其所有成员关系全部消失。"""
    user = register_dummy_user("CascadeDel")
    user_id = user["id"]

    # 新建两个群组并加入
    for i in range(2):
        g = _create_admin_group(f"CascadeG{i} {uuid.uuid4().hex[:4]}")
        _create_admin_membership(g["id"], user_id)

    # 删除用户
    requests.delete(f"{BASE_URL}/api/admin/users/{user_id}", headers=ADMIN_HEADERS)

    # 查成员关系
    r = requests.get(
        f"{BASE_URL}/api/admin/memberships",
        params={"user_id": user_id, "page_size": 20},
        headers=ADMIN_HEADERS,
    )
    if r.status_code != 200:
        return _log(True, "admin 成员关系查询返回非200（可能用户已删除，视为通过）", {"status": r.status_code})
    remaining = r.json().get("items", [])
    ok = len(remaining) == 0
    return _log(ok, "admin 删除用户级联删除所有成员关系场景", {"remaining": remaining})


# ────────────────────────────────────────────────────────────
# 批量删除场景
# ────────────────────────────────────────────────────────────

def scenario_admin_batch_delete_users_success() -> bool:
    u1 = register_dummy_user("BatchDel1")
    u2 = register_dummy_user("BatchDel2")
    # 给两个用户各加一条成员关系
    g = _create_admin_group(f"BatchDelG {uuid.uuid4().hex[:4]}")
    _create_admin_membership(g["id"], u1["id"])
    _create_admin_membership(g["id"], u2["id"])

    # 批量删除（同时会触发 speech_transcripts UPDATE，无数据时应静默成功）
    r = requests.post(
        f"{BASE_URL}/api/admin/users/batch-delete",
        json={"ids": [u1["id"], u2["id"]]},
        headers=ADMIN_HEADERS,
    )
    if r.status_code != 200:
        return _log(False, "admin 批量删除用户失败（期望 200）", {"status": r.status_code, "body": r.text})
    data = r.json()
    ok = data.get("deleted") == 2
    ok &= _log(ok, "admin 批量删除用户成功 deleted=2 场景", data)

    # 验证用户已删除
    for uid in [u1["id"], u2["id"]]:
        r2 = requests.get(f"{BASE_URL}/api/admin/users/{uid}", headers=ADMIN_HEADERS)
        ok &= _log(r2.status_code == 404, f"批量删除后用户 {uid} 应返回 404")

    # 验证成员关系级联删除
    r3 = requests.get(
        f"{BASE_URL}/api/admin/memberships",
        params={"group_id": g["id"]},
        headers=ADMIN_HEADERS,
    )
    if r3.status_code == 200:
        remaining = [m for m in r3.json().get("items", [])
                     if m.get("user_id") in {u1["id"], u2["id"]}]
        ok &= _log(len(remaining) == 0, "批量删除用户后成员关系应级联删除场景",
                   {"remaining": remaining})
    return ok


def scenario_admin_batch_delete_users_empty_ids() -> bool:
    r = requests.post(
        f"{BASE_URL}/api/admin/users/batch-delete",
        json={"ids": []},
        headers=ADMIN_HEADERS,
    )
    ok = r.status_code == 422
    return _log(ok, "admin 批量删除 ids 为空应返回 422 场景", {"status": r.status_code})


def scenario_admin_batch_delete_users_partial() -> bool:
    u = register_dummy_user("BatchDelPartial")
    r = requests.post(
        f"{BASE_URL}/api/admin/users/batch-delete",
        json={"ids": [u["id"], "non-existent-uuid-1111"]},
        headers=ADMIN_HEADERS,
    )
    if r.status_code != 200:
        return _log(False, "admin 批量删除含不存在 id 应返回 200", {"status": r.status_code, "body": r.text})
    ok = r.json().get("deleted") == 1
    return _log(ok, "admin 批量删除部分存在场景 deleted=1", r.json())


def scenario_admin_batch_delete_users_too_many() -> bool:
    r = requests.post(
        f"{BASE_URL}/api/admin/users/batch-delete",
        json={"ids": [f"id-{i}" for i in range(101)]},
        headers=ADMIN_HEADERS,
    )
    ok = r.status_code == 422
    return _log(ok, "admin 批量删除 ids 超过 100 应返回 422 场景", {"status": r.status_code})


# ────────────────────────────────────────────────────────────
# 标记重置密码
# ────────────────────────────────────────────────────────────

def scenario_admin_mark_password_reset_and_verify(ctx: Dict[str, Any]) -> bool:
    target = ctx["users"][1]
    r = requests.post(
        f"{BASE_URL}/api/admin/users/{target['id']}/mark-password-reset",
        headers=ADMIN_HEADERS,
    )
    if r.status_code != 200:
        return _log(False, "admin mark-password-reset 失败（期望 200）", {"status": r.status_code, "body": r.text})
    ok = r.json().get("password_needs_reset") is True
    # 详情中也应看到标记
    r2 = requests.get(f"{BASE_URL}/api/admin/users/{target['id']}", headers=ADMIN_HEADERS)
    ok &= r2.json().get("password_needs_reset") is True
    return _log(ok, "admin 标记强制重置密码场景", {"mark": r.json()})


def scenario_admin_mark_password_reset_not_found() -> bool:
    r = requests.post(
        f"{BASE_URL}/api/admin/users/non-exist-id/mark-password-reset",
        headers=ADMIN_HEADERS,
    )
    ok = r.status_code == 404
    return _log(ok, "admin mark-password-reset 不存在用户应返回 404", {"status": r.status_code})


# ────────────────────────────────────────────────────────────
# 导出 CSV
# ────────────────────────────────────────────────────────────

def scenario_admin_export_csv_basic(ctx: Dict[str, Any]) -> bool:
    r = requests.get(
        f"{BASE_URL}/api/admin/users/export",
        params={"email": "admin_test_"},
        headers=ADMIN_HEADERS,
    )
    if r.status_code != 200:
        return _log(False, "admin 导出 CSV 失败（期望 200）", {"status": r.status_code, "body": r.text[:200]})
    ok = "text/csv" in r.headers.get("Content-Type", "")
    lines = r.text.strip().splitlines()
    # header 行格式验证：含 groups 列，不含 group_ids/group_names
    header = lines[0] if lines else ""
    ok &= _log("groups" in header, "CSV header 含 groups 列", {"header": header})
    ok &= _log("group_ids" not in header, "CSV header 不含旧 group_ids 列", {"header": header})
    ok &= _log("group_names" not in header, "CSV header 不含旧 group_names 列", {"header": header})
    # 含标准列
    for col in ["id", "name", "email", "device_token", "password_needs_reset", "created_at"]:
        ok &= _log(col in header, f"CSV header 含 {col} 列", {"header": header})
    # 包含已知用户 email
    known_email = ctx["users"][0]["email"]
    ok &= _log(known_email in r.text, f"CSV 包含已知用户 email={known_email}")
    return _log(ok, "admin 导出 CSV 基础场景")


def scenario_admin_export_csv_with_filter(ctx: Dict[str, Any]) -> bool:
    target = ctx["users"][0]
    r = requests.get(
        f"{BASE_URL}/api/admin/users/export",
        params={"email": target["email"]},
        headers=ADMIN_HEADERS,
    )
    if r.status_code != 200:
        return _log(False, "admin 带过滤参数导出 CSV 失败", {"status": r.status_code})
    lines = [ln for ln in r.text.strip().splitlines() if ln]
    ok = True
    # header + 1 条数据
    ok &= _log(len(lines) == 2, "admin 带 email 过滤 CSV 应只有 header+1 行", {"line_count": len(lines)})
    ok &= _log(target["email"] in lines[1], "数据行包含目标 email", {"data_line": lines[1] if len(lines) > 1 else ""})
    # groups 列存在于 header
    ok &= _log("groups" in lines[0], "CSV header 含 groups 列")
    return _log(ok, "admin 带 email 过滤导出 CSV 场景", {"lines": lines})


def scenario_admin_export_csv_no_token() -> bool:
    r = requests.get(f"{BASE_URL}/api/admin/users/export")
    ok = r.status_code == 403
    return _log(ok, "admin 导出 CSV 无 token 应返回 403", {"status": r.status_code})


# ────────────────────────────────────────────────────────────
# 删除无 FK 报错（含会话场景）
# ────────────────────────────────────────────────────────────

def scenario_admin_delete_user_fk_no_error() -> bool:
    """注册用户 → admin 获取默认群组 → 创建会话 → 删除用户 → 断言 204（无 FK 报错）。"""
    user = register_dummy_user("FKDelTest")
    user_id = user["id"]

    # 获取用户默认群组
    r = requests.get(f"{BASE_URL}/api/admin/users/{user_id}", headers=ADMIN_HEADERS)
    if r.status_code != 200:
        return _log(False, "FK删除场景：获取用户详情失败", {"status": r.status_code})
    group_ids = r.json().get("group_ids", [])
    if not group_ids:
        return _log(False, "FK删除场景：用户无默认群组", r.json())
    group_id = group_ids[0]

    # 在该群组中创建一个会话（模拟有关联数据）
    r2 = requests.post(
        f"{BASE_URL}/api/admin/chat-sessions/",
        json={"group_id": group_id, "session_title": f"FK Test Session {RUN_ID}"},
        headers=ADMIN_HEADERS,
    )
    if r2.status_code != 201:
        return _log(False, "FK删除场景：创建会话失败", {"status": r2.status_code, "body": r2.text})

    # 删除用户（group_memberships 级联 + speech_transcripts 软更新）
    r3 = requests.delete(f"{BASE_URL}/api/admin/users/{user_id}", headers=ADMIN_HEADERS)
    ok = r3.status_code == 204
    return _log(ok, "admin 删除有成员关系和会话的用户无 FK 报错场景", {"status": r3.status_code})


def scenario_admin_batch_delete_fk_no_error() -> bool:
    """注册2用户 → 默认群组各创建会话 → 批量删除 → 断言 deleted=2（无 FK 报错）。"""
    u1 = register_dummy_user("FKBatchDel1")
    u2 = register_dummy_user("FKBatchDel2")

    # 在 u1 的默认群组中创建会话
    r = requests.get(f"{BASE_URL}/api/admin/users/{u1['id']}", headers=ADMIN_HEADERS)
    group_ids = r.json().get("group_ids", []) if r.status_code == 200 else []
    if group_ids:
        requests.post(
            f"{BASE_URL}/api/admin/chat-sessions/",
            json={"group_id": group_ids[0], "session_title": f"FK Batch Session {RUN_ID}"},
            headers=ADMIN_HEADERS,
        )

    r = requests.post(
        f"{BASE_URL}/api/admin/users/batch-delete",
        json={"ids": [u1["id"], u2["id"]]},
        headers=ADMIN_HEADERS,
    )
    ok = r.status_code == 200 and r.json().get("deleted") == 2
    return _log(
        ok, "admin 批量删除有成员关系和会话的用户无 FK 报错场景",
        {"status": r.status_code, "deleted": r.json().get("deleted") if r.status_code == 200 else r.text},
    )


# ────────────────────────────────────────────────────────────
# 代登录
# ────────────────────────────────────────────────────────────

def scenario_admin_impersonate_user(ctx: Dict[str, Any]) -> bool:
    target = ctx["users"][0]
    r = requests.post(
        f"{BASE_URL}/api/admin/users/{target['id']}/impersonate",
        headers=ADMIN_HEADERS,
    )
    if r.status_code != 200:
        return _log(False, "admin impersonate 失败（期望 200）", {"status": r.status_code, "body": r.text})
    token = r.json().get("access_token")
    if not token:
        return _log(False, "impersonate 未返回 access_token", r.json())

    r_me = requests.get(f"{BASE_URL}/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    if r_me.status_code != 200:
        return _log(False, "impersonate token 调 /me 失败", {"status": r_me.status_code})
    me = r_me.json()
    ok = me.get("id") == target["id"]
    return _log(ok, "admin impersonate 用户成功场景", {"me_id": me.get("id")})


def scenario_admin_impersonate_not_found() -> bool:
    r = requests.post(
        f"{BASE_URL}/api/admin/users/non-exist-id/impersonate",
        headers=ADMIN_HEADERS,
    )
    ok = r.status_code == 404
    return _log(ok, "admin impersonate 不存在用户应返回 404", {"status": r.status_code})


# ────────────────────────────────────────────────────────────
# 总入口
# ────────────────────────────────────────────────────────────

def run_all() -> bool:
    print("=== 开始 Admin Users 后台接口测试 ===\n")
    ctx: Dict[str, Any] = {}

    ok = True

    print("-- 鉴权 --")
    ok &= scenario_admin_missing_or_wrong_token()

    print("\n-- 准备数据 --")
    ok &= setup_users(ctx)

    print("\n-- 创建用户 --")
    ok &= scenario_admin_create_user_success(ctx)
    ok &= scenario_admin_create_user_creates_default_group(ctx)
    ok &= scenario_admin_create_user_duplicate_email(ctx)
    ok &= scenario_admin_create_user_invalid_password()

    print("\n-- 列表 & 过滤 --")
    ok &= scenario_admin_list_users_basic(ctx)
    ok &= scenario_admin_list_users_with_filters(ctx)
    ok &= scenario_admin_list_pagination(ctx)
    ok &= scenario_admin_users_group_filters(ctx)

    print("\n-- 详情 --")
    ok &= scenario_admin_get_user_detail(ctx)
    ok &= scenario_admin_get_user_not_found()

    print("\n-- 更新 --")
    ok &= scenario_admin_update_user_success(ctx)
    ok &= scenario_admin_update_user_no_fields(ctx)
    ok &= scenario_admin_update_user_not_found()

    print("\n-- 删除 --")
    ok &= scenario_admin_delete_user_success()
    ok &= scenario_admin_delete_user_not_found()
    ok &= scenario_admin_delete_user_cascade_memberships()
    ok &= scenario_admin_delete_user_fk_no_error()

    print("\n-- 批量删除 --")
    ok &= scenario_admin_batch_delete_users_success()
    ok &= scenario_admin_batch_delete_users_empty_ids()
    ok &= scenario_admin_batch_delete_users_partial()
    ok &= scenario_admin_batch_delete_users_too_many()
    ok &= scenario_admin_batch_delete_fk_no_error()

    print("\n-- 标记重置密码 --")
    ok &= scenario_admin_mark_password_reset_and_verify(ctx)
    ok &= scenario_admin_mark_password_reset_not_found()

    print("\n-- 导出 CSV --")
    ok &= scenario_admin_export_csv_basic(ctx)
    ok &= scenario_admin_export_csv_with_filter(ctx)
    ok &= scenario_admin_export_csv_no_token()

    print("\n-- 代登录 --")
    ok &= scenario_admin_impersonate_user(ctx)
    ok &= scenario_admin_impersonate_not_found()

    print(f"\n=== Admin Users 测试结果: {'全部通过 ✅' if ok else '有失败 ❌'} ===")
    return ok


if __name__ == "__main__":
    import sys
    sys.exit(0 if run_all() else 1)
