from __future__ import annotations

import uuid
from typing import Any, Dict, Tuple

import requests

BASE_URL = "http://127.0.0.1:8000"
RUN_ID = uuid.uuid4().hex[:6]

# 和 app.admin.deps 中的默认值保持一致，用于在场景中切换群组启用状态
ADMIN_KEY = "TestAdminKey123"
ADMIN_HEADERS = {"X-Admin-Token": ADMIN_KEY}


def _log(ok: bool, message: str, extra: Any | None = None) -> bool:
    prefix = "✅" if ok else "❌"
    print(f"{prefix} {message}")
    if not ok and extra is not None:
        print("   详情:", extra)
    return ok


def register_and_login(name: str, email_suffix: str) -> Tuple[str, str]:
    """注册一个用户并登录，返回 (access_token, user_id)。"""
    email = f"test_{email_suffix}_{uuid.uuid4().hex[:6]}@example.com"
    # /api/auth/register 要求密码必须为 4 位
    password = "1234"

    r = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={
            "name": name,
            "email": email,
            "password": password,
            "device_token": f"device-{email_suffix}-{uuid.uuid4().hex[:8]}",
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
        json={"name": f"Initial Group {RUN_ID}"},
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
        data["group"]["name"] == f"Initial Group {RUN_ID}"
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
        json={"name": f"Renamed Group {RUN_ID}"},
        headers=headers,
    )
    if r.status_code != 200:
        return _log(False, "leader 修改组名失败（期望 200）", r.json())

    data = r.json()
    ok = data["group"]["name"] == f"Renamed Group {RUN_ID}"
    return _log(ok, "leader 修改组名场景", data)


def scenario_rename_group_by_member_forbidden(ctx: Dict[str, Any]) -> bool:
    headers = {"Authorization": f"Bearer {ctx['third_token']}"}
    r = requests.patch(
        f"{BASE_URL}/api/groups/{ctx['group_id']}",
        json={"name": "Should Not Apply"},
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


def scenario_discover_basic_list(ctx: Dict[str, Any]) -> bool:
    """
    基础场景：新用户可以在 /groups/discover 中看到可加入的群组（包含当前业务场景中的群）。
    """
    headers = {"Authorization": f"Bearer {ctx['discover_token']}"}
    r = requests.get(f"{BASE_URL}/api/groups/discover", headers=headers)
    if r.status_code != 200:
        return _log(False, "/groups/discover 基础列表失败（期望 200）", {"status_code": r.status_code, "body": r.text})

    data = r.json()
    if not isinstance(data, list):
        return _log(False, "/groups/discover 返回值不是列表", data)

    ids = {g["id"] for g in data if isinstance(g, dict) and "id" in g}
    ok = True
    # 至少包含当前业务群组（leader 创建的那个）
    ok &= ctx["group_id"] in ids

    # 字段与约束基本校验
    for g in data:
        if not isinstance(g, dict):
            ok = False
            break
        if not {"id", "name", "created_at", "is_active", "member_count"} <= g.keys():
            ok = False
            break
        if not g["is_active"]:
            ok = False
            break
        # discover 中不应包含已满员的群
        if g["member_count"] >= 3:
            ok = False
            break

    return _log(ok, "/groups/discover 基础列表场景", data)


def scenario_discover_excludes_joined(ctx: Dict[str, Any]) -> bool:
    """
    新用户加入某个群后，该群应从 /groups/discover 列表中消失。
    """
    discover_headers = {"Authorization": f"Bearer {ctx['discover_token']}"}

    # 先加入业务群组
    r_join = requests.post(
        f"{BASE_URL}/api/groups/{ctx['group_id']}/join",
        headers=discover_headers,
    )
    if r_join.status_code != 200:
        return _log(False, "discover 用户加入群组失败（期望 200）", {"status_code": r_join.status_code, "body": r_join.text})

    # 再次获取 discover 列表
    r = requests.get(f"{BASE_URL}/api/groups/discover", headers=discover_headers)
    if r.status_code != 200:
        return _log(False, "加入后获取 /groups/discover 失败（期望 200）", {"status_code": r.status_code, "body": r.text})

    data = r.json()
    ids = {g["id"] for g in data if isinstance(g, dict) and "id" in g}
    ok = ctx["group_id"] not in ids
    return _log(ok, "加入后 /groups/discover 不再包含该群组场景", data)


def scenario_discover_name_filter(ctx: Dict[str, Any]) -> bool:
    """
    按 name 模糊过滤 discover 列表。
    """
    # 使用 leader 再创建几组带特定前缀的群
    headers_leader = {"Authorization": f"Bearer {ctx['leader_token']}"}
    abc_ids = []
    for i in range(2):
        name = f"Discover Test Group ABC {i + 1} {RUN_ID}"
        r = requests.post(
            f"{BASE_URL}/api/groups",
            json={"name": name},
            headers=headers_leader,
        )
        r.raise_for_status()
        abc_ids.append(r.json()["group"]["id"])

    # 再创建一个不含该前缀的群
    r_other = requests.post(
        f"{BASE_URL}/api/groups",
        json={"name": f"Discover Test Group XYZ 1 {RUN_ID}"},
        headers=headers_leader,
    )
    r_other.raise_for_status()

    headers_discover = {"Authorization": f"Bearer {ctx['discover_token']}"}
    r = requests.get(
        f"{BASE_URL}/api/groups/discover",
        params={"name": "ABC"},
        headers=headers_discover,
    )
    if r.status_code != 200:
        return _log(False, "/groups/discover 按 name 过滤失败（期望 200）", {"status_code": r.status_code, "body": r.text})

    data = r.json()
    if not isinstance(data, list):
        return _log(False, "/groups/discover 按 name 过滤返回值不是列表", data)

    returned_ids = {g["id"] for g in data if isinstance(g, dict) and "id" in g}
    ok = True

    # 所有返回项 name 都应该包含 "ABC"
    for g in data:
        if "name" not in g or "ABC" not in g["name"]:
            ok = False
            break

    # 至少包含我们创建的 ABC 群中的一个
    ok &= bool(set(abc_ids) & returned_ids)

    return _log(ok, "/groups/discover 按 name 模糊过滤场景", data)


def scenario_discover_limit(ctx: Dict[str, Any]) -> bool:
    """
    limit 参数能够限制返回条数。
    """
    headers = {"Authorization": f"Bearer {ctx['discover_token']}"}

    r_all = requests.get(f"{BASE_URL}/api/groups/discover", headers=headers)
    if r_all.status_code != 200:
        return _log(False, "获取 /groups/discover 全量列表失败（期望 200）", {"status_code": r_all.status_code, "body": r_all.text})
    all_data = r_all.json()
    total = len(all_data) if isinstance(all_data, list) else 0

    r_limit = requests.get(
        f"{BASE_URL}/api/groups/discover",
        params={"limit": 2},
        headers=headers,
    )
    if r_limit.status_code != 200:
        return _log(False, "/groups/discover 携带 limit 失败（期望 200）", {"status_code": r_limit.status_code, "body": r_limit.text})

    data = r_limit.json()
    if not isinstance(data, list):
        return _log(False, "/groups/discover 携带 limit 返回值不是列表", data)

    ok = len(data) <= 2
    if total >= 2:
        ok &= len(data) == 2

    return _log(ok, "/groups/discover limit 参数限制条数场景", {"total_before": total, "limited": len(data)})


def scenario_discover_excludes_full_groups() -> bool:
    """
    已经满员的群组不会出现在任何用户的 discover 列表中。
    """
    # 创建一个群并补满 3 人
    leader_token, _ = register_and_login(f"Full Group Leader {RUN_ID}", "discover_full_leader")
    headers_leader = {"Authorization": f"Bearer {leader_token}"}
    r = requests.post(
        f"{BASE_URL}/api/groups",
        json={"name": f"Full Member Test Group {RUN_ID}"},
        headers=headers_leader,
    )
    r.raise_for_status()
    group_id = r.json()["group"]["id"]

    # 再注册两个成员并加入该群，使其达到上限 3 人
    for label in ("a", "b"):
        member_token, _ = register_and_login(f"Full Group Member {label} {RUN_ID}", f"discover_full_{label}")
        headers_member = {"Authorization": f"Bearer {member_token}"}
        r_join = requests.post(f"{BASE_URL}/api/groups/{group_id}/join", headers=headers_member)
        if r_join.status_code != 200:
            return _log(
                False,
                "补满成员时加入群组失败（期望 200）",
                {"label": label, "status_code": r_join.status_code, "body": r_join.text},
            )

    # 第四个用户既不在群内，也用于调用 discover
    viewer_token, _ = register_and_login(f"Full Group Viewer {RUN_ID}", "discover_full_viewer")
    headers_viewer = {"Authorization": f"Bearer {viewer_token}"}

    r = requests.get(f"{BASE_URL}/api/groups/discover", headers=headers_viewer)
    if r.status_code != 200:
        return _log(
            False,
            "满员场景下获取 /groups/discover 失败（期望 200）",
            {"status_code": r.status_code, "body": r.text},
        )

    data = r.json()
    ids = {g["id"] for g in data if isinstance(g, dict) and "id" in g}
    ok = group_id not in ids

    # 顺便验证：第四个用户直接 join 也应该得到 409
    r_join_full = requests.post(f"{BASE_URL}/api/groups/{group_id}/join", headers=headers_viewer)
    ok &= r_join_full.status_code == 409

    return _log(ok, "已满员群组不出现在 discover 且 join 返回 409 场景", {"discover_ids": list(ids), "join_status": r_join_full.status_code})


def scenario_discover_inactive_groups_hidden() -> bool:
    """
    is_active = False 的群组应从 discover 列表中隐藏。
    """
    # 新建一个群
    leader_token, _ = register_and_login(f"Inactive Group Leader {RUN_ID}", "discover_inactive_leader")
    headers_leader = {"Authorization": f"Bearer {leader_token}"}
    r = requests.post(
        f"{BASE_URL}/api/groups",
        json={"name": f"Inactive Test Group {RUN_ID}"},
        headers=headers_leader,
    )
    r.raise_for_status()
    group_id = r.json()["group"]["id"]

    # 通过 admin 接口将其设为 inactive
    r_admin = requests.patch(
        f"{BASE_URL}/api/admin/groups/{group_id}",
        json={"is_active": False},
        headers=ADMIN_HEADERS,
    )
    if r_admin.status_code != 200:
        return _log(
            False,
            "admin 将群组设为 inactive 失败（期望 200）",
            {"status_code": r_admin.status_code, "body": r_admin.text},
        )

    # 用一个未加入该群的普通用户查看 discover
    viewer_token, _ = register_and_login(f"Inactive Group Viewer {RUN_ID}", "discover_inactive_viewer")
    headers_viewer = {"Authorization": f"Bearer {viewer_token}"}
    r = requests.get(f"{BASE_URL}/api/groups/discover", headers=headers_viewer)
    if r.status_code != 200:
        return _log(
            False,
            "停用群组场景下获取 /groups/discover 失败（期望 200）",
            {"status_code": r.status_code, "body": r.text},
        )

    data = r.json()
    ids = {g["id"] for g in data if isinstance(g, dict) and "id" in g}
    ok = group_id not in ids
    return _log(ok, "is_active=false 群组不在 discover 列表中场景", {"discover_ids": list(ids)})


def scenario_discover_rejoin_left_group() -> bool:
    """
    用户离开某群后，该群应重新出现在该用户的 discover 列表中。
    """
    leader_token, _ = register_and_login(f"Leave Group Leader {RUN_ID}", "discover_left_leader")
    headers_leader = {"Authorization": f"Bearer {leader_token}"}
    r = requests.post(
        f"{BASE_URL}/api/groups",
        json={"name": f"Rejoinable Test Group {RUN_ID}"},
        headers=headers_leader,
    )
    r.raise_for_status()
    group_id = r.json()["group"]["id"]

    member_token, _ = register_and_login(f"Leave Group Member {RUN_ID}", "discover_left_member")
    headers_member = {"Authorization": f"Bearer {member_token}"}

    # 成员先加入该群
    r_join = requests.post(f"{BASE_URL}/api/groups/{group_id}/join", headers=headers_member)
    if r_join.status_code != 200:
        return _log(
            False,
            "成员首次加入群组失败（期望 200）",
            {"status_code": r_join.status_code, "body": r_join.text},
        )

    # 成员退出该群
    r_leave = requests.post(f"{BASE_URL}/api/groups/{group_id}/leave", headers=headers_member)
    if r_leave.status_code != 200:
        return _log(
            False,
            "成员退出群组失败（期望 200）",
            {"status_code": r_leave.status_code, "body": r_leave.text},
        )

    # 再看 discover 列表，应重新出现该群
    r_discover = requests.get(f"{BASE_URL}/api/groups/discover", headers=headers_member)
    if r_discover.status_code != 200:
        return _log(
            False,
            "成员退出后获取 /groups/discover 失败（期望 200）",
            {"status_code": r_discover.status_code, "body": r_discover.text},
        )

    data = r_discover.json()
    ids = {g["id"] for g in data if isinstance(g, dict) and "id" in g}
    ok = group_id in ids
    return _log(ok, "成员退出后对应群组重新出现在 discover 列表场景", {"discover_ids": list(ids)})


def scenario_discover_unauthorized() -> bool:
    """
    未携带或携带错误的用户端 token 访问 /groups/discover 应被拒绝。
    """
    ok = True

    # 缺少 Authorization
    r = requests.get(f"{BASE_URL}/api/groups/discover")
    ok &= _log(
        r.status_code in (401, 403),
        "缺少 Authorization 访问 /groups/discover 被拒绝场景",
        {"status_code": r.status_code, "body": r.text},
    )

    # 错误的 Authorization
    r2 = requests.get(
        f"{BASE_URL}/api/groups/discover",
        headers={"Authorization": "Bearer invalid_token_123"},
    )
    ok &= _log(
        r2.status_code in (401, 403),
        "错误 Authorization 访问 /groups/discover 被拒绝场景",
        {"status_code": r2.status_code, "body": r2.text},
    )

    return ok


def run_all() -> bool:
    print("=== 开始 Group 组队相关功能测试 ===")

    ctx: Dict[str, Any] = {}

    ctx["leader_token"], ctx["leader_user_id"] = register_and_login(f"Alice Chen {RUN_ID}", "leader")
    ctx["second_token"], ctx["second_user_id"] = register_and_login(f"Bob Wang {RUN_ID}", "second")
    ctx["third_token"], ctx["third_user_id"] = register_and_login(f"Carol Liu {RUN_ID}", "third")
    ctx["fourth_token"], ctx["fourth_user_id"] = register_and_login(f"David Zhang {RUN_ID}", "fourth")
    ctx["discover_token"], ctx["discover_user_id"] = register_and_login(f"Eve Yang {RUN_ID}", "discover")

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

    # /api/groups/discover 相关场景
    ok &= scenario_discover_basic_list(ctx)
    ok &= scenario_discover_excludes_joined(ctx)
    ok &= scenario_discover_name_filter(ctx)
    ok &= scenario_discover_limit(ctx)
    ok &= scenario_discover_excludes_full_groups()
    ok &= scenario_discover_inactive_groups_hidden()
    ok &= scenario_discover_rejoin_left_group()
    ok &= scenario_discover_unauthorized()

    print("\n=== Group 测试结果: {} ===".format("全部通过 ✅" if ok else "有失败 ❌"))
    return ok


if __name__ == "__main__":
    import sys
    sys.exit(0 if run_all() else 1)

