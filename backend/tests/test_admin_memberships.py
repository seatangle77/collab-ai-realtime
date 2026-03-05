from __future__ import annotations

import uuid
from datetime import datetime, timedelta
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


def register_and_login(label: str) -> Dict[str, Any]:
    """注册并登录一个用户，返回 dict：{ user, access_token }。"""
    email = f"admin_member_{label}_{uuid.uuid4().hex[:6]}@example.com"
    password = "test_password_123"

    r = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={
            "name": f"成员测试用户-{label}",
            "email": email,
            "password": password,
            "device_token": f"device-membership-{label}",
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


def join_group(access_token: str, group_id: str) -> Dict[str, Any]:
    headers = {"Authorization": f"Bearer {access_token}"}
    r = requests.post(
        f"{BASE_URL}/api/groups/{group_id}/join",
        headers=headers,
    )
    r.raise_for_status()
    return r.json()


# ---------- 场景：准备 memberships ----------


def setup_memberships(ctx: Dict[str, Any]) -> bool:
    """
    注册 3 个用户：leader、member1、member2
    leader 创建群，另外两人加入；然后通过 admin 列表接口拿到 3 条 membership 记录。
    """
    info_leader = register_and_login("leader")
    info_member1 = register_and_login("member1")
    info_member2 = register_and_login("member2")

    ctx["leader_user_id"] = info_leader["user"]["id"]
    ctx["member1_user_id"] = info_member1["user"]["id"]
    ctx["member2_user_id"] = info_member2["user"]["id"]

    # leader 创建群
    group_detail = create_group(info_leader["access_token"], name="成员测试群")
    group_id = group_detail["group"]["id"]
    ctx["group_id"] = group_id

    # 成员加入群
    join_group(info_member1["access_token"], group_id)
    join_group(info_member2["access_token"], group_id)

    # 通过 admin 接口列出该群的所有 membership
    r = requests.get(
        f"{BASE_URL}/api/admin/memberships",
        params={"group_id": group_id, "page": 1, "page_size": 20},
        headers=ADMIN_HEADERS,
    )
    if r.status_code != 200:
        return _log(
            False,
            "准备阶段：通过 admin 获取 group_memberships 失败（期望 200）",
            {"status_code": r.status_code, "body": r.text},
        )

    data = r.json()
    memberships: List[Dict[str, Any]] = data["items"]
    ctx["memberships"] = memberships

    # 简单检查至少有 3 条记录
    ok = len(memberships) >= 3
    return _log(ok, "准备阶段：成功创建 3 条成员关系（leader + 2 个成员）", memberships)


# ---------- 场景：管理员分页列出成员关系 ----------


def scenario_admin_list_memberships_basic(ctx: Dict[str, Any]) -> bool:
    r = requests.get(
        f"{BASE_URL}/api/admin/memberships",
        params={"page": 1, "page_size": 10},
        headers=ADMIN_HEADERS,
    )
    if r.status_code != 200:
        return _log(False, "admin 分页列出成员关系失败（期望 200）", {"status_code": r.status_code, "body": r.text})

    data = r.json()
    ok = isinstance(data.get("items"), list) and isinstance(data.get("meta"), dict)

    existing_ids = {m["id"] for m in ctx["memberships"]}
    returned_ids = {item["id"] for item in data["items"]}
    ok = ok and bool(existing_ids & returned_ids)

    return _log(ok, "admin 基础分页列出成员关系场景", data)


# ---------- 场景：管理员按条件过滤成员关系 ----------


def scenario_admin_list_memberships_filters(ctx: Dict[str, Any]) -> bool:
    ok = True

    group_id = ctx["group_id"]
    member1_user_id = ctx["member1_user_id"]

    # 按 group_id 过滤
    r = requests.get(
        f"{BASE_URL}/api/admin/memberships",
        params={"group_id": group_id, "page": 1, "page_size": 20},
        headers=ADMIN_HEADERS,
    )
    if r.status_code != 200:
        return _log(False, "admin 按 group_id 过滤成员关系失败（期望 200）", {"status_code": r.status_code, "body": r.text})
    data = r.json()
    ok &= _log(
        all(item["group_id"] == group_id for item in data["items"]),
        "admin 按 group_id 过滤成员关系场景",
        data,
    )

    # 按 user_id 过滤（member1）
    r2 = requests.get(
        f"{BASE_URL}/api/admin/memberships",
        params={"user_id": member1_user_id, "page": 1, "page_size": 20},
        headers=ADMIN_HEADERS,
    )
    if r2.status_code != 200:
        return _log(False, "admin 按 user_id 过滤成员关系失败（期望 200）", {"status_code": r2.status_code, "body": r2.text})
    data2 = r2.json()
    ok &= _log(
        all(item["user_id"] == member1_user_id for item in data2["items"]) and len(data2["items"]) >= 1,
        "admin 按 user_id 过滤成员关系场景",
        data2,
    )

    # 修改 member2 的 status 为 left，用于 status 过滤测试
    member2_user_id = ctx["member2_user_id"]
    member2_membership = next(
        (m for m in ctx["memberships"] if m["user_id"] == member2_user_id),
        None,
    )
    if not member2_membership:
        return _log(False, "未找到 member2 的 membership 记录", ctx["memberships"])

    m2_id = member2_membership["id"]
    r3 = requests.patch(
        f"{BASE_URL}/api/admin/memberships/{m2_id}",
        json={"status": "left"},
        headers=ADMIN_HEADERS,
    )
    if r3.status_code != 200:
        return _log(False, "admin 将 member2 的 status 改为 left 失败（期望 200）", {"status_code": r3.status_code, "body": r3.text})

    # status=active 列表中不应包含 member2
    r4 = requests.get(
        f"{BASE_URL}/api/admin/memberships",
        params={"status": "active", "group_id": group_id, "page": 1, "page_size": 20},
        headers=ADMIN_HEADERS,
    )
    if r4.status_code != 200:
        return _log(False, "admin 按 status=active 过滤成员关系失败（期望 200）", {"status_code": r4.status_code, "body": r4.text})
    data4 = r4.json()
    active_user_ids = {item["user_id"] for item in data4["items"]}
    ok &= _log(
        member2_user_id not in active_user_ids,
        "admin 按 status=active 过滤成员关系（不包含 left 成员）场景",
        data4,
    )

    # status=left 列表中应包含 member2
    r5 = requests.get(
        f"{BASE_URL}/api/admin/memberships",
        params={"status": "left", "group_id": group_id, "page": 1, "page_size": 20},
        headers=ADMIN_HEADERS,
    )
    if r5.status_code != 200:
        return _log(False, "admin 按 status=left 过滤成员关系失败（期望 200）", {"status_code": r5.status_code, "body": r5.text})
    data5 = r5.json()
    left_user_ids = {item["user_id"] for item in data5["items"]}
    ok &= _log(
        member2_user_id in left_user_ids,
        "admin 按 status=left 过滤成员关系（包含 left 成员）场景",
        data5,
    )

    return ok


# ---------- 场景：创建时间范围过滤 ----------


def scenario_admin_list_memberships_created_time_filter(ctx: Dict[str, Any]) -> bool:
    """
    使用 created_from/created_to 过滤成员关系，确保：
    1）在一个宽松时间窗口内可以查到准备阶段产生的成员关系；
    2）在窗口之外查不到这些成员关系。
    """
    memberships: List[Dict[str, Any]] = ctx["memberships"]
    if not memberships:
        return _log(False, "created_time 过滤场景：ctx['memberships'] 为空", ctx)

    # 从准备阶段的 membership 中解析 created_at 列表
    created_list: list[datetime] = []
    for m in memberships:
        raw = m.get("created_at")
        if not isinstance(raw, str):
            continue
        try:
            # 兼容 FastAPI 默认的 ISO 格式，可能带尾部的 Z
            created_list.append(datetime.fromisoformat(raw.replace("Z", "+00:00")))
        except Exception as exc:  # noqa: BLE001
            _log(False, "解析 membership.created_at 失败", {"raw": raw, "error": str(exc)})

    if not created_list:
        return _log(False, "created_time 过滤场景：无法解析任何 created_at", memberships)

    earliest = min(created_list)
    latest = max(created_list)

    # 构造一个「肯定包含」所有记录的时间窗口：向前/向后各扩 5 分钟
    window_start = (earliest - timedelta(minutes=5)).isoformat()
    window_end = (latest + timedelta(minutes=5)).isoformat()

    group_id = ctx["group_id"]
    r_in = requests.get(
        f"{BASE_URL}/api/admin/memberships",
        params={
            "group_id": group_id,
            "created_from": window_start,
            "created_to": window_end,
            "page": 1,
            "page_size": 50,
        },
        headers=ADMIN_HEADERS,
    )
    if r_in.status_code != 200:
        return _log(
            False,
            "admin 使用 created_from/created_to 过滤成员关系失败（期望 200）",
            {"status_code": r_in.status_code, "body": r_in.text},
        )

    data_in = r_in.json()
    returned_ids_in = {item["id"] for item in data_in["items"]}
    original_ids = {m["id"] for m in memberships}
    ok_in = original_ids.issubset(returned_ids_in)

    ok = _log(
        ok_in,
        "admin 使用 created_from/created_to 过滤（窗口内包含准备阶段生成的成员关系）场景",
        {"window_start": window_start, "window_end": window_end, "returned": data_in},
    )

    # 再构造一个「肯定在所有记录之后」的时间窗口，预期查不到这些成员关系
    after_start = (latest + timedelta(minutes=10)).isoformat()
    after_end = (latest + timedelta(minutes=20)).isoformat()
    r_out = requests.get(
        f"{BASE_URL}/api/admin/memberships",
        params={
            "group_id": group_id,
            "created_from": after_start,
            "created_to": after_end,
            "page": 1,
            "page_size": 50,
        },
        headers=ADMIN_HEADERS,
    )
    if r_out.status_code != 200:
        return _log(
            False,
            "admin 使用 created_from/created_to（窗口在所有记录之后）过滤失败（期望 200）",
            {"status_code": r_out.status_code, "body": r_out.text},
        )

    data_out = r_out.json()
    returned_ids_out = {item["id"] for item in data_out["items"]}
    ok_out = original_ids.isdisjoint(returned_ids_out)

    ok &= _log(
        ok_out,
        "admin 使用 created_from/created_to（窗口在所有记录之后）过滤场景",
        {"after_start": after_start, "after_end": after_end, "returned": data_out},
    )

    return ok


# ---------- 场景：获取单条成员详情 ----------


def scenario_admin_get_membership_detail(ctx: Dict[str, Any]) -> bool:
    # 选 leader 的 membership
    leader_user_id = ctx["leader_user_id"]
    leader_membership = next(
        (m for m in ctx["memberships"] if m["user_id"] == leader_user_id),
        None,
    )
    if not leader_membership:
        return _log(False, "未找到 leader 的 membership 记录", ctx["memberships"])

    mid = leader_membership["id"]
    r = requests.get(
        f"{BASE_URL}/api/admin/memberships/{mid}",
        headers=ADMIN_HEADERS,
    )
    if r.status_code != 200:
        return _log(False, "admin 获取成员关系详情失败（期望 200）", {"status_code": r.status_code, "body": r.text})

    data = r.json()
    ok = data["id"] == mid and data["user_id"] == leader_user_id and data["group_id"] == ctx["group_id"]
    return _log(ok, "admin 获取成员关系详情场景", data)


def scenario_admin_get_membership_not_found() -> bool:
    r = requests.get(
        f"{BASE_URL}/api/admin/memberships/m_non_exist_12345",
        headers=ADMIN_HEADERS,
    )
    ok = r.status_code == 404
    return _log(ok, "admin 获取不存在成员关系返回 404 场景", {"status_code": r.status_code, "body": r.text})


# ---------- 场景：更新成员 role/status ----------


def scenario_admin_update_membership_role_and_status(ctx: Dict[str, Any]) -> bool:
    # 选 member1 的 membership
    member1_user_id = ctx["member1_user_id"]
    membership = next(
        (m for m in ctx["memberships"] if m["user_id"] == member1_user_id),
        None,
    )
    if not membership:
        return _log(False, "未找到 member1 的 membership 记录", ctx["memberships"])

    mid = membership["id"]
    r = requests.patch(
        f"{BASE_URL}/api/admin/memberships/{mid}",
        json={"role": "leader", "status": "kicked"},
        headers=ADMIN_HEADERS,
    )
    if r.status_code != 200:
        return _log(False, "admin 更新成员 role/status 失败（期望 200）", {"status_code": r.status_code, "body": r.text})

    data = r.json()
    ok = data["role"] == "leader" and data["status"] == "kicked"
    ok &= _log(ok, "admin 更新成员 role/status 场景", data)

    # 再获取详情确认
    r2 = requests.get(
        f"{BASE_URL}/api/admin/memberships/{mid}",
        headers=ADMIN_HEADERS,
    )
    if r2.status_code != 200:
        return _log(False, "admin 更新后再次获取成员关系详情失败（期望 200）", {"status_code": r2.status_code, "body": r2.text})
    data2 = r2.json()
    ok &= _log(
        data2["role"] == "leader" and data2["status"] == "kicked",
        "admin 更新成员 role/status 后详情校验场景",
        data2,
    )
    return ok


def scenario_admin_update_membership_no_fields(ctx: Dict[str, Any]) -> bool:
    # 取任意一条 membership
    mid = ctx["memberships"][0]["id"]
    r = requests.patch(
        f"{BASE_URL}/api/admin/memberships/{mid}",
        json={},
        headers=ADMIN_HEADERS,
    )
    ok = r.status_code == 400
    return _log(ok, "admin 更新成员关系但没有任何字段返回 400 场景", {"status_code": r.status_code, "body": r.text})


# ---------- 场景：删除成员关系 ----------


def scenario_admin_delete_membership_success(ctx: Dict[str, Any]) -> bool:
    # 单独创建一个临时成员用于删除测试
    temp_info = register_and_login("temp")
    temp_user_id = temp_info["user"]["id"]
    group_id = ctx["group_id"]

    # 让临时成员加入群
    join_group(temp_info["access_token"], group_id)

    # 通过 admin 列表找到它的 membership
    r = requests.get(
        f"{BASE_URL}/api/admin/memberships",
        params={"group_id": group_id, "user_id": temp_user_id, "page": 1, "page_size": 10},
        headers=ADMIN_HEADERS,
    )
    if r.status_code != 200:
        return _log(
            False,
            "admin 列出临时成员的 membership 失败（期望 200）",
            {"status_code": r.status_code, "body": r.text},
        )
    data = r.json()
    if not data["items"]:
        return _log(False, "未找到临时成员的 membership 记录", data)

    mid = data["items"][0]["id"]

    # 删除
    r2 = requests.delete(
        f"{BASE_URL}/api/admin/memberships/{mid}",
        headers=ADMIN_HEADERS,
    )
    if r2.status_code != 204:
        return _log(False, "admin 删除成员关系失败（期望 204）", {"status_code": r2.status_code, "body": r2.text})

    # 再查一次，应为 404
    r3 = requests.get(
        f"{BASE_URL}/api/admin/memberships/{mid}",
        headers=ADMIN_HEADERS,
    )
    ok = r3.status_code == 404
    return _log(ok, "admin 删除成员关系后再次获取返回 404 场景", {"status_code": r3.status_code, "body": r3.text})


def scenario_admin_delete_membership_not_found() -> bool:
    r = requests.delete(
        f"{BASE_URL}/api/admin/memberships/m_non_exist_6789",
        headers=ADMIN_HEADERS,
    )
    ok = r.status_code == 404
    return _log(ok, "admin 删除不存在成员关系返回 404 场景", {"status_code": r.status_code, "body": r.text})


# ---------- 场景：管理员 token 缺失 / 错误 ----------


def scenario_admin_missing_or_wrong_token() -> bool:
    ok = True

    # 不带任何 X-Admin-Token
    r = requests.get(f"{BASE_URL}/api/admin/memberships")
    ok &= _log(
        r.status_code == 403,
        "缺少 X-Admin-Token 访问后台成员关系接口被禁止场景",
        {"status_code": r.status_code, "body": r.text},
    )

    # 带错误的 token
    r = requests.get(
        f"{BASE_URL}/api/admin/memberships",
        headers={"X-Admin-Token": "WrongKey"},
    )
    ok &= _log(
        r.status_code == 403,
        "错误 X-Admin-Token 访问后台成员关系接口被禁止场景",
        {"status_code": r.status_code, "body": r.text},
    )

    return ok


# ---------- 总入口 ----------


def run_all() -> None:
    print("=== 开始 Admin Memberships 后台成员关系接口测试 ===")
    ctx: Dict[str, Any] = {}

    ok = True
    ok &= setup_memberships(ctx)
    ok &= scenario_admin_list_memberships_basic(ctx)
    ok &= scenario_admin_list_memberships_filters(ctx)
    ok &= scenario_admin_list_memberships_created_time_filter(ctx)
    ok &= scenario_admin_get_membership_detail(ctx)
    ok &= scenario_admin_get_membership_not_found()
    ok &= scenario_admin_update_membership_role_and_status(ctx)
    ok &= scenario_admin_update_membership_no_fields(ctx)
    ok &= scenario_admin_delete_membership_success(ctx)
    ok &= scenario_admin_delete_membership_not_found()
    ok &= scenario_admin_missing_or_wrong_token()

    print("\n=== Admin Memberships 测试结果: {} ===".format("全部通过 ✅" if ok else "有失败 ❌"))


if __name__ == "__main__":
    run_all()

