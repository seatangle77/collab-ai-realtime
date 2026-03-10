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
    # 与 /api/auth/register 的密码规则保持一致：必须为 4 位
    password = "1234"

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

    # 新增字段：每条记录都应该带有 group_name / user_name
    for item in data["items"]:
        if "group_name" not in item or "user_name" not in item:
            return _log(False, "admin 列表返回缺少 group_name/user_name 字段", item)
        if not isinstance(item["group_name"], str) or not isinstance(item["user_name"], str):
            return _log(False, "admin 列表返回的 group_name/user_name 类型错误", item)

    return _log(ok, "admin 基础分页列出成员关系场景（含名称字段）", data)


def scenario_admin_list_memberships_with_names(ctx: Dict[str, Any]) -> bool:
    """
    验证：
    1）按 group_id 查询时，每条记录都带有 group_name/user_name；
    2）准备阶段创建的群“成员测试群”的成员记录，其 group_name 与 user_name 与预期一致。
    """
    group_id = ctx["group_id"]
    leader_user_id = ctx["leader_user_id"]
    member1_user_id = ctx["member1_user_id"]
    member2_user_id = ctx["member2_user_id"]

    r = requests.get(
        f"{BASE_URL}/api/admin/memberships",
        params={"group_id": group_id, "page": 1, "page_size": 50},
        headers=ADMIN_HEADERS,
    )
    if r.status_code != 200:
        return _log(
            False,
            "admin 按 group_id 获取成员关系列表（验证名称字段）失败（期望 200）",
            {"status_code": r.status_code, "body": r.text},
        )

    data = r.json()
    items: List[Dict[str, Any]] = data.get("items", [])
    if not items:
        return _log(False, "admin 按 group_id 获取成员关系列表为空，无法验证名称字段", data)

    # 1）所有记录都应具有非空的 group_name/user_name 字段
    for item in items:
        if "group_name" not in item or "user_name" not in item:
            return _log(False, "admin 按 group_id 列表返回缺少 group_name/user_name 字段", item)
        if not isinstance(item["group_name"], str) or not isinstance(item["user_name"], str):
            return _log(False, "admin 按 group_id 列表返回的 group_name/user_name 类型错误", item)
        if not item["group_name"]:
            return _log(False, "admin 按 group_id 列表返回的 group_name 为空字符串", item)

    # 2）针对已知用户校验名称正确性
    expected_group_name = "成员测试群"
    expected_leader_name = "成员测试用户-leader"
    expected_member1_name = "成员测试用户-member1"
    expected_member2_name = "成员测试用户-member2"

    def _find_by_user(uid: str) -> Dict[str, Any] | None:
        for it in items:
            if it.get("user_id") == uid:
                return it
        return None

    leader_item = _find_by_user(leader_user_id)
    member1_item = _find_by_user(member1_user_id)
    member2_item = _find_by_user(member2_user_id)

    if not (leader_item and member1_item and member2_item):
        return _log(
            False,
            "admin 按 group_id 返回的成员关系列表中缺少 leader/member1/member2 记录",
            {"items": items},
        )

    ok = True
    ok &= leader_item["group_name"] == expected_group_name and leader_item["user_name"] == expected_leader_name
    ok &= member1_item["group_name"] == expected_group_name and member1_item["user_name"] == expected_member1_name
    ok &= member2_item["group_name"] == expected_group_name and member2_item["user_name"] == expected_member2_name

    return _log(ok, "admin 按 group_id 返回的成员关系列表包含正确的 group_name/user_name 场景", data)


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


# ---------- 场景：管理员通过接口创建成员关系 ----------


def scenario_admin_create_membership_success(_ctx: Dict[str, Any]) -> bool:
    """
    管理员为指定群组和用户创建一条全新的成员关系，预期 201 且列表可见。
    为避免干扰已有上下文，这里使用独立的用户与群组。
    """
    # leader 创建群
    info_leader = register_and_login("create_success_leader")
    group_detail = create_group(info_leader["access_token"], name="admin 创建成员关系-成功场景")
    group_id = group_detail["group"]["id"]

    # 再注册一个成员用户
    info_member = register_and_login("create_success_member")
    user_id = info_member["user"]["id"]

    # 通过 admin 创建成员关系
    r = requests.post(
        f"{BASE_URL}/api/admin/memberships",
        json={
            "group_id": group_id,
            "user_id": user_id,
            "role": "member",
            "status": "active",
        },
        headers=ADMIN_HEADERS,
    )
    if r.status_code != 201:
        return _log(
            False,
            "admin 创建成员关系失败（期望 201）",
            {"status_code": r.status_code, "body": r.text},
        )
    data = r.json()
    ok = data["group_id"] == group_id and data["user_id"] == user_id
    ok &= _log(ok, "admin 创建成员关系成功场景", data)

    # 再通过 admin 列表接口确认可见
    r_list = requests.get(
        f"{BASE_URL}/api/admin/memberships",
        params={"group_id": group_id, "user_id": user_id, "page": 1, "page_size": 10},
        headers=ADMIN_HEADERS,
    )
    if r_list.status_code != 200:
        return _log(
            False,
            "admin 创建后按 group_id+user_id 列出成员关系失败（期望 200）",
            {"status_code": r_list.status_code, "body": r_list.text},
        )
    data_list = r_list.json()
    ok &= _log(
        any(item["id"] == data["id"] for item in data_list.get("items", [])),
        "admin 创建成员关系后列表校验场景",
        data_list,
    )
    return ok


def scenario_admin_create_membership_already_active_conflict(ctx: Dict[str, Any]) -> bool:
    """
    对已经 active 的成员再次创建 active 成员关系，应返回 409。
    """
    # 为避免受前面场景中对 member2 status 修改的影响，这里**固定使用 leader** 的成员关系，
    # leader 在所有场景中始终保持 active 状态。
    leader_user_id = ctx["leader_user_id"]
    membership = next(
        (m for m in ctx["memberships"] if m.get("user_id") == leader_user_id),
        None,
    )
    if not membership:
        return _log(False, "未找到任何 active 成员关系，无法测试重复添加场景", ctx["memberships"])

    r = requests.post(
        f"{BASE_URL}/api/admin/memberships",
        json={
            "group_id": membership["group_id"],
            "user_id": membership["user_id"],
            "role": membership["role"],
            "status": "active",
        },
        headers=ADMIN_HEADERS,
    )
    ok = r.status_code == 409
    return _log(
        ok,
        "admin 为已在群中的 active 成员重复创建成员关系返回 409 场景",
        {"status_code": r.status_code, "body": r.text},
    )


def scenario_admin_create_membership_group_full() -> bool:
    """
    当群组已满（active 成员数达到 MAX_GROUP_MEMBERS）时，尝试为新用户创建 active 成员关系应返回 409。
    """
    # 创建 leader + 群
    info_leader = register_and_login("group_full_leader")
    group_detail = create_group(info_leader["access_token"], name="成员关系-满员群")
    group_id = group_detail["group"]["id"]

    # 再注册若干成员并通过业务 join 接口加入，直到达到上限
    members: list[Dict[str, Any]] = []
    for i in range(1, 3):  # 业务侧 MAX_GROUP_MEMBERS=3，leader 已经占 1，这里再加入 2 个
        info = register_and_login(f"group_full_member{i}")
        members.append(info)
        join_group(info["access_token"], group_id)

    # 额外注册一个用户，尝试通过 admin 创建 active 成员关系
    extra = register_and_login("group_full_extra")
    r = requests.post(
        f"{BASE_URL}/api/admin/memberships",
        json={
            "group_id": group_id,
            "user_id": extra["user"]["id"],
            "role": "member",
            "status": "active",
        },
        headers=ADMIN_HEADERS,
    )
    ok = r.status_code == 409
    return _log(
        ok,
        "admin 在群组人数已满时创建 active 成员关系返回 409 场景",
        {"status_code": r.status_code, "body": r.text},
    )


def scenario_admin_create_membership_reactivate_existing() -> bool:
    """
    对已有成员关系（status!=active）使用 POST 接口进行“复活”，应复用原记录并更新 role/status。
    """
    # 独立构造一个群组和成员关系，避免污染其它场景
    info_leader = register_and_login("reactivate_leader")
    group_detail = create_group(info_leader["access_token"], name="成员关系-复活场景群")
    group_id = group_detail["group"]["id"]

    info_member = register_and_login("reactivate_member")
    user_id = info_member["user"]["id"]

    # 先通过业务 join 接口生成一条 active 成员关系
    join_group(info_member["access_token"], group_id)

    # 找到这条 membership
    r_list = requests.get(
        f"{BASE_URL}/api/admin/memberships",
        params={"group_id": group_id, "user_id": user_id, "page": 1, "page_size": 10},
        headers=ADMIN_HEADERS,
    )
    if r_list.status_code != 200:
        return _log(
            False,
            "reactivate 场景：首次列出成员关系失败（期望 200）",
            {"status_code": r_list.status_code, "body": r_list.text},
        )
    data_list = r_list.json()
    if not data_list["items"]:
        return _log(False, "reactivate 场景：未找到成员关系记录", data_list)
    membership = data_list["items"][0]
    mid = membership["id"]

    # 先通过 admin 接口将其 status 改为 left
    r_update = requests.patch(
        f"{BASE_URL}/api/admin/memberships/{mid}",
        json={"status": "left"},
        headers=ADMIN_HEADERS,
    )
    if r_update.status_code != 200:
        return _log(
            False,
            "reactivate 场景：将成员 status 设为 left 失败（期望 200）",
            {"status_code": r_update.status_code, "body": r_update.text},
        )

    # 再通过 POST 接口将其“复活”为 active，并变更角色为 member（如果之前是 leader）
    r_create = requests.post(
        f"{BASE_URL}/api/admin/memberships",
        json={
            "group_id": group_id,
            "user_id": user_id,
            "role": "member",
            "status": "active",
        },
        headers=ADMIN_HEADERS,
    )
    if r_create.status_code != 201:
        return _log(
            False,
            "reactivate 场景：通过 POST 复活成员关系失败（期望 201）",
            {"status_code": r_create.status_code, "body": r_create.text},
        )
    data_create = r_create.json()
    ok = data_create["id"] == mid and data_create["status"] == "active" and data_create["role"] == "member"
    ok &= _log(ok, "reactivate 场景：POST 返回内容校验", data_create)

    # 再获取详情确认
    r_detail = requests.get(
        f"{BASE_URL}/api/admin/memberships/{mid}",
        headers=ADMIN_HEADERS,
    )
    if r_detail.status_code != 200:
        return _log(
            False,
            "reactivate 场景：复活后获取详情失败（期望 200）",
            {"status_code": r_detail.status_code, "body": r_detail.text},
        )
    data_detail = r_detail.json()
    ok &= _log(
        data_detail["status"] == "active" and data_detail["role"] == "member",
        "reactivate 场景：详情状态校验",
        data_detail,
    )
    return ok


def scenario_admin_create_membership_in_inactive_group() -> bool:
    """
    当群组 is_active=False 时，尝试创建成员关系应返回 409。
    """
    # 创建群组
    info_leader = register_and_login("inactive_group_leader")
    group_detail = create_group(info_leader["access_token"], name="成员关系-关闭群")
    group_id = group_detail["group"]["id"]

    # 将群组设为 inactive
    r_toggle = requests.patch(
        f"{BASE_URL}/api/admin/groups/{group_id}",
        json={"is_active": False},
        headers=ADMIN_HEADERS,
    )
    if r_toggle.status_code != 200:
        return _log(
            False,
            "inactive_group 场景：admin 将群组设为 inactive 失败（期望 200）",
            {"status_code": r_toggle.status_code, "body": r_toggle.text},
        )

    # 再注册一个成员用户
    info_member = register_and_login("inactive_group_member")
    user_id = info_member["user"]["id"]

    # 尝试创建 active 成员关系
    r_create = requests.post(
        f"{BASE_URL}/api/admin/memberships",
        json={
            "group_id": group_id,
            "user_id": user_id,
            "role": "member",
            "status": "active",
        },
        headers=ADMIN_HEADERS,
    )
    ok = r_create.status_code == 409
    return _log(
        ok,
        "inactive_group 场景：在已关闭群组中创建成员关系返回 409 场景",
        {"status_code": r_create.status_code, "body": r_create.text},
    )


def scenario_admin_create_membership_invalid_role_or_status(ctx: Dict[str, Any]) -> bool:
    """
    role/status 非法值时应返回 400。
    这里复用 ctx 中已有的 group_id 和某个用户 id。
    """
    group_id = ctx["group_id"]
    member1_user_id = ctx["member1_user_id"]

    ok = True

    # 无效角色
    r_role = requests.post(
        f"{BASE_URL}/api/admin/memberships",
        json={
            "group_id": group_id,
            "user_id": member1_user_id,
            "role": "invalid_role",
            "status": "active",
        },
        headers=ADMIN_HEADERS,
    )
    ok &= _log(
        r_role.status_code == 400,
        "admin 创建成员关系时传入无效 role 返回 400 场景",
        {"status_code": r_role.status_code, "body": r_role.text},
    )

    # 无效状态
    r_status = requests.post(
        f"{BASE_URL}/api/admin/memberships",
        json={
            "group_id": group_id,
            "user_id": member1_user_id,
            "role": "member",
            "status": "invalid_status",
        },
        headers=ADMIN_HEADERS,
    )
    ok &= _log(
        r_status.status_code == 400,
        "admin 创建成员关系时传入无效 status 返回 400 场景",
        {"status_code": r_status.status_code, "body": r_status.text},
    )

    return ok


def scenario_admin_create_membership_group_or_user_not_found(ctx: Dict[str, Any]) -> bool:
    """
    群组或用户不存在时应返回 404。
    """
    ok = True

    # 群组不存在
    r_group = requests.post(
        f"{BASE_URL}/api/admin/memberships",
        json={
            "group_id": "g_non_exist_12345",
            "user_id": ctx["member1_user_id"],
            "role": "member",
            "status": "active",
        },
        headers=ADMIN_HEADERS,
    )
    ok &= _log(
        r_group.status_code == 404,
        "admin 创建成员关系时群组不存在返回 404 场景",
        {"status_code": r_group.status_code, "body": r_group.text},
    )

    # 用户不存在
    r_user = requests.post(
        f"{BASE_URL}/api/admin/memberships",
        json={
            "group_id": ctx["group_id"],
            "user_id": "u_non_exist_67890",
            "role": "member",
            "status": "active",
        },
        headers=ADMIN_HEADERS,
    )
    ok &= _log(
        r_user.status_code == 404,
        "admin 创建成员关系时用户不存在返回 404 场景",
        {"status_code": r_user.status_code, "body": r_user.text},
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


# ---------- 场景：批量删除成员关系 ----------


def scenario_admin_batch_delete_memberships_success(ctx: Dict[str, Any]) -> bool:
    temp_info = register_and_login("batch_del_1")
    temp_info2 = register_and_login("batch_del_2")
    group_id = ctx["group_id"]
    join_group(temp_info["access_token"], group_id)
    join_group(temp_info2["access_token"], group_id)

    r = requests.get(
        f"{BASE_URL}/api/admin/memberships",
        params={"group_id": group_id, "page": 1, "page_size": 20},
        headers=ADMIN_HEADERS,
    )
    r.raise_for_status()
    items = r.json()["items"]
    ids = [m["id"] for m in items if m["user_id"] in (temp_info["user"]["id"], temp_info2["user"]["id"])]
    if len(ids) < 2:
        return _log(False, "准备批量删除的成员关系不足 2 条", {"items": items})

    r2 = requests.post(
        f"{BASE_URL}/api/admin/memberships/batch-delete",
        json={"ids": ids},
        headers=ADMIN_HEADERS,
    )
    if r2.status_code != 200:
        return _log(False, "admin 批量删除成员关系失败（期望 200）", {"status_code": r2.status_code, "body": r2.text})
    data = r2.json()
    if data.get("deleted") != len(ids):
        return _log(False, "admin 批量删除成员关系应返回 deleted 与请求数量一致", data)
    return _log(True, "admin 批量删除成员关系成功场景")


def scenario_admin_batch_delete_memberships_empty_ids() -> bool:
    r = requests.post(
        f"{BASE_URL}/api/admin/memberships/batch-delete",
        json={"ids": []},
        headers=ADMIN_HEADERS,
    )
    ok = r.status_code == 422
    return _log(ok, "admin 批量删除成员关系 ids 为空返回 422 场景", {"status_code": r.status_code, "body": r.text})


def scenario_admin_batch_delete_memberships_partial(ctx: Dict[str, Any]) -> bool:
    temp_info = register_and_login("batch_del_partial")
    group_id = ctx["group_id"]
    join_group(temp_info["access_token"], group_id)
    r = requests.get(
        f"{BASE_URL}/api/admin/memberships",
        params={"group_id": group_id, "user_id": temp_info["user"]["id"], "page": 1, "page_size": 5},
        headers=ADMIN_HEADERS,
    )
    r.raise_for_status()
    items = r.json()["items"]
    if not items:
        return _log(False, "未找到临时成员的 membership", None)
    mid = items[0]["id"]
    r2 = requests.post(
        f"{BASE_URL}/api/admin/memberships/batch-delete",
        json={"ids": [mid, "non-existent-membership-uuid-1111"]},
        headers=ADMIN_HEADERS,
    )
    if r2.status_code != 200:
        return _log(False, "admin 批量删除成员关系（含不存在的 id）应返回 200", {"status_code": r2.status_code, "body": r2.text})
    data = r2.json()
    if data.get("deleted") != 1:
        return _log(False, "admin 批量删除成员关系仅删除存在的 1 条", data)
    return _log(True, "admin 批量删除成员关系部分存在部分不存在场景")


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

    # 不带 X-Admin-Token 调用创建成员关系接口
    r_create = requests.post(
        f"{BASE_URL}/api/admin/memberships",
        json={
            "group_id": "g_dummy",
            "user_id": "u_dummy",
            "role": "member",
            "status": "active",
        },
    )
    ok &= _log(
        r_create.status_code == 403,
        "缺少 X-Admin-Token 调用 admin 创建成员关系接口被禁止场景",
        {"status_code": r_create.status_code, "body": r_create.text},
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

    # 带错误 token 调用创建成员关系接口
    r_create_wrong = requests.post(
        f"{BASE_URL}/api/admin/memberships",
        json={
            "group_id": "g_dummy",
            "user_id": "u_dummy",
            "role": "member",
            "status": "active",
        },
        headers={"X-Admin-Token": "WrongKey"},
    )
    ok &= _log(
        r_create_wrong.status_code == 403,
        "错误 X-Admin-Token 调用 admin 创建成员关系接口被禁止场景",
        {"status_code": r_create_wrong.status_code, "body": r_create_wrong.text},
    )

    return ok


# ---------- 总入口 ----------


def run_all() -> bool:
    print("=== 开始 Admin Memberships 后台成员关系接口测试 ===")
    ctx: Dict[str, Any] = {}

    ok = True
    ok &= setup_memberships(ctx)
    ok &= scenario_admin_list_memberships_basic(ctx)
    ok &= scenario_admin_list_memberships_with_names(ctx)
    ok &= scenario_admin_list_memberships_filters(ctx)
    ok &= scenario_admin_list_memberships_created_time_filter(ctx)
    ok &= scenario_admin_create_membership_success(ctx)
    ok &= scenario_admin_create_membership_already_active_conflict(ctx)
    ok &= scenario_admin_create_membership_group_full()
    ok &= scenario_admin_create_membership_reactivate_existing()
    ok &= scenario_admin_create_membership_in_inactive_group()
    ok &= scenario_admin_create_membership_invalid_role_or_status(ctx)
    ok &= scenario_admin_create_membership_group_or_user_not_found(ctx)
    ok &= scenario_admin_get_membership_detail(ctx)
    ok &= scenario_admin_get_membership_not_found()
    ok &= scenario_admin_update_membership_role_and_status(ctx)
    ok &= scenario_admin_update_membership_no_fields(ctx)
    ok &= scenario_admin_delete_membership_success(ctx)
    ok &= scenario_admin_delete_membership_not_found()
    ok &= scenario_admin_batch_delete_memberships_success(ctx)
    ok &= scenario_admin_batch_delete_memberships_empty_ids()
    ok &= scenario_admin_batch_delete_memberships_partial(ctx)
    ok &= scenario_admin_missing_or_wrong_token()

    print("\n=== Admin Memberships 测试结果: {} ===".format("全部通过 ✅" if ok else "有失败 ❌"))
    return ok


if __name__ == "__main__":
    import sys
    sys.exit(0 if run_all() else 1)

