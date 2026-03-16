from __future__ import annotations

import uuid
from typing import Any, Dict, Tuple

from datetime import datetime, timedelta, timezone

import requests

BASE_URL = "http://127.0.0.1:8000"
RUN_ID = uuid.uuid4().hex[:6]


def _log(ok: bool, message: str, extra: Any | None = None) -> bool:
    prefix = "✅" if ok else "❌"
    print(f"{prefix} {message}")
    if not ok and extra is not None:
        print("   详情:", extra)
    return ok


def register_and_login(label: str) -> Tuple[str, str]:
    """
    注册一个用户并登录，返回 (access_token, user_id)。
    与其他测试脚本保持相似风格。
    """
    email = f"app_session_{label}_{uuid.uuid4().hex[:6]}@example.com"
    # 根据 /api/auth/register 的规则：密码必须为 4 位
    password = "1234"

    r = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={
            "name": f"Session User {label} {RUN_ID}",
            "email": email,
            "password": password,
            "device_token": f"device-session-{label}-{uuid.uuid4().hex[:8]}",
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


def setup_group_and_sessions(ctx: Dict[str, Any]) -> bool:
    """
    场景准备：
    - 注册 3 个用户：leader / member / outsider
    - leader 创建群组
    - member 加入群组
    - leader 创建会话 A
    - member 创建会话 B
    - member 结束会话 A

    这样 ctx 中会有：
    - leader_token, member_token, outsider_token
    - group_id
    - session_id_a (已结束), session_id_b (进行中)
    """
    ok = True

    leader_token, leader_user_id = register_and_login("leader")
    member_token, member_user_id = register_and_login("member")
    outsider_token, outsider_user_id = register_and_login("outsider")

    ctx["leader_token"] = leader_token
    ctx["leader_user_id"] = leader_user_id
    ctx["member_token"] = member_token
    ctx["member_user_id"] = member_user_id
    ctx["outsider_token"] = outsider_token
    ctx["outsider_user_id"] = outsider_user_id

    # leader 创建群组
    headers_leader = {"Authorization": f"Bearer {leader_token}"}
    r = requests.post(
        f"{BASE_URL}/api/groups",
        json={"name": f"App Session Test Group {RUN_ID}"},
        headers=headers_leader,
    )
    if r.status_code != 201:
        return _log(False, "准备阶段：创建群组失败", {"status_code": r.status_code, "body": r.text})
    group_detail = r.json()
    group_id = group_detail["group"]["id"]
    ctx["group_id"] = group_id

    # member 加入群组
    headers_member = {"Authorization": f"Bearer {member_token}"}
    r = requests.post(
        f"{BASE_URL}/api/groups/{group_id}/join",
        headers=headers_member,
    )
    if r.status_code != 200:
        return _log(False, "准备阶段：成员加入群组失败", {"status_code": r.status_code, "body": r.text})

    # leader 创建会话 A
    r = requests.post(
        f"{BASE_URL}/api/groups/{group_id}/sessions",
        json={"session_title": "Session A To End"},
        headers=headers_leader,
    )
    if r.status_code != 201:
        return _log(False, "准备阶段：leader 创建会话 A 失败", {"status_code": r.status_code, "body": r.text})
    session_a = r.json()
    ctx["session_id_a"] = session_a["id"]

    # member 创建会话 B
    r = requests.post(
        f"{BASE_URL}/api/groups/{group_id}/sessions",
        json={"session_title": "Session B Ongoing"},
        headers=headers_member,
    )
    if r.status_code != 201:
        return _log(False, "准备阶段：member 创建会话 B 失败", {"status_code": r.status_code, "body": r.text})
    session_b = r.json()
    ctx["session_id_b"] = session_b["id"]

    # member 结束会话 A
    r = requests.post(
        f"{BASE_URL}/api/sessions/{ctx['session_id_a']}/end",
        headers=headers_member,
    )
    if r.status_code != 200:
        return _log(False, "准备阶段：member 结束会话 A 失败", {"status_code": r.status_code, "body": r.text})
    ended = r.json()

    ok &= _log(True, "准备阶段：创建群组/2个会话并结束其中1个成功", {"group_id": group_id, "ended": ended})
    return ok


def scenario_list_sessions_response_schema(ctx: Dict[str, Any]) -> bool:
    """
    校验列表响应结构：
    - 每条记录包含 is_active / ended_at 字段
    - include_ended=false 时不返回已结束会话 A
    - include_ended=true 时包含会话 A，且其 is_active=False, ended_at 非空
    """
    ok = True
    group_id = ctx["group_id"]

    headers_member = {"Authorization": f"Bearer {ctx['member_token']}"}

    # 默认列表（不传 include_ended）
    r = requests.get(
        f"{BASE_URL}/api/groups/{group_id}/sessions",
        headers=headers_member,
    )
    if r.status_code != 200:
        return _log(False, "列表接口（默认）请求失败（期望 200）", {"status_code": r.status_code, "body": r.text})
    sessions_default = r.json()

    # 结构校验
    for item in sessions_default:
        for key in ["id", "group_id", "created_at", "last_updated", "session_title", "status", "ended_at"]:
            if key not in item:
                return _log(False, f"默认列表返回缺少字段 {key}", item)

    ids_default = {s["id"] for s in sessions_default}
    ok &= _log(
        ctx["session_id_a"] not in ids_default and ctx["session_id_b"] in ids_default,
        "默认列表仅包含未结束的会话（B）",
        {"ids": list(ids_default)},
    )

    # include_ended=true
    r = requests.get(
        f"{BASE_URL}/api/groups/{group_id}/sessions",
        params={"include_ended": "true"},
        headers=headers_member,
    )
    if r.status_code != 200:
        return _log(False, "列表接口（include_ended=true）请求失败（期望 200）", {"status_code": r.status_code, "body": r.text})
    sessions_all = r.json()
    ids_all = {s["id"] for s in sessions_all}

    if not (ctx["session_id_a"] in ids_all and ctx["session_id_b"] in ids_all):
        return _log(False, "include_ended=true 时应包含 A/B 两个会话", {"ids": list(ids_all)})

    # 检查已结束会话 A 的状态字段
    session_a = next((s for s in sessions_all if s["id"] == ctx["session_id_a"]), None)
    if not session_a:
        return _log(False, "未在 include_ended 结果中找到会话 A", {"sessions": sessions_all})

    ok &= _log(
        session_a.get("status") == "ended" and session_a.get("ended_at") is not None,
        "已结束会话 A 在列表中具有正确的 status/ended_at",
        session_a,
    )

    return ok


def scenario_create_session_success_and_forbidden(ctx: Dict[str, Any]) -> bool:
    ok = True
    group_id = ctx["group_id"]

    # 成员创建会话成功
    headers_member = {"Authorization": f"Bearer {ctx['member_token']}"}
    r = requests.post(
        f"{BASE_URL}/api/groups/{group_id}/sessions",
        json={"session_title": "New Session Member Created"},
        headers=headers_member,
    )
    if r.status_code != 201:
        return _log(False, "成员创建会话失败（期望 201）", {"status_code": r.status_code, "body": r.text})
    data = r.json()
    required_keys = {"id", "group_id", "session_title", "created_at", "last_updated", "status", "ended_at"}
    if not required_keys <= data.keys():
        return _log(False, "成员创建会话返回字段不完整", data)
    ok &= _log(True, "成员创建会话成功（带状态字段）", data)

    # outsider 创建会话应 403
    headers_outsider = {"Authorization": f"Bearer {ctx['outsider_token']}"}
    r = requests.post(
        f"{BASE_URL}/api/groups/{group_id}/sessions",
        json={"session_title": "Should Not Succeed"},
        headers=headers_outsider,
    )
    ok &= _log(r.status_code == 403, "非群成员创建会话被禁止（403）", {"status_code": r.status_code, "body": r.text})

    return ok


def _parse_dt(value: str | None) -> datetime | None:
    """
    将 ISO 字符串解析为 UTC naive datetime，便于与期望值比较。
    - 若带时区，则先转为 UTC 再去掉 tzinfo；
    - 若不带时区，则直接视为 naive。
    """
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        return None


def _close_dt(a: datetime | None, b: datetime | None, *, seconds: int = 1) -> bool:
    if a is None or b is None:
        return False
    return abs((a - b).total_seconds()) <= seconds


def scenario_create_session_with_explicit_times(ctx: Dict[str, Any]) -> bool:
    """
    成员在创建会话时显式传入 created_at/last_updated/ended_at：
    - 若传入 ended_at 且未显式传 is_active，则 is_active=False；
    - created_at/last_updated 与传入值在秒级上相等；
    - ended_at 至少非空。
    """
    ok = True
    group_id = ctx["group_id"]
    headers_member = {"Authorization": f"Bearer {ctx['member_token']}"}

    base_time = datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None)
    created_at = (base_time - timedelta(hours=2)).isoformat()
    last_updated = (base_time - timedelta(hours=1)).isoformat()
    ended_at = base_time.isoformat()

    r = requests.post(
        f"{BASE_URL}/api/groups/{group_id}/sessions",
        json={
            "session_title": "Session With Explicit Times",
            "created_at": created_at,
            "last_updated": last_updated,
            "ended_at": ended_at,
        },
        headers=headers_member,
    )
    if r.status_code != 201:
        return _log(
            False,
            "成员创建带显式时间的会话失败（期望 201）",
            {"status_code": r.status_code, "body": r.text},
        )

    data = r.json()
    created_resp = _parse_dt(data.get("created_at"))
    last_updated_resp = _parse_dt(data.get("last_updated"))
    created_expected = _parse_dt(created_at)
    last_updated_expected = _parse_dt(last_updated)

    ok = (
        data.get("group_id") == group_id
        and data.get("session_title") == "Session With Explicit Times"
        and data.get("status") == "ended"
        and data.get("ended_at") is not None
        and _close_dt(created_resp, created_expected)
        and _close_dt(last_updated_resp, last_updated_expected)
    )
    ok &= _log(ok, "成员创建带显式时间会话成功场景", data)
    return ok


def scenario_update_not_started_session_times(ctx: Dict[str, Any]) -> bool:
    """
    对一条「未开始」的会话（is_active=True/NULL, ended_at=None, created_at==last_updated）：
    - 显式修改 created_at/last_updated 应成功；
    - 返回的时间字段与传入值在秒级上对齐。
    """
    ok = True
    group_id = ctx["group_id"]
    headers_member = {"Authorization": f"Bearer {ctx['member_token']}"}

    # 新建一条未开始会话：业务创建接口默认 created_at == last_updated, ended_at=None
    r = requests.post(
        f"{BASE_URL}/api/groups/{group_id}/sessions",
        json={"session_title": "Not Started Can Change Time"},
        headers=headers_member,
    )
    if r.status_code != 201:
        return _log(
            False,
            "准备未开始会话失败（期望 201）",
            {"status_code": r.status_code, "body": r.text},
        )
    data = r.json()
    sid = data["id"]

    # 准备新的时间值
    now_utc = datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None)
    new_created = (now_utc - timedelta(days=1)).isoformat()
    new_last_updated = (now_utc - timedelta(minutes=10)).isoformat()

    r2 = requests.patch(
        f"{BASE_URL}/api/sessions/{sid}",
        json={
            "created_at": new_created,
            "last_updated": new_last_updated,
        },
        headers=headers_member,
    )
    if r2.status_code != 200:
        return _log(
            False,
            "未开始会话显式更新时间失败（期望 200）",
            {"status_code": r2.status_code, "body": r2.text},
        )

    data2 = r2.json()
    created_resp = _parse_dt(data2.get("created_at"))
    last_updated_resp = _parse_dt(data2.get("last_updated"))
    created_expected = _parse_dt(new_created)
    last_updated_expected = _parse_dt(new_last_updated)

    ok &= _log(
        _close_dt(created_resp, created_expected) and _close_dt(last_updated_resp, last_updated_expected),
        "未开始会话更新时间字段成功场景",
        data2,
    )
    return ok


def scenario_update_non_not_started_session_times_forbidden(ctx: Dict[str, Any]) -> bool:
    """
    对已结束的会话显式传入时间字段，应被后台拒绝（400），只允许未开始会话修改时间。
    """
    ok = True
    headers_member = {"Authorization": f"Bearer {ctx['member_token']}"}

    # 使用准备阶段已结束的会话 A
    sid = ctx["session_id_a"]

    r = requests.patch(
        f"{BASE_URL}/api/sessions/{sid}",
        json={
            "created_at": "2026-03-01T00:00:00Z",
            "last_updated": "2026-03-01T01:00:00Z",
        },
        headers=headers_member,
    )
    ok &= _log(
        r.status_code == 400,
        "对已结束会话显式更新时间字段被禁止（期望 400）",
        {"status_code": r.status_code, "body": r.text},
    )
    return ok


def scenario_update_session_success_forbidden_404(ctx: Dict[str, Any]) -> bool:
    ok = True
    session_id_b = ctx["session_id_b"]

    # 成员更新自己会话标题成功
    headers_member = {"Authorization": f"Bearer {ctx['member_token']}"}
    r = requests.patch(
        f"{BASE_URL}/api/sessions/{session_id_b}",
        json={"session_title": "Session B New Title"},
        headers=headers_member,
    )
    if r.status_code != 200:
        return _log(False, "成员更新会话标题失败（期望 200）", {"status_code": r.status_code, "body": r.text})
    data = r.json()
    ok &= _log(
        data.get("session_title") == "Session B New Title" and "status" in data and "ended_at" in data,
        "成员更新会话标题成功（响应包含状态字段）",
        data,
    )

    # outsider 更新任意会话应 403
    headers_outsider = {"Authorization": f"Bearer {ctx['outsider_token']}"}
    r = requests.patch(
        f"{BASE_URL}/api/sessions/{session_id_b}",
        json={"session_title": "Should Not Apply"},
        headers=headers_outsider,
    )
    ok &= _log(r.status_code == 403, "非群成员更新会话被禁止（403）", {"status_code": r.status_code, "body": r.text})

    # 更新不存在的会话应 404
    r = requests.patch(
        f"{BASE_URL}/api/sessions/nonexistent-session",
        json={"session_title": "whatever"},
        headers=headers_member,
    )
    ok &= _log(r.status_code == 404, "更新不存在会话返回 404", {"status_code": r.status_code, "body": r.text})

    return ok


def scenario_end_session_success_forbidden_404(ctx: Dict[str, Any]) -> bool:
    ok = True

    # 重新创建一个进行中会话 C，然后结束它
    headers_member = {"Authorization": f"Bearer {ctx['member_token']}"}
    r = requests.post(
        f"{BASE_URL}/api/groups/{ctx['group_id']}/sessions",
        json={"session_title": "Session C To End"},
        headers=headers_member,
    )
    if r.status_code != 201:
        return _log(False, "准备会话 C 失败（期望 201）", {"status_code": r.status_code, "body": r.text})
    session_c = r.json()
    session_id_c = session_c["id"]

    r = requests.post(
        f"{BASE_URL}/api/sessions/{session_id_c}/end",
        headers=headers_member,
    )
    if r.status_code != 200:
        return _log(False, "结束会话 C 失败（期望 200）", {"status_code": r.status_code, "body": r.text})
    data = r.json()

    ok &= _log(
        data.get("status") == "ended" and data.get("ended_at") is not None,
        "结束会话后响应中 status=ended 且 ended_at 非空",
        data,
    )

    # outsider 结束会话应 403
    headers_outsider = {"Authorization": f"Bearer {ctx['outsider_token']}"}
    r = requests.post(
        f"{BASE_URL}/api/sessions/{session_id_c}/end",
        headers=headers_outsider,
    )
    ok &= _log(r.status_code == 403, "非群成员结束会话被禁止（403）", {"status_code": r.status_code, "body": r.text})

    # 结束不存在的会话应 404
    r = requests.post(
        f"{BASE_URL}/api/sessions/nonexistent-session/end",
        headers=headers_member,
    )
    ok &= _log(r.status_code == 404, "结束不存在会话返回 404", {"status_code": r.status_code, "body": r.text})

    return ok


def scenario_transcripts_success_forbidden_404(ctx: Dict[str, Any]) -> bool:
    ok = True
    session_id_b = ctx["session_id_b"]

    # 成员查看会话 B 的转写（可能为空 list，但应 200）
    headers_member = {"Authorization": f"Bearer {ctx['member_token']}"}
    r = requests.get(
        f"{BASE_URL}/api/sessions/{session_id_b}/transcripts",
        headers=headers_member,
    )
    if r.status_code != 200:
        return _log(False, "成员查看会话转写失败（期望 200）", {"status_code": r.status_code, "body": r.text})
    try:
        data = r.json()
    except Exception:
        return _log(False, "成员查看会话转写返回非 JSON", {"body": r.text})
    ok &= _log(isinstance(data, list), "成员查看会话转写返回列表", data)

    # outsider 查看同一会话应 403
    headers_outsider = {"Authorization": f"Bearer {ctx['outsider_token']}"}
    r = requests.get(
        f"{BASE_URL}/api/sessions/{session_id_b}/transcripts",
        headers=headers_outsider,
    )
    ok &= _log(r.status_code == 403, "非群成员查看会话转写被禁止（403）", {"status_code": r.status_code, "body": r.text})

    # 查看不存在的会话转写应 404
    r = requests.get(
        f"{BASE_URL}/api/sessions/nonexistent-session/transcripts",
        headers=headers_member,
    )
    ok &= _log(r.status_code == 404, "查看不存在会话转写返回 404", {"status_code": r.status_code, "body": r.text})

    return ok


def run_all() -> bool:
    print("=== 开始 App Sessions 会话接口契约测试 ===")
    ctx: Dict[str, Any] = {}

    ok = True
    ok &= setup_group_and_sessions(ctx)
    if not ok:
        print("准备阶段失败，后续场景跳过 ❌")
        return False

    ok &= scenario_list_sessions_response_schema(ctx)
    ok &= scenario_create_session_success_and_forbidden(ctx)
    ok &= scenario_create_session_with_explicit_times(ctx)
    ok &= scenario_update_not_started_session_times(ctx)
    ok &= scenario_update_non_not_started_session_times_forbidden(ctx)
    ok &= scenario_update_session_success_forbidden_404(ctx)
    ok &= scenario_end_session_success_forbidden_404(ctx)
    ok &= scenario_transcripts_success_forbidden_404(ctx)

    print("\n=== App Sessions 测试结果: {} ===".format("全部通过 ✅" if ok else "有失败 ❌"))
    return ok


if __name__ == "__main__":
    import sys

    sys.exit(0 if run_all() else 1)

