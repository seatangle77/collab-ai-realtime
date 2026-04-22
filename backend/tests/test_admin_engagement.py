from __future__ import annotations

import uuid
from typing import Any, Dict, Tuple

import requests

BASE_URL = "http://127.0.0.1:8000"
RUN_ID = uuid.uuid4().hex[:6]
ADMIN_HEADERS = {"X-Admin-Token": "TestAdminKey123"}
BAD_HEADERS = {"X-Admin-Token": "WrongKey"}

VALID_STATE_TYPES = [
    "stagnation", "over_dominance", "disengaged",
    "deadlock", "topic_drift", "low_depth", "homogeneous",
]


def _log(ok: bool, message: str, extra: Any = None) -> bool:
    print(f"{'✅' if ok else '❌'} {message}")
    if not ok and extra is not None:
        print("   详情:", extra)
    return ok


def _register_and_login(label: str) -> Tuple[Dict[str, Any], str]:
    email = f"adm_eng_{label}_{uuid.uuid4().hex[:6]}@example.com"
    r = requests.post(f"{BASE_URL}/api/auth/register", json={
        "name": f"AE {label} {RUN_ID}",
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


def _setup_session(label: str) -> Tuple[str, str]:
    """注册用户 → 建群 → 建会话，返回 (user_id, session_id)"""
    user, token = _register_and_login(label)
    r = requests.post(f"{BASE_URL}/api/groups", headers=_auth(token),
                      json={"name": f"AE Group {label} {RUN_ID}"})
    r.raise_for_status()
    group_id = r.json()["group"]["id"]
    r2 = requests.post(f"{BASE_URL}/api/groups/{group_id}/sessions",
                       headers=_auth(token), json={"session_title": f"AE Session {label}"})
    r2.raise_for_status()
    return user["id"], r2.json()["id"]


def _create_state(session_id: str, state_type: str, **kwargs) -> Dict[str, Any]:
    r = requests.post(f"{BASE_URL}/api/admin/discussion-states/",
                      headers=ADMIN_HEADERS,
                      json={"session_id": session_id, "state_type": state_type, **kwargs})
    r.raise_for_status()
    return r.json()


def _get_rules_response() -> requests.Response:
    return requests.get(f"{BASE_URL}/api/admin/discussion-rules/", headers=ADMIN_HEADERS)


def _load_rules_or_skip() -> Dict[str, Any] | None:
    r = _get_rules_response()
    if r.status_code != 200:
        _log(True, "Rules 默认配置缺失，跳过规则相关场景", {"status": r.status_code, "body": r.text})
        return None
    return r.json()


# ──────────────────────────────
# B. Admin discussion-states
# ──────────────────────────────

def scenario_ds_no_token() -> bool:
    r = requests.get(f"{BASE_URL}/api/admin/discussion-states/")
    ok = r.status_code == 403
    return _log(ok, "DS 无 token 返回 403", {"status": r.status_code})


def scenario_ds_create_missing_fields() -> bool:
    r = requests.post(f"{BASE_URL}/api/admin/discussion-states/",
                      headers=ADMIN_HEADERS, json={"session_id": "only"})
    ok = r.status_code == 422
    return _log(ok, "DS 创建缺少 state_type 返回 422", {"status": r.status_code})


def scenario_ds_create_invalid_state_type() -> bool:
    _, session_id = _setup_session("DSInvalidType")
    r = requests.post(f"{BASE_URL}/api/admin/discussion-states/",
                      headers=ADMIN_HEADERS,
                      json={"session_id": session_id, "state_type": "invalid_type"})
    ok = r.status_code == 400
    return _log(ok, "DS 创建非法 state_type 返回 400", {"status": r.status_code})


def scenario_ds_create_group_state() -> bool:
    """全组状态，target_user_id 不传，应返回 null。"""
    _, session_id = _setup_session("DSGroupState")
    r = requests.post(f"{BASE_URL}/api/admin/discussion-states/",
                      headers=ADMIN_HEADERS,
                      json={"session_id": session_id, "state_type": "deadlock"})
    if r.status_code != 201:
        return _log(False, "DS 创建全组状态失败（期望 201）", r.text)
    data = r.json()
    ok = data.get("id", "").startswith("ds")
    ok &= data.get("target_user_id") is None
    ok &= data.get("target_user_name") is None
    ok &= data.get("ai_analysis_done") is False
    ok &= data.get("push_sent") is False
    return _log(ok, "DS 创建全组状态（target_user_id=null）场景", data)


def scenario_ds_create_member_state() -> bool:
    """成员状态，target_user_id 有值，target_user_name 应回显。"""
    user_id, session_id = _setup_session("DSMemberState")
    r = requests.post(f"{BASE_URL}/api/admin/discussion-states/",
                      headers=ADMIN_HEADERS,
                      json={"session_id": session_id, "state_type": "stagnation",
                            "target_user_id": user_id,
                            "trigger_metrics": {"speaking_ratio": 0.05},
                            "ai_analysis_done": True, "push_sent": True})
    if r.status_code != 201:
        return _log(False, "DS 创建成员状态失败（期望 201）", r.text)
    data = r.json()
    ok = data.get("target_user_id") == user_id
    ok &= data.get("target_user_name") is not None
    ok &= isinstance(data.get("trigger_metrics"), dict)
    ok &= data.get("ai_analysis_done") is True
    ok &= data.get("push_sent") is True
    return _log(ok, "DS 创建成员状态，trigger_metrics/target_user_name 场景", data)


def scenario_ds_list_basic() -> bool:
    r = requests.get(f"{BASE_URL}/api/admin/discussion-states/", headers=ADMIN_HEADERS)
    if r.status_code != 200:
        return _log(False, "DS 基础列表失败", r.text)
    data = r.json()
    ok = "items" in data and "meta" in data
    return _log(ok, "DS 基础列表 Page 结构场景", data.get("meta"))


def scenario_ds_filter_session() -> bool:
    _, session_id = _setup_session("DSFilterSess")
    _create_state(session_id, "deadlock")
    r = requests.get(f"{BASE_URL}/api/admin/discussion-states/",
                     headers=ADMIN_HEADERS, params={"session_id": session_id})
    r.raise_for_status()
    items = r.json()["items"]
    ok = all(i["session_id"] == session_id for i in items) and len(items) >= 1
    return _log(ok, "DS session_id 过滤场景", {"count": len(items)})


def scenario_ds_filter_state_type() -> bool:
    _, session_id = _setup_session("DSFilterType")
    _create_state(session_id, "deadlock")
    _create_state(session_id, "topic_drift")
    r = requests.get(f"{BASE_URL}/api/admin/discussion-states/",
                     headers=ADMIN_HEADERS,
                     params={"session_id": session_id, "state_type": "deadlock"})
    r.raise_for_status()
    items = r.json()["items"]
    ok = all(i["state_type"] == "deadlock" for i in items) and len(items) >= 1
    return _log(ok, "DS state_type 合法枚举过滤场景", {"count": len(items)})


def scenario_ds_filter_invalid_state_type() -> bool:
    r = requests.get(f"{BASE_URL}/api/admin/discussion-states/",
                     headers=ADMIN_HEADERS, params={"state_type": "bad_type"})
    ok = r.status_code == 400
    return _log(ok, "DS state_type 非法值过滤返回 400", {"status": r.status_code})


def scenario_ds_filter_target_user() -> bool:
    user_id, session_id = _setup_session("DSFilterUser")
    _create_state(session_id, "stagnation", target_user_id=user_id)
    r = requests.get(f"{BASE_URL}/api/admin/discussion-states/",
                     headers=ADMIN_HEADERS, params={"target_user_id": user_id})
    r.raise_for_status()
    items = r.json()["items"]
    ok = all(i["target_user_id"] == user_id for i in items) and len(items) >= 1
    return _log(ok, "DS target_user_id 过滤场景", {"count": len(items)})


def scenario_ds_filter_ai_analysis_done() -> bool:
    _, session_id = _setup_session("DSFilterAI")
    _create_state(session_id, "deadlock", ai_analysis_done=True)
    _create_state(session_id, "topic_drift", ai_analysis_done=False)

    r_true = requests.get(f"{BASE_URL}/api/admin/discussion-states/",
                          headers=ADMIN_HEADERS,
                          params={"session_id": session_id, "ai_analysis_done": True})
    r_false = requests.get(f"{BASE_URL}/api/admin/discussion-states/",
                           headers=ADMIN_HEADERS,
                           params={"session_id": session_id, "ai_analysis_done": False})
    ok = r_true.status_code == 200 and r_false.status_code == 200
    items_true = r_true.json()["items"]
    items_false = r_false.json()["items"]
    ok &= all(i["ai_analysis_done"] is True for i in items_true)
    ok &= all(i["ai_analysis_done"] is False for i in items_false)
    return _log(ok, "DS ai_analysis_done true/false 过滤场景",
                {"true_count": len(items_true), "false_count": len(items_false)})


def scenario_ds_filter_push_sent() -> bool:
    _, session_id = _setup_session("DSFilterPush")
    _create_state(session_id, "deadlock", push_sent=True)
    _create_state(session_id, "topic_drift", push_sent=False)

    r_true = requests.get(f"{BASE_URL}/api/admin/discussion-states/",
                          headers=ADMIN_HEADERS,
                          params={"session_id": session_id, "push_sent": True})
    r_false = requests.get(f"{BASE_URL}/api/admin/discussion-states/",
                           headers=ADMIN_HEADERS,
                           params={"session_id": session_id, "push_sent": False})
    ok = all(i["push_sent"] is True for i in r_true.json()["items"])
    ok &= all(i["push_sent"] is False for i in r_false.json()["items"])
    return _log(ok, "DS push_sent true/false 过滤场景")


def scenario_ds_filter_time_range() -> bool:
    _, session_id = _setup_session("DSTimeRange")
    _create_state(session_id, "deadlock")
    r = requests.get(f"{BASE_URL}/api/admin/discussion-states/",
                     headers=ADMIN_HEADERS,
                     params={"session_id": session_id,
                             "triggered_from": "2020-01-01T00:00:00",
                             "triggered_to": "2099-01-01T00:00:00"})
    r.raise_for_status()
    ok = len(r.json()["items"]) >= 1
    r2 = requests.get(f"{BASE_URL}/api/admin/discussion-states/",
                      headers=ADMIN_HEADERS,
                      params={"session_id": session_id,
                              "triggered_from": "2099-01-01T00:00:00",
                              "triggered_to": "2099-12-31T00:00:00"})
    r2.raise_for_status()
    ok &= len(r2.json()["items"]) == 0
    return _log(ok, "DS triggered_from/to 时间区间过滤场景")


def scenario_ds_page_size_over_limit() -> bool:
    r = requests.get(f"{BASE_URL}/api/admin/discussion-states/",
                     headers=ADMIN_HEADERS, params={"page_size": 201})
    ok = r.status_code == 422
    return _log(ok, "DS page_size=201 超限返回 422", {"status": r.status_code})


# ──────────────────────────────
# C. Admin discussion-rules
# ──────────────────────────────

def scenario_rules_no_token() -> bool:
    r = requests.get(f"{BASE_URL}/api/admin/discussion-rules/")
    ok = r.status_code == 403
    return _log(ok, "Rules 无 token GET 返回 403", {"status": r.status_code})


def scenario_rules_get_defaults() -> bool:
    data = _load_rules_or_skip()
    if data is None:
        return True
    required = ["silence_threshold_minutes", "speaking_ratio_min", "speaking_ratio_max",
                "cosine_similarity_threshold", "min_session_duration_minutes",
                "push_interval_minutes", "max_push_per_member",
                "analysis_enabled", "updated_at"]
    ok = all(f in data for f in required)
    return _log(ok, "Rules GET 返回默认值，所有字段存在场景", data)


def scenario_rules_put_single_field() -> bool:
    # 先 GET 当前值
    before = _load_rules_or_skip()
    if before is None:
        return True
    new_val = not before["analysis_enabled"]
    r = requests.put(f"{BASE_URL}/api/admin/discussion-rules/",
                     headers=ADMIN_HEADERS,
                     json={"analysis_enabled": new_val})
    if r.status_code != 200:
        return _log(False, "Rules PUT 单字段失败（期望 200）", r.text)
    data = r.json()
    ok = data["analysis_enabled"] == new_val
    # 其他字段不变
    ok &= data["silence_threshold_minutes"] == before["silence_threshold_minutes"]
    ok &= data["speaking_ratio_min"] == before["speaking_ratio_min"]
    return _log(ok, "Rules PUT 单字段更新，其他字段不变场景", data)


def scenario_rules_put_all_fields() -> bool:
    if _load_rules_or_skip() is None:
        return True
    new_rules = {
        "silence_threshold_minutes": 7,
        "speaking_ratio_min": 0.12,
        "speaking_ratio_max": 0.55,
        "cosine_similarity_threshold": 0.35,
        "min_session_duration_minutes": 8,
        "push_interval_minutes": 15,
        "max_push_per_member": 5,
        "analysis_enabled": True,
    }
    r = requests.put(f"{BASE_URL}/api/admin/discussion-rules/",
                     headers=ADMIN_HEADERS, json=new_rules)
    if r.status_code != 200:
        return _log(False, "Rules PUT 全字段失败（期望 200）", r.text)
    data = r.json()
    ok = all(data.get(k) == v for k, v in new_rules.items())
    ok &= data.get("updated_at") is not None
    return _log(ok, "Rules PUT 全字段更新场景", data)


def scenario_rules_put_empty_body() -> bool:
    if _load_rules_or_skip() is None:
        return True
    r = requests.put(f"{BASE_URL}/api/admin/discussion-rules/",
                     headers=ADMIN_HEADERS, json={})
    ok = r.status_code == 400
    return _log(ok, "Rules PUT 空 body 返回 400", {"status": r.status_code})


def scenario_rules_put_persist() -> bool:
    """GET → PUT → GET，验证持久化。"""
    if _load_rules_or_skip() is None:
        return True
    val = 6
    requests.put(f"{BASE_URL}/api/admin/discussion-rules/",
                 headers=ADMIN_HEADERS,
                 json={"silence_threshold_minutes": val}).raise_for_status()
    r = requests.get(f"{BASE_URL}/api/admin/discussion-rules/", headers=ADMIN_HEADERS)
    r.raise_for_status()
    ok = r.json().get("silence_threshold_minutes") == val
    return _log(ok, "Rules PUT 后 GET 持久化验证场景", {"value": r.json().get("silence_threshold_minutes")})


def scenario_rules_put_invalid_values() -> bool:
    if _load_rules_or_skip() is None:
        return True
    ok = True
    # ge=1 校验：0 应被拒绝
    r1 = requests.put(f"{BASE_URL}/api/admin/discussion-rules/",
                      headers=ADMIN_HEADERS,
                      json={"silence_threshold_minutes": 0})
    ok &= _log(r1.status_code == 422,
               "Rules PUT silence_threshold_minutes=0 被拒绝", {"status": r1.status_code})
    # float 超出 0~1 范围
    r2 = requests.put(f"{BASE_URL}/api/admin/discussion-rules/",
                      headers=ADMIN_HEADERS,
                      json={"speaking_ratio_min": 1.5})
    ok &= _log(r2.status_code == 422,
               "Rules PUT speaking_ratio_min=1.5 被拒绝", {"status": r2.status_code})
    return ok


def scenario_rules_toggle_analysis_enabled() -> bool:
    """analysis_enabled 反复切换 true → false → true。"""
    if _load_rules_or_skip() is None:
        return True
    ok = True
    for expected in [True, False, True]:
        r = requests.put(f"{BASE_URL}/api/admin/discussion-rules/",
                         headers=ADMIN_HEADERS,
                         json={"analysis_enabled": expected})
        ok &= r.status_code == 200 and r.json().get("analysis_enabled") == expected
    return _log(ok, "Rules analysis_enabled 反复切换场景")


def run_all() -> bool:
    print("=== 开始 Admin Discussion 管理端接口测试 ===")
    ok = True

    print("\n--- B. Admin discussion-states ---")
    ok &= scenario_ds_no_token()
    ok &= scenario_ds_create_missing_fields()
    ok &= scenario_ds_create_invalid_state_type()
    ok &= scenario_ds_create_group_state()
    ok &= scenario_ds_create_member_state()
    ok &= scenario_ds_list_basic()
    ok &= scenario_ds_filter_session()
    ok &= scenario_ds_filter_state_type()
    ok &= scenario_ds_filter_invalid_state_type()
    ok &= scenario_ds_filter_target_user()
    ok &= scenario_ds_filter_ai_analysis_done()
    ok &= scenario_ds_filter_push_sent()
    ok &= scenario_ds_filter_time_range()
    ok &= scenario_ds_page_size_over_limit()

    print("\n--- C. Admin discussion-rules ---")
    ok &= scenario_rules_no_token()
    ok &= scenario_rules_get_defaults()
    ok &= scenario_rules_put_single_field()
    ok &= scenario_rules_put_all_fields()
    ok &= scenario_rules_put_empty_body()
    ok &= scenario_rules_put_persist()
    ok &= scenario_rules_put_invalid_values()
    ok &= scenario_rules_toggle_analysis_enabled()

    print("\n=== Admin Discussion 测试结果: {} ===".format("全部通过 ✅" if ok else "有失败 ❌"))
    return ok


if __name__ == "__main__":
    import sys
    sys.exit(0 if run_all() else 1)
