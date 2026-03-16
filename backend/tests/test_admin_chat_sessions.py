from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import requests

BASE_URL = "http://127.0.0.1:8000"
RUN_ID = uuid.uuid4().hex[:6]

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
    # 与 /api/auth/register 的密码规则保持一致：必须为 4 位
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

    group_detail = create_group(access_token, name=f"Admin Session Test Group {RUN_ID}")
    group_id = group_detail["group"]["id"]
    ctx["group_id"] = group_id

    # 创建两个会话
    s1 = create_session(access_token, group_id, title="First Session")
    s2 = create_session(access_token, group_id, title="Second Session")
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

    items = data.get("items", [])
    ids = {item["id"] for item in items}
    ok = ok and (ctx["session_id_1"] in ids or ctx["session_id_2"] in ids)

    # 校验新增字段 group_name：字段存在且类型为 str 或 None
    for item in items:
        if "group_name" not in item:
            ok = False
            break
        if item["group_name"] is not None and not isinstance(item["group_name"], str):
            ok = False
            break

    return _log(ok, "admin 基础分页列出会话场景（含 group_name）", data)


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
    items = data.get("items", [])
    ok &= _log(
        all(item["group_id"] == group_id for item in items) and len(items) >= 2,
        "admin 按 group_id 过滤会话场景",
        data,
    )

    # 在按 group_id 过滤结果中，至少有一条记录的 group_name 非空，用于简单验证群组名称回填正确
    has_non_empty_group_name = any(
        (item.get("group_name") is not None) and isinstance(item.get("group_name"), str) and item["group_name"] != ""
        for item in items
    )
    ok &= _log(
        has_non_empty_group_name,
        "admin 按 group_id 过滤结果包含至少一条带有效 group_name 的会话",
        data,
    )

    # 按 status=not_started 过滤（应该只包含未结束的会话）
    r2 = requests.get(
        f"{BASE_URL}/api/admin/chat-sessions",
        params={"group_id": group_id, "status": "not_started", "page": 1, "page_size": 20},
        headers=ADMIN_HEADERS,
    )
    if r2.status_code != 200:
        return _log(False, "admin 按 status=not_started 过滤会话失败（期望 200）", {"status_code": r2.status_code, "body": r2.text})
    data2 = r2.json()
    ids2 = {item["id"] for item in data2["items"]}
    ok &= _log(
        ctx["session_id_2"] in ids2 and ctx["session_id_1"] not in ids2,
        "admin 按 status=not_started 过滤会话场景",
        data2,
    )

    # 按 status=ended 过滤（应该包含已结束的会话）
    r3 = requests.get(
        f"{BASE_URL}/api/admin/chat-sessions",
        params={"group_id": group_id, "status": "ended", "page": 1, "page_size": 20},
        headers=ADMIN_HEADERS,
    )
    if r3.status_code != 200:
        return _log(False, "admin 按 status=ended 过滤会话失败（期望 200）", {"status_code": r3.status_code, "body": r3.text})
    data3 = r3.json()
    ids3 = {item["id"] for item in data3["items"]}
    ok &= _log(
        ctx["session_id_1"] in ids3,
        "admin 按 status=ended 过滤会话场景",
        data3,
    )

    # 按 session_title 模糊搜索
    r4 = requests.get(
        f"{BASE_URL}/api/admin/chat-sessions",
        params={"session_title": "First Session", "page": 1, "page_size": 10},
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


# ---------- 场景：创建时间 / 更新时间 / 结束时间范围过滤 ----------


def scenario_admin_chat_sessions_time_filters(ctx: Dict[str, Any]) -> bool:
  """
  使用 created_from/created_to、last_updated_from/last_updated_to、ended_from/ended_to
  对同一 group 下的会话做时间范围过滤，验证：
  1）在一个宽松时间窗口内可以查到准备阶段产生的会话；
  2）在窗口之外查不到这些会话；
  3）使用 ended_* 仅命中已结束的会话。
  """
  group_id = ctx["group_id"]

  r = requests.get(
      f"{BASE_URL}/api/admin/chat-sessions",
      params={"group_id": group_id, "page": 1, "page_size": 20},
      headers=ADMIN_HEADERS,
  )
  if r.status_code != 200:
      return _log(
          False,
          "admin 基础列表用于时间过滤准备失败（期望 200）",
          {"status_code": r.status_code, "body": r.text},
      )

  data = r.json()
  items = data.get("items", [])
  if not items:
      return _log(False, "时间过滤场景：指定 group 下没有任何会话", data)

  def _parse(ts: str | None) -> datetime | None:
      if not ts:
          return None
      try:
          return datetime.fromisoformat(ts.replace("Z", "+00:00"))
      except Exception as exc:  # noqa: BLE001
          _log(False, "解析时间字符串失败", {"value": ts, "error": str(exc)})
          return None

  created_list = [_parse(i.get("created_at")) for i in items]
  created_list = [d for d in created_list if d is not None]

  if not created_list:
      return _log(False, "时间过滤场景：无法解析任何 created_at", items)

  earliest_created = min(created_list)
  latest_created = max(created_list)

  # ---- created_at 窗口：包含所有会话 ----
  window_start = (earliest_created - timedelta(minutes=5)).isoformat()
  window_end = (latest_created + timedelta(minutes=5)).isoformat()

  r_in = requests.get(
      f"{BASE_URL}/api/admin/chat-sessions",
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
          "admin 使用 created_from/created_to 过滤会话失败（期望 200）",
          {"status_code": r_in.status_code, "body": r_in.text},
      )
  data_in = r_in.json()
  original_ids = {i["id"] for i in items}
  returned_ids_in = {i["id"] for i in data_in.get("items", [])}
  ok = original_ids.issubset(returned_ids_in)
  ok &= _log(
      ok,
      "admin created_at 窗口内包含准备阶段创建的会话场景",
      {"window_start": window_start, "window_end": window_end, "returned": data_in},
  )

  # ---- created_at 窗口：在所有记录之后，应查不到这些会话 ----
  future_start = (latest_created + timedelta(hours=1)).isoformat()
  future_end = (latest_created + timedelta(hours=2)).isoformat()
  r_out = requests.get(
      f"{BASE_URL}/api/admin/chat-sessions",
      params={
          "group_id": group_id,
          "created_from": future_start,
          "created_to": future_end,
          "page": 1,
          "page_size": 50,
      },
      headers=ADMIN_HEADERS,
  )
  if r_out.status_code != 200:
      return _log(
          False,
          "admin 使用 created_from/created_to（未来窗口）过滤失败（期望 200）",
          {"status_code": r_out.status_code, "body": r_out.text},
      )
  data_out = r_out.json()
  returned_ids_out = {i["id"] for i in data_out.get("items", [])}
  ok &= _log(
      original_ids.isdisjoint(returned_ids_out),
      "admin created_at 未来窗口不包含准备阶段会话场景",
      {"future_start": future_start, "future_end": future_end, "returned": data_out},
  )

  # ---- ended_at 窗口：仅命中已结束的会话（如果存在）----
  ended_times = [_parse(i.get("ended_at")) for i in items]
  ended_times = [d for d in ended_times if d is not None]
  if ended_times:
      earliest_ended = min(ended_times)
      latest_ended = max(ended_times)
      ended_start = (earliest_ended - timedelta(minutes=5)).isoformat()
      ended_end = (latest_ended + timedelta(minutes=5)).isoformat()

      r_ended = requests.get(
          f"{BASE_URL}/api/admin/chat-sessions",
          params={
              "group_id": group_id,
              "ended_from": ended_start,
              "ended_to": ended_end,
              "page": 1,
              "page_size": 50,
          },
          headers=ADMIN_HEADERS,
      )
      if r_ended.status_code != 200:
          return _log(
              False,
              "admin 使用 ended_from/ended_to 过滤会话失败（期望 200）",
              {"status_code": r_ended.status_code, "body": r_ended.text},
          )
      data_ended = r_ended.json()
      # 返回结果中的会话，其 ended_at 都应非空
      ok &= _log(
          all(item.get("ended_at") for item in data_ended.get("items", [])),
          "admin 使用 ended_from/ended_to 仅命中已结束会话场景",
          data_ended,
      )

  return ok


# ---------- 场景：管理员创建会话（未开始 / 进行中） ----------


def scenario_admin_create_chat_session_success_not_started() -> bool:
    """
    管理员为指定群组创建一条“未开始”的会话（is_active=None, ended_at=None）。
    """
    info = register_and_login("admin_create_not_started_owner")
    access_token = info["access_token"]
    group_detail = create_group(access_token, name=f"Admin New Group Not Started {RUN_ID}")
    group_id = group_detail["group"]["id"]

    r = requests.post(
        f"{BASE_URL}/api/admin/chat-sessions",
        json={"group_id": group_id, "session_title": "Admin Create Not Started Session"},
        headers=ADMIN_HEADERS,
    )
    if r.status_code != 201:
        return _log(
            False,
            "admin 创建未开始会话失败（期望 201）",
            {"status_code": r.status_code, "body": r.text},
        )
    data = r.json()
    ok = (
        data.get("group_id") == group_id
        and data.get("session_title") == "Admin Create Not Started Session"
        and data.get("status") == "not_started"
        and data.get("ended_at") is None
    )
    ok &= _log(ok, "admin 创建未开始会话成功场景", data)

    # 再通过列表接口校验可见性
    r_list = requests.get(
        f"{BASE_URL}/api/admin/chat-sessions",
        params={"group_id": group_id, "page": 1, "page_size": 10},
        headers=ADMIN_HEADERS,
    )
    if r_list.status_code != 200:
        return _log(
            False,
            "admin 创建未开始会话后列表查询失败（期望 200）",
            {"status_code": r_list.status_code, "body": r_list.text},
        )
    data_list = r_list.json()
    ids = {item["id"] for item in data_list.get("items", [])}
    ok &= _log(
        data["id"] in ids,
        "admin 创建未开始会话后列表校验场景",
        data_list,
    )
    return ok


def scenario_admin_create_chat_session_success_ongoing() -> bool:
    """
    管理员创建一条“进行中”的会话（is_active=True）。
    """
    info = register_and_login("admin_create_ongoing_owner")
    access_token = info["access_token"]
    group_detail = create_group(access_token, name=f"Admin New Group Ongoing {RUN_ID}")
    group_id = group_detail["group"]["id"]

    r = requests.post(
        f"{BASE_URL}/api/admin/chat-sessions",
        json={
            "group_id": group_id,
            "session_title": "Admin Create Ongoing Session",
            "status": "ongoing",
        },
        headers=ADMIN_HEADERS,
    )
    if r.status_code != 201:
        return _log(
            False,
            "admin 创建进行中会话失败（期望 201）",
            {"status_code": r.status_code, "body": r.text},
        )
    data = r.json()
    ok = (
        data.get("group_id") == group_id
        and data.get("session_title") == "Admin Create Ongoing Session"
        and data.get("status") == "ongoing"
        and data.get("ended_at") is None
    )
    ok &= _log(ok, "admin 创建进行中会话成功场景", data)
    return ok


# ---------- 场景：管理员创建/更新会话时显式控制时间字段 ----------


def _parse_dt(value: str | None) -> datetime | None:
    """
    将 ISO 字符串解析为 UTC naive datetime，统一比较口径：
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
    except Exception as exc:  # noqa: BLE001
        _log(False, "解析时间字符串失败(_parse_dt)", {"value": value, "error": str(exc)})
        return None


def scenario_admin_create_chat_session_with_explicit_times() -> bool:
    """
    管理员创建会话时显式传入 created_at/last_updated/ended_at，验证后台按传入值落库：
    - 若传入 ended_at 且未显式传 is_active，则 is_active=False。
    - created_at/last_updated 与传入值在秒级上相等；
    - ended_at 至少非空（具体值可能受数据库时区类型影响，这里不做精确校验）。
    """
    info = register_and_login("admin_create_with_times_owner")
    access_token = info["access_token"]
    group_detail = create_group(access_token, name=f"Admin New Group With Times {RUN_ID}")
    group_id = group_detail["group"]["id"]

    # 使用 UTC 时间，但传给后端时用 ISO 字符串（不额外拼接 "Z"，避免出现 "+00:00Z" 这种非法格式）
    base_time = datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None)
    created_at = (base_time - timedelta(hours=2)).isoformat()
    last_updated = (base_time - timedelta(hours=1)).isoformat()
    ended_at = base_time.isoformat()

    r = requests.post(
        f"{BASE_URL}/api/admin/chat-sessions",
        json={
            "group_id": group_id,
            "session_title": "Admin Create Session With Times",
            "created_at": created_at,
            "last_updated": last_updated,
            "ended_at": ended_at,
        },
        headers=ADMIN_HEADERS,
    )
    if r.status_code != 201:
        return _log(
            False,
            "admin 创建带显式时间的会话失败（期望 201）",
            {"status_code": r.status_code, "body": r.text},
        )

    data = r.json()
    created_resp = _parse_dt(data.get("created_at"))
    last_updated_resp = _parse_dt(data.get("last_updated"))
    # ended_at 可能是 timestamptz，返回值可能带 Z，这里只校验非空
    ended_value = data.get("ended_at")

    created_expected = _parse_dt(created_at)
    last_updated_expected = _parse_dt(last_updated)

    def _close(a: datetime | None, b: datetime | None) -> bool:
        if a is None or b is None:
            return False
        return abs((a - b).total_seconds()) < 1

    ok = (
        data.get("group_id") == group_id
        and data.get("status") == "ended"  # 传了 ended_at 且未指定 status，默认视为已结束
        and _close(created_resp, created_expected)
        and _close(last_updated_resp, last_updated_expected)
        and ended_value is not None
    )
    ok &= _log(ok, "admin 创建带显式时间会话成功场景", data)
    return ok


def scenario_admin_update_chat_session_times(ctx: Dict[str, Any]) -> bool:
    """
    管理员更新会话时显式修改 created_at/last_updated：
    - 传入 last_updated 时，应使用传入值而不是自动 NOW()。
    """
    sid = ctx["session_id_2"]

    # 同样使用 UTC naive 时间，避免传入带重复时区信息的字符串
    now_utc = datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None)
    new_created = (now_utc - timedelta(days=1)).isoformat()
    new_last_updated = (now_utc - timedelta(minutes=30)).isoformat()

    r = requests.patch(
        f"{BASE_URL}/api/admin/chat-sessions/{sid}",
        json={
            "created_at": new_created,
            "last_updated": new_last_updated,
        },
        headers=ADMIN_HEADERS,
    )
    if r.status_code != 200:
        return _log(
            False,
            "admin 显式更新 created_at/last_updated 失败（期望 200）",
            {"status_code": r.status_code, "body": r.text},
        )

    data = r.json()
    created_resp = _parse_dt(data.get("created_at"))
    last_updated_resp = _parse_dt(data.get("last_updated"))
    created_expected = _parse_dt(new_created)
    last_updated_expected = _parse_dt(new_last_updated)

    def _close(a: datetime | None, b: datetime | None) -> bool:
        if a is None or b is None:
            return False
        return abs((a - b).total_seconds()) < 1

    ok = _close(created_resp, created_expected) and _close(last_updated_resp, last_updated_expected)
    ok &= _log(ok, "admin 显式更新 created_at/last_updated 场景", data)
    return ok


# ---------- 场景：status 三态过滤 ----------


def scenario_admin_list_chat_sessions_status_filters_with_status_param(ctx: Dict[str, Any]) -> bool:
    """
    使用 status=not_started/ongoing/ended 三态过滤会话。
    利用准备阶段的 ctx（包含已结束/进行中会话），并额外创建一条未开始会话。
    """
    ok = True
    group_id = ctx["group_id"]

    # 额外创建一条未开始会话：通过 admin 创建，created_at == last_updated 且未结束
    r_create_not_started = requests.post(
        f"{BASE_URL}/api/admin/chat-sessions",
        json={
            "group_id": group_id,
            "session_title": "Admin Status Test Not Started Session",
        },
        headers=ADMIN_HEADERS,
    )
    if r_create_not_started.status_code != 201:
        return _log(
            False,
            "status 三态场景：admin 创建未开始会话失败（期望 201）",
            {"status_code": r_create_not_started.status_code, "body": r_create_not_started.text},
        )
    created_not_started = r_create_not_started.json()
    not_started_id = created_not_started["id"]

    # not_started：通过 status=not_started + group_id 应至少包含该会话
    r_list = requests.get(
        f"{BASE_URL}/api/admin/chat-sessions",
        params={"group_id": group_id, "session_title": "Admin Status Test", "page": 1, "page_size": 20},
        headers=ADMIN_HEADERS,
    )
    r_not = requests.get(
        f"{BASE_URL}/api/admin/chat-sessions",
        params={"group_id": group_id, "status": "not_started", "page": 1, "page_size": 20},
        headers=ADMIN_HEADERS,
    )
    if r_not.status_code != 200:
        return _log(
            False,
            "admin 按 status=not_started 过滤会话失败（期望 200）",
            {"status_code": r_not.status_code, "body": r_not.text},
        )
    data_not = r_not.json()
    ids_not = {item["id"] for item in data_not.get("items", [])}
    ok &= _log(
        not_started_id in ids_not,
        "admin 按 status=not_started 过滤会话场景",
        data_not,
    )

    # ongoing：将准备阶段的 session_id_2 设为进行中
    r_update_ongoing = requests.patch(
        f"{BASE_URL}/api/admin/chat-sessions/{ctx['session_id_2']}",
        json={"session_title": "Ongoing Session Updated", "status": "ongoing"},
        headers=ADMIN_HEADERS,
    )
    if r_update_ongoing.status_code != 200:
        return _log(
            False,
            "status 三态场景：将 session_id_2 标记为进行中失败（期望 200）",
            {"status_code": r_update_ongoing.status_code, "body": r_update_ongoing.text},
        )

    r_ongoing = requests.get(
        f"{BASE_URL}/api/admin/chat-sessions",
        params={"group_id": group_id, "status": "ongoing", "page": 1, "page_size": 20},
        headers=ADMIN_HEADERS,
    )
    if r_ongoing.status_code != 200:
        return _log(
            False,
            "admin 按 status=ongoing 过滤会话失败（期望 200）",
            {"status_code": r_ongoing.status_code, "body": r_ongoing.text},
        )
    data_ongoing = r_ongoing.json()
    ids_ongoing = {item["id"] for item in data_ongoing.get("items", [])}
    ok &= _log(
        ctx["session_id_2"] in ids_ongoing,
        "admin 按 status=ongoing 过滤会话场景",
        data_ongoing,
    )

    # ended：应至少包含准备阶段结束的 session_id_1
    r_ended = requests.get(
        f"{BASE_URL}/api/admin/chat-sessions",
        params={"group_id": group_id, "status": "ended", "page": 1, "page_size": 20},
        headers=ADMIN_HEADERS,
    )
    if r_ended.status_code != 200:
        return _log(
            False,
            "admin 按 status=ended 过滤会话失败（期望 200）",
            {"status_code": r_ended.status_code, "body": r_ended.text},
        )
    data_ended = r_ended.json()
    ids_ended = {item["id"] for item in data_ended.get("items", [])}
    ok &= _log(
        ctx["session_id_1"] in ids_ended,
        "admin 按 status=ended 过滤会话场景",
        data_ended,
    )

    return ok


def scenario_admin_list_chat_sessions_invalid_status_param() -> bool:
    """
    非法的 status 参数应返回 400。
    """
    r = requests.get(
        f"{BASE_URL}/api/admin/chat-sessions",
        params={"status": "invalid_status"},
        headers=ADMIN_HEADERS,
    )
    ok = r.status_code == 400
    return _log(ok, "admin 使用非法 status 参数返回 400 场景", {"status_code": r.status_code, "body": r.text})

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
    new_title = "Admin Renamed Session"

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
            "status": "ended",
            "ended_at": "2026-03-04T12:00:00Z",
        },
        headers=ADMIN_HEADERS,
    )
    if r.status_code != 200:
        return _log(False, "admin 更新会话 status/ended_at 失败（期望 200）", {"status_code": r.status_code, "body": r.text})

    data = r.json()
    ok = (data.get("status") == "ended") and (data.get("ended_at") is not None)
    ok &= _log(ok, "admin 更新会话 status/ended_at 场景", data)

    # 再按 status=ended 过滤时应能看到该会话
    r2 = requests.get(
        f"{BASE_URL}/api/admin/chat-sessions",
        params={"group_id": ctx["group_id"], "status": "ended", "page": 1, "page_size": 20},
        headers=ADMIN_HEADERS,
    )
    if r2.status_code != 200:
        return _log(False, "admin 更新 flags 后按 status=ended 过滤失败（期望 200）", {"status_code": r2.status_code, "body": r2.text})
    data2 = r2.json()
    ids2 = {item["id"] for item in data2["items"]}
    ok &= _log(
        sid in ids2,
        "admin 更新 flags 后按 status=ended 过滤包含该会话场景",
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
    group_detail = create_group(access_token, name=f"Temp Session Group {RUN_ID}")
    group_id = group_detail["group"]["id"]
    session_detail = create_session(access_token, group_id, title="Temp Session")
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


# ---------- 场景：批量删除会话 ----------


def scenario_admin_batch_delete_chat_sessions_success() -> bool:
    info = register_and_login("batch_del_sess")
    access_token = info["access_token"]
    group_detail = create_group(access_token, name=f"Batch Delete Sessions Group {RUN_ID}")
    group_id = group_detail["group"]["id"]
    s1 = create_session(access_token, group_id, title="Batch Delete Session 1")
    s2 = create_session(access_token, group_id, title="Batch Delete Session 2")
    ids = [s1["id"], s2["id"]]

    r = requests.post(
        f"{BASE_URL}/api/admin/chat-sessions/batch-delete",
        json={"ids": ids},
        headers=ADMIN_HEADERS,
    )
    if r.status_code != 200:
        return _log(False, "admin 批量删除会话失败（期望 200）", {"status_code": r.status_code, "body": r.text})
    data = r.json()
    if data.get("deleted") != 2:
        return _log(False, "admin 批量删除会话应返回 deleted=2", data)

    for sid in ids:
        r2 = requests.get(f"{BASE_URL}/api/admin/chat-sessions/{sid}", headers=ADMIN_HEADERS)
        if r2.status_code != 404:
            return _log(False, f"批量删除后会话 {sid} 应 404", {"status_code": r2.status_code})
    return _log(True, "admin 批量删除会话成功场景")


def scenario_admin_batch_delete_chat_sessions_empty_ids() -> bool:
    r = requests.post(
        f"{BASE_URL}/api/admin/chat-sessions/batch-delete",
        json={"ids": []},
        headers=ADMIN_HEADERS,
    )
    ok = r.status_code == 422
    return _log(ok, "admin 批量删除会话 ids 为空返回 422 场景", {"status_code": r.status_code, "body": r.text})


def scenario_admin_batch_delete_chat_sessions_partial() -> bool:
    info = register_and_login("batch_del_sess_partial")
    access_token = info["access_token"]
    group_detail = create_group(access_token, name=f"Batch Delete Sessions Partial Group {RUN_ID}")
    group_id = group_detail["group"]["id"]
    s = create_session(access_token, group_id, title="Batch Delete Session Partial")
    r = requests.post(
        f"{BASE_URL}/api/admin/chat-sessions/batch-delete",
        json={"ids": [s["id"], "non-existent-session-uuid-1111"]},
        headers=ADMIN_HEADERS,
    )
    if r.status_code != 200:
        return _log(False, "admin 批量删除会话（含不存在的 id）应返回 200", {"status_code": r.status_code, "body": r.text})
    data = r.json()
    if data.get("deleted") != 1:
        return _log(False, "admin 批量删除会话仅删除存在的 1 条", data)
    return _log(True, "admin 批量删除会话部分存在部分不存在场景")


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

    # 不带 X-Admin-Token 调用创建会话接口
    r_create = requests.post(
        f"{BASE_URL}/api/admin/chat-sessions",
        json={
            "group_id": "g_dummy",
            "session_title": "no-token-session",
        },
    )
    ok &= _log(
        r_create.status_code == 403,
        "缺少 X-Admin-Token 调用 admin 创建会话接口被禁止场景",
        {"status_code": r_create.status_code, "body": r_create.text},
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

    # 带错误 token 调用创建会话接口
    r_create_wrong = requests.post(
        f"{BASE_URL}/api/admin/chat-sessions",
        json={
            "group_id": "g_dummy",
            "session_title": "wrong-token-session",
        },
        headers={"X-Admin-Token": "WrongKey"},
    )
    ok &= _log(
        r_create_wrong.status_code == 403,
        "错误 X-Admin-Token 调用 admin 创建会话接口被禁止场景",
        {"status_code": r_create_wrong.status_code, "body": r_create_wrong.text},
    )

    return ok


# ---------- 总入口 ----------


def run_all() -> bool:
    print("=== 开始 Admin Chat Sessions 后台会话接口测试 ===")
    ctx: Dict[str, Any] = {}

    ok = True
    ok &= setup_chat_sessions(ctx)
    ok &= scenario_admin_list_chat_sessions_basic(ctx)
    ok &= scenario_admin_list_chat_sessions_filters(ctx)
    ok &= scenario_admin_chat_sessions_time_filters(ctx)
    ok &= scenario_admin_create_chat_session_success_not_started()
    ok &= scenario_admin_create_chat_session_success_ongoing()
    ok &= scenario_admin_create_chat_session_with_explicit_times()
    ok &= scenario_admin_list_chat_sessions_status_filters_with_status_param(ctx)
    ok &= scenario_admin_list_chat_sessions_invalid_status_param()
    ok &= scenario_admin_get_chat_session_detail(ctx)
    ok &= scenario_admin_get_chat_session_not_found()
    ok &= scenario_admin_update_chat_session_title(ctx)
    ok &= scenario_admin_update_chat_session_flags(ctx)
    ok &= scenario_admin_update_chat_session_times(ctx)
    ok &= scenario_admin_update_chat_session_no_fields(ctx)
    ok &= scenario_admin_delete_chat_session_success(ctx)
    ok &= scenario_admin_delete_chat_session_not_found()
    ok &= scenario_admin_batch_delete_chat_sessions_success()
    ok &= scenario_admin_batch_delete_chat_sessions_empty_ids()
    ok &= scenario_admin_batch_delete_chat_sessions_partial()
    ok &= scenario_admin_missing_or_wrong_token()

    print("\n=== Admin Chat Sessions 测试结果: {} ===".format("全部通过 ✅" if ok else "有失败 ❌"))
    return ok


if __name__ == "__main__":
    import sys
    sys.exit(0 if run_all() else 1)

