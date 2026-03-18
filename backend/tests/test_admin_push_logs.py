from __future__ import annotations

import uuid
from typing import Any, Dict, Tuple

import requests

BASE_URL = "http://127.0.0.1:8000"
RUN_ID = uuid.uuid4().hex[:6]
ADMIN_HEADERS = {"X-Admin-Token": "TestAdminKey123"}


def _log(ok: bool, message: str, extra: Any = None) -> bool:
    print(f"{'✅' if ok else '❌'} {message}")
    if not ok and extra is not None:
        print("   详情:", extra)
    return ok


def _register_and_login(label: str) -> Tuple[Dict[str, Any], str]:
    email = f"apl_{label}_{uuid.uuid4().hex[:6]}@example.com"
    r = requests.post(f"{BASE_URL}/api/auth/register", json={
        "name": f"APL {label} {RUN_ID}",
        "email": email,
        "password": "1234",
        "device_token": f"dev-{uuid.uuid4().hex[:8]}",
    })
    r.raise_for_status()
    user = r.json()
    token = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": email, "password": "1234"}).json()["access_token"]
    return user, token


def _auth(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _setup_session(label: str) -> Tuple[Dict, str, str, str]:
    leader, token = _register_and_login(f"Leader{label}")

    r = requests.post(f"{BASE_URL}/api/groups", headers=_auth(token),
                      json={"name": f"APL Group {label} {RUN_ID}"})
    r.raise_for_status()
    group_id = r.json()["group"]["id"]

    r2 = requests.post(f"{BASE_URL}/api/groups/{group_id}/sessions",
                       headers=_auth(token), json={"session_title": f"APL Session {label}"})
    r2.raise_for_status()
    session_id = r2.json()["id"]

    requests.post(f"{BASE_URL}/api/sessions/{session_id}/start",
                  headers=_auth(token)).raise_for_status()

    return leader, token, group_id, session_id


def _create_log(**kwargs) -> Dict[str, Any]:
    r = requests.post(f"{BASE_URL}/api/admin/push-logs/",
                      headers=ADMIN_HEADERS, json=kwargs)
    r.raise_for_status()
    return r.json()


def _create_discussion_state(session_id: str) -> str:
    r = requests.post(f"{BASE_URL}/api/admin/discussion-states/",
                      headers=ADMIN_HEADERS,
                      json={"session_id": session_id, "state_type": "low_participation"})
    r.raise_for_status()
    return r.json()["id"]


# ════════════════════════════════════════════════════
# POST /api/admin/push-logs/
# ════════════════════════════════════════════════════

def scenario_create_no_token() -> bool:
    r = requests.post(f"{BASE_URL}/api/admin/push-logs/",
                      json={"session_id": "x", "target_user_id": "y", "push_channel": "app"})
    return _log(r.status_code == 403, "POST /admin/push-logs 无 Token 返回 403", {"status": r.status_code})


def scenario_create_wrong_token() -> bool:
    r = requests.post(f"{BASE_URL}/api/admin/push-logs/",
                      headers={"X-Admin-Token": "wrong"},
                      json={"session_id": "x", "target_user_id": "y", "push_channel": "app"})
    return _log(r.status_code == 403, "POST /admin/push-logs 错误 Token 返回 403", {"status": r.status_code})


def scenario_create_session_not_found() -> bool:
    _, token = _register_and_login("SessNF")
    r = requests.post(f"{BASE_URL}/api/admin/push-logs/",
                      headers=ADMIN_HEADERS,
                      json={"session_id": "non-exist-session",
                            "target_user_id": "any",
                            "push_channel": "app"})
    return _log(r.status_code == 404, "POST /admin/push-logs session 不存在返回 404", {"status": r.status_code})


def scenario_create_user_not_found() -> bool:
    leader, _, _, session_id = _setup_session("UserNF")
    r = requests.post(f"{BASE_URL}/api/admin/push-logs/",
                      headers=ADMIN_HEADERS,
                      json={"session_id": session_id,
                            "target_user_id": "non-exist-user",
                            "push_channel": "app"})
    return _log(r.status_code == 404, "POST /admin/push-logs 用户不存在返回 404", {"status": r.status_code})


def scenario_create_invalid_channel() -> bool:
    leader, _, _, session_id = _setup_session("InvalidChan")
    r = requests.post(f"{BASE_URL}/api/admin/push-logs/",
                      headers=ADMIN_HEADERS,
                      json={"session_id": session_id,
                            "target_user_id": leader["id"],
                            "push_channel": "sms"})
    return _log(r.status_code == 400, "POST /admin/push-logs 非法 push_channel 返回 400", {"status": r.status_code})


def scenario_create_invalid_delivery_status() -> bool:
    leader, _, _, session_id = _setup_session("InvalidDS")
    r = requests.post(f"{BASE_URL}/api/admin/push-logs/",
                      headers=ADMIN_HEADERS,
                      json={"session_id": session_id,
                            "target_user_id": leader["id"],
                            "push_channel": "app",
                            "delivery_status": "unknown"})
    return _log(r.status_code == 400, "POST /admin/push-logs 非法 delivery_status 返回 400", {"status": r.status_code})


def scenario_create_state_not_found() -> bool:
    leader, _, _, session_id = _setup_session("StateNF")
    r = requests.post(f"{BASE_URL}/api/admin/push-logs/",
                      headers=ADMIN_HEADERS,
                      json={"session_id": session_id,
                            "target_user_id": leader["id"],
                            "push_channel": "app",
                            "state_id": "non-exist-state"})
    return _log(r.status_code == 404, "POST /admin/push-logs state 不存在返回 404", {"status": r.status_code})


def scenario_create_minimal() -> bool:
    """只传必填字段（session_id, target_user_id, push_channel）"""
    leader, _, _, session_id = _setup_session("Minimal")
    r = requests.post(f"{BASE_URL}/api/admin/push-logs/",
                      headers=ADMIN_HEADERS,
                      json={"session_id": session_id,
                            "target_user_id": leader["id"],
                            "push_channel": "app"})
    if r.status_code != 201:
        return _log(False, "POST /admin/push-logs 最小字段创建失败", r.text)
    data = r.json()
    ok = data.get("delivery_status") == "pending"  # 默认值
    ok &= data.get("id", "").startswith("pl")
    return _log(ok, "POST /admin/push-logs 最小字段创建成功，默认 delivery_status=pending", data)


def scenario_create_full_fields() -> bool:
    """传全部字段，含 state_id、jpush_message_id 等"""
    leader, _, _, session_id = _setup_session("Full")
    state_id = _create_discussion_state(session_id)

    r = requests.post(f"{BASE_URL}/api/admin/push-logs/",
                      headers=ADMIN_HEADERS,
                      json={"session_id": session_id,
                            "target_user_id": leader["id"],
                            "push_channel": "glasses",
                            "state_id": state_id,
                            "push_content": "请积极发言",
                            "jpush_message_id": f"jmsg-{RUN_ID}",
                            "delivery_status": "delivered"})
    if r.status_code != 201:
        return _log(False, "POST /admin/push-logs 全字段创建失败", r.text)
    data = r.json()
    required = ["id", "session_id", "state_id", "state_type", "target_user_id",
                "target_user_name", "push_content", "push_channel",
                "jpush_message_id", "delivery_status", "triggered_at"]
    ok = all(f in data for f in required)
    ok &= data.get("state_type") == "low_participation"
    ok &= data.get("push_channel") == "glasses"
    return _log(ok, "POST /admin/push-logs 全字段创建，state_type JOIN 正确", data)


def scenario_create_channels() -> bool:
    """验证三种 push_channel 均可创建"""
    leader, _, _, session_id = _setup_session("Channels")
    results = []
    for ch in ["web", "app", "glasses"]:
        r = requests.post(f"{BASE_URL}/api/admin/push-logs/",
                          headers=ADMIN_HEADERS,
                          json={"session_id": session_id,
                                "target_user_id": leader["id"],
                                "push_channel": ch})
        results.append(r.status_code == 201)
    ok = all(results)
    return _log(ok, "POST /admin/push-logs 三种 push_channel 均可创建", results)


def scenario_create_delivery_statuses() -> bool:
    """验证三种 delivery_status 均可创建"""
    leader, _, _, session_id = _setup_session("DelivStat")
    results = []
    for ds in ["pending", "delivered", "failed"]:
        r = requests.post(f"{BASE_URL}/api/admin/push-logs/",
                          headers=ADMIN_HEADERS,
                          json={"session_id": session_id,
                                "target_user_id": leader["id"],
                                "push_channel": "app",
                                "delivery_status": ds})
        results.append(r.status_code == 201)
    ok = all(results)
    return _log(ok, "POST /admin/push-logs 三种 delivery_status 均可创建", results)


# ════════════════════════════════════════════════════
# GET /api/admin/push-logs/
# ════════════════════════════════════════════════════

def scenario_list_no_token() -> bool:
    r = requests.get(f"{BASE_URL}/api/admin/push-logs/")
    return _log(r.status_code == 403, "GET /admin/push-logs 无 Token 返回 403", {"status": r.status_code})


def scenario_list_empty() -> bool:
    r = requests.get(f"{BASE_URL}/api/admin/push-logs/",
                     headers=ADMIN_HEADERS,
                     params={"session_id": f"fake-session-{uuid.uuid4().hex}"})
    if r.status_code != 200:
        return _log(False, "GET /admin/push-logs 无记录返回 200 失败", r.text)
    data = r.json()
    ok = data["items"] == [] and data["meta"]["total"] == 0
    return _log(ok, "GET /admin/push-logs 无记录返回空列表", data["meta"])


def scenario_list_pagination() -> bool:
    leader, _, _, session_id = _setup_session("Pagination")
    for _ in range(5):
        _create_log(session_id=session_id, target_user_id=leader["id"], push_channel="app")

    r = requests.get(f"{BASE_URL}/api/admin/push-logs/",
                     headers=ADMIN_HEADERS,
                     params={"session_id": session_id, "page": 1, "page_size": 3})
    r.raise_for_status()
    data = r.json()
    ok = len(data["items"]) == 3
    ok &= data["meta"]["total"] >= 5
    ok &= data["meta"]["page"] == 1
    ok &= data["meta"]["page_size"] == 3
    return _log(ok, "GET /admin/push-logs 分页（page_size=3）验证", data["meta"])


def scenario_list_filter_session() -> bool:
    leader, _, _, session_id = _setup_session("FiltSess")
    _create_log(session_id=session_id, target_user_id=leader["id"], push_channel="app")

    r = requests.get(f"{BASE_URL}/api/admin/push-logs/",
                     headers=ADMIN_HEADERS,
                     params={"session_id": session_id})
    r.raise_for_status()
    data = r.json()
    ok = data["meta"]["total"] >= 1
    ok &= all(item["session_id"] == session_id for item in data["items"])
    return _log(ok, "GET /admin/push-logs 按 session_id 过滤", data["meta"])


def scenario_list_filter_target_user() -> bool:
    leader, _, group_id, session_id = _setup_session("FiltUser")
    member, member_token = _register_and_login("FiltMember")
    requests.post(f"{BASE_URL}/api/groups/{group_id}/join",
                  headers=_auth(member_token)).raise_for_status()

    _create_log(session_id=session_id, target_user_id=leader["id"], push_channel="app")
    _create_log(session_id=session_id, target_user_id=member["id"], push_channel="app")

    r = requests.get(f"{BASE_URL}/api/admin/push-logs/",
                     headers=ADMIN_HEADERS,
                     params={"session_id": session_id, "target_user_id": leader["id"]})
    r.raise_for_status()
    data = r.json()
    ok = data["meta"]["total"] >= 1
    ok &= all(item["target_user_id"] == leader["id"] for item in data["items"])
    return _log(ok, "GET /admin/push-logs 按 target_user_id 过滤", data["meta"])


def scenario_list_filter_push_channel() -> bool:
    leader, _, _, session_id = _setup_session("FiltChan")
    _create_log(session_id=session_id, target_user_id=leader["id"], push_channel="web")
    _create_log(session_id=session_id, target_user_id=leader["id"], push_channel="app")

    r = requests.get(f"{BASE_URL}/api/admin/push-logs/",
                     headers=ADMIN_HEADERS,
                     params={"session_id": session_id, "push_channel": "web"})
    r.raise_for_status()
    data = r.json()
    ok = data["meta"]["total"] >= 1
    ok &= all(item["push_channel"] == "web" for item in data["items"])
    return _log(ok, "GET /admin/push-logs 按 push_channel=web 过滤", data["meta"])


def scenario_list_filter_delivery_status() -> bool:
    leader, _, _, session_id = _setup_session("FiltDelivStat")
    _create_log(session_id=session_id, target_user_id=leader["id"],
                push_channel="app", delivery_status="failed")
    _create_log(session_id=session_id, target_user_id=leader["id"],
                push_channel="app", delivery_status="pending")

    r = requests.get(f"{BASE_URL}/api/admin/push-logs/",
                     headers=ADMIN_HEADERS,
                     params={"session_id": session_id, "delivery_status": "failed"})
    r.raise_for_status()
    data = r.json()
    ok = data["meta"]["total"] >= 1
    ok &= all(item["delivery_status"] == "failed" for item in data["items"])
    return _log(ok, "GET /admin/push-logs 按 delivery_status=failed 过滤", data["meta"])


def scenario_list_filter_state_id() -> bool:
    leader, _, _, session_id = _setup_session("FiltState")
    state_id = _create_discussion_state(session_id)
    _create_log(session_id=session_id, target_user_id=leader["id"],
                push_channel="app", state_id=state_id)
    _create_log(session_id=session_id, target_user_id=leader["id"],
                push_channel="app")  # no state_id

    r = requests.get(f"{BASE_URL}/api/admin/push-logs/",
                     headers=ADMIN_HEADERS,
                     params={"session_id": session_id, "state_id": state_id})
    r.raise_for_status()
    data = r.json()
    ok = data["meta"]["total"] >= 1
    ok &= all(item["state_id"] == state_id for item in data["items"])
    return _log(ok, "GET /admin/push-logs 按 state_id 过滤", data["meta"])


def scenario_list_filter_jpush_message_id() -> bool:
    leader, _, _, session_id = _setup_session("FiltJpush")
    jmsg_id = f"jmsg-{uuid.uuid4().hex[:8]}"
    _create_log(session_id=session_id, target_user_id=leader["id"],
                push_channel="app", jpush_message_id=jmsg_id)
    _create_log(session_id=session_id, target_user_id=leader["id"],
                push_channel="app", jpush_message_id="other-jmsg")

    r = requests.get(f"{BASE_URL}/api/admin/push-logs/",
                     headers=ADMIN_HEADERS,
                     params={"jpush_message_id": jmsg_id})
    r.raise_for_status()
    data = r.json()
    ok = data["meta"]["total"] >= 1
    ok &= all(item["jpush_message_id"] == jmsg_id for item in data["items"])
    return _log(ok, "GET /admin/push-logs 按 jpush_message_id 过滤", data["meta"])


def scenario_list_filter_triggered_range() -> bool:
    leader, _, _, session_id = _setup_session("FiltTime")
    _create_log(session_id=session_id, target_user_id=leader["id"], push_channel="app")

    r = requests.get(f"{BASE_URL}/api/admin/push-logs/",
                     headers=ADMIN_HEADERS,
                     params={
                         "session_id": session_id,
                         "triggered_from": "2020-01-01T00:00:00",
                         "triggered_to": "2099-01-01T00:00:00",
                     })
    r.raise_for_status()
    data = r.json()
    ok = data["meta"]["total"] >= 1
    return _log(ok, "GET /admin/push-logs 时间范围过滤（2020~2099）", data["meta"])


def scenario_list_filter_triggered_range_empty() -> bool:
    leader, _, _, session_id = _setup_session("FiltTimeEmpty")
    _create_log(session_id=session_id, target_user_id=leader["id"], push_channel="app")

    r = requests.get(f"{BASE_URL}/api/admin/push-logs/",
                     headers=ADMIN_HEADERS,
                     params={
                         "session_id": session_id,
                         "triggered_from": "2099-01-01T00:00:00",
                         "triggered_to": "2099-12-31T00:00:00",
                     })
    r.raise_for_status()
    data = r.json()
    ok = data["meta"]["total"] == 0
    return _log(ok, "GET /admin/push-logs 时间范围过滤（未来，无结果）", data["meta"])


def scenario_list_invalid_channel_filter() -> bool:
    r = requests.get(f"{BASE_URL}/api/admin/push-logs/",
                     headers=ADMIN_HEADERS,
                     params={"push_channel": "sms"})
    return _log(r.status_code == 400, "GET /admin/push-logs 非法 push_channel 过滤返回 400", {"status": r.status_code})


def scenario_list_invalid_status_filter() -> bool:
    r = requests.get(f"{BASE_URL}/api/admin/push-logs/",
                     headers=ADMIN_HEADERS,
                     params={"delivery_status": "lost"})
    return _log(r.status_code == 400, "GET /admin/push-logs 非法 delivery_status 过滤返回 400", {"status": r.status_code})


def scenario_list_join_fields() -> bool:
    """验证列表返回 session_title、target_user_name、state_type"""
    leader, _, _, session_id = _setup_session("JoinFields")
    state_id = _create_discussion_state(session_id)
    _create_log(session_id=session_id, target_user_id=leader["id"],
                push_channel="app", state_id=state_id)

    r = requests.get(f"{BASE_URL}/api/admin/push-logs/",
                     headers=ADMIN_HEADERS,
                     params={"session_id": session_id})
    r.raise_for_status()
    data = r.json()
    if not data["items"]:
        return _log(False, "GET /admin/push-logs JOIN 字段验证：无记录", data)
    item = data["items"][0]
    ok = item.get("session_title") is not None
    ok &= item.get("target_user_name") is not None
    ok &= item.get("state_type") == "low_participation"
    return _log(ok, "GET /admin/push-logs JOIN 字段（session_title、target_user_name、state_type）", item)


# ════════════════════════════════════════════════════
# DELETE /api/admin/push-logs/{log_id}
# ════════════════════════════════════════════════════

def scenario_delete_no_token() -> bool:
    r = requests.delete(f"{BASE_URL}/api/admin/push-logs/any-id")
    return _log(r.status_code == 403, "DELETE /admin/push-logs/{id} 无 Token 返回 403", {"status": r.status_code})


def scenario_delete_not_found() -> bool:
    r = requests.delete(f"{BASE_URL}/api/admin/push-logs/non-exist-id",
                        headers=ADMIN_HEADERS)
    return _log(r.status_code == 404, "DELETE /admin/push-logs/{id} 不存在返回 404", {"status": r.status_code})


def scenario_delete_success() -> bool:
    leader, _, _, session_id = _setup_session("Delete")
    log = _create_log(session_id=session_id, target_user_id=leader["id"], push_channel="app")
    log_id = log["id"]

    r = requests.delete(f"{BASE_URL}/api/admin/push-logs/{log_id}", headers=ADMIN_HEADERS)
    if r.status_code != 204:
        return _log(False, "DELETE /admin/push-logs/{id} 删除失败", r.text)

    # 确认已删除：列表中不再出现
    r2 = requests.get(f"{BASE_URL}/api/admin/push-logs/",
                      headers=ADMIN_HEADERS,
                      params={"session_id": session_id})
    r2.raise_for_status()
    ids = [item["id"] for item in r2.json()["items"]]
    ok = log_id not in ids
    return _log(ok, "DELETE /admin/push-logs/{id} 删除成功，列表中已不存在", {"log_id": log_id})


def scenario_delete_idempotent() -> bool:
    """连续删除同一条记录，第二次返回 404"""
    leader, _, _, session_id = _setup_session("DeleteIdem")
    log = _create_log(session_id=session_id, target_user_id=leader["id"], push_channel="app")
    log_id = log["id"]

    requests.delete(f"{BASE_URL}/api/admin/push-logs/{log_id}", headers=ADMIN_HEADERS).raise_for_status()
    r = requests.delete(f"{BASE_URL}/api/admin/push-logs/{log_id}", headers=ADMIN_HEADERS)
    return _log(r.status_code == 404, "DELETE /admin/push-logs/{id} 重复删除返回 404", {"status": r.status_code})


# ════════════════════════════════════════════════════
# POST /api/admin/push-logs/batch-delete
# ════════════════════════════════════════════════════

def scenario_batch_delete_no_token() -> bool:
    r = requests.post(f"{BASE_URL}/api/admin/push-logs/batch-delete",
                      json={"ids": ["a"]})
    return _log(r.status_code == 403, "POST /admin/push-logs/batch-delete 无 Token 返回 403", {"status": r.status_code})


def scenario_batch_delete_empty_ids() -> bool:
    r = requests.post(f"{BASE_URL}/api/admin/push-logs/batch-delete",
                      headers=ADMIN_HEADERS,
                      json={"ids": []})
    return _log(r.status_code == 422, "POST /admin/push-logs/batch-delete 空 ids 返回 422", {"status": r.status_code})


def scenario_batch_delete_exceed_limit() -> bool:
    r = requests.post(f"{BASE_URL}/api/admin/push-logs/batch-delete",
                      headers=ADMIN_HEADERS,
                      json={"ids": [f"x{i}" for i in range(101)]})
    return _log(r.status_code == 422, "POST /admin/push-logs/batch-delete 超 100 条返回 422", {"status": r.status_code})


def scenario_batch_delete_all_exist() -> bool:
    leader, _, _, session_id = _setup_session("BatchAll")
    ids = [
        _create_log(session_id=session_id, target_user_id=leader["id"], push_channel="app")["id"]
        for _ in range(3)
    ]
    r = requests.post(f"{BASE_URL}/api/admin/push-logs/batch-delete",
                      headers=ADMIN_HEADERS,
                      json={"ids": ids})
    if r.status_code != 200:
        return _log(False, "POST /admin/push-logs/batch-delete 全存在批量删除失败", r.text)
    ok = r.json()["deleted"] == 3
    return _log(ok, "POST /admin/push-logs/batch-delete 全存在，deleted=3", r.json())


def scenario_batch_delete_partial_exist() -> bool:
    """部分 id 不存在，已存在的删掉，不报错"""
    leader, _, _, session_id = _setup_session("BatchPartial")
    existing_id = _create_log(session_id=session_id, target_user_id=leader["id"],
                               push_channel="app")["id"]
    r = requests.post(f"{BASE_URL}/api/admin/push-logs/batch-delete",
                      headers=ADMIN_HEADERS,
                      json={"ids": [existing_id, "fake-id-001", "fake-id-002"]})
    if r.status_code != 200:
        return _log(False, "POST /admin/push-logs/batch-delete 部分存在批量删除失败", r.text)
    ok = r.json()["deleted"] == 1
    return _log(ok, "POST /admin/push-logs/batch-delete 部分存在，deleted=1", r.json())


def scenario_batch_delete_none_exist() -> bool:
    r = requests.post(f"{BASE_URL}/api/admin/push-logs/batch-delete",
                      headers=ADMIN_HEADERS,
                      json={"ids": ["fake-x", "fake-y"]})
    if r.status_code != 200:
        return _log(False, "POST /admin/push-logs/batch-delete 全不存在失败", r.text)
    ok = r.json()["deleted"] == 0
    return _log(ok, "POST /admin/push-logs/batch-delete 全不存在，deleted=0", r.json())


def scenario_batch_delete_dedup_ids() -> bool:
    """ids 中有重复项，实际只删一条"""
    leader, _, _, session_id = _setup_session("BatchDedup")
    log_id = _create_log(session_id=session_id, target_user_id=leader["id"],
                          push_channel="app")["id"]
    r = requests.post(f"{BASE_URL}/api/admin/push-logs/batch-delete",
                      headers=ADMIN_HEADERS,
                      json={"ids": [log_id, log_id, log_id]})
    if r.status_code != 200:
        return _log(False, "POST /admin/push-logs/batch-delete 重复 id 批量删除失败", r.text)
    ok = r.json()["deleted"] == 1
    return _log(ok, "POST /admin/push-logs/batch-delete 重复 id 去重后 deleted=1", r.json())


def run_all() -> bool:
    print("=== 开始 Admin Push Logs 接口测试 ===")
    ok = True

    print("\n-- POST 创建 --")
    ok &= scenario_create_no_token()
    ok &= scenario_create_wrong_token()
    ok &= scenario_create_session_not_found()
    ok &= scenario_create_user_not_found()
    ok &= scenario_create_invalid_channel()
    ok &= scenario_create_invalid_delivery_status()
    ok &= scenario_create_state_not_found()
    ok &= scenario_create_minimal()
    ok &= scenario_create_full_fields()
    ok &= scenario_create_channels()
    ok &= scenario_create_delivery_statuses()

    print("\n-- GET 列表 --")
    ok &= scenario_list_no_token()
    ok &= scenario_list_empty()
    ok &= scenario_list_pagination()
    ok &= scenario_list_filter_session()
    ok &= scenario_list_filter_target_user()
    ok &= scenario_list_filter_push_channel()
    ok &= scenario_list_filter_delivery_status()
    ok &= scenario_list_filter_state_id()
    ok &= scenario_list_filter_jpush_message_id()
    ok &= scenario_list_filter_triggered_range()
    ok &= scenario_list_filter_triggered_range_empty()
    ok &= scenario_list_invalid_channel_filter()
    ok &= scenario_list_invalid_status_filter()
    ok &= scenario_list_join_fields()

    print("\n-- DELETE 单条 --")
    ok &= scenario_delete_no_token()
    ok &= scenario_delete_not_found()
    ok &= scenario_delete_success()
    ok &= scenario_delete_idempotent()

    print("\n-- batch-delete --")
    ok &= scenario_batch_delete_no_token()
    ok &= scenario_batch_delete_empty_ids()
    ok &= scenario_batch_delete_exceed_limit()
    ok &= scenario_batch_delete_all_exist()
    ok &= scenario_batch_delete_partial_exist()
    ok &= scenario_batch_delete_none_exist()
    ok &= scenario_batch_delete_dedup_ids()

    print("\n=== Admin Push Logs 测试结果: {} ===".format("全部通过 ✅" if ok else "有失败 ❌"))
    return ok


if __name__ == "__main__":
    import sys
    sys.exit(0 if run_all() else 1)
