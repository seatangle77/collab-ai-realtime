from __future__ import annotations

import time
import uuid
from typing import Any, Dict, Tuple

import requests

BASE_URL = "http://127.0.0.1:8000"
RUN_ID = uuid.uuid4().hex[:6]
ADMIN_HEADERS = {"X-Admin-Token": "TestAdminKey123"}
BAD_HEADERS = {"X-Admin-Token": "WrongKey"}

VALID_STATE_TYPES = [
    "low_participation", "over_dominance", "disengaged",
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


def _create_metric(session_id: str, user_id: str, **kwargs) -> Dict[str, Any]:
    r = requests.post(f"{BASE_URL}/api/admin/engagement-metrics/",
                      headers=ADMIN_HEADERS,
                      json={"session_id": session_id, "user_id": user_id, **kwargs})
    r.raise_for_status()
    return r.json()


def _create_state(session_id: str, state_type: str, **kwargs) -> Dict[str, Any]:
    r = requests.post(f"{BASE_URL}/api/admin/discussion-states/",
                      headers=ADMIN_HEADERS,
                      json={"session_id": session_id, "state_type": state_type, **kwargs})
    r.raise_for_status()
    return r.json()


# ──────────────────────────────
# B. Admin engagement-metrics
# ──────────────────────────────

def scenario_em_no_token() -> bool:
    r = requests.get(f"{BASE_URL}/api/admin/engagement-metrics/")
    ok = r.status_code == 403
    return _log(ok, "EM 无 token 返回 403", {"status": r.status_code})


def scenario_em_create_missing_fields() -> bool:
    r = requests.post(f"{BASE_URL}/api/admin/engagement-metrics/",
                      headers=ADMIN_HEADERS, json={"session_id": "only-session"})
    ok = r.status_code == 422
    return _log(ok, "EM 创建缺少 user_id 返回 422", {"status": r.status_code})


def scenario_em_create_session_not_found() -> bool:
    user, _ = _register_and_login("EMSessNF")
    r = requests.post(f"{BASE_URL}/api/admin/engagement-metrics/",
                      headers=ADMIN_HEADERS,
                      json={"session_id": "ghost-session-999", "user_id": user["id"]})
    ok = r.status_code == 404
    return _log(ok, "EM 创建 session 不存在返回 404", {"status": r.status_code})


def scenario_em_create_user_not_found() -> bool:
    _, session_id = _setup_session("EMUserNF")
    r = requests.post(f"{BASE_URL}/api/admin/engagement-metrics/",
                      headers=ADMIN_HEADERS,
                      json={"session_id": session_id, "user_id": "ghost-user-999"})
    ok = r.status_code == 404
    return _log(ok, "EM 创建 user 不存在返回 404", {"status": r.status_code})


def scenario_em_create_success() -> bool:
    user_id, session_id = _setup_session("EMCreate")
    r = requests.post(f"{BASE_URL}/api/admin/engagement-metrics/",
                      headers=ADMIN_HEADERS,
                      json={
                          "session_id": session_id, "user_id": user_id,
                          "speaking_ratio": 0.35, "speaking_frequency": 2.1,
                          "silence_duration_s": 45, "mattr_score": 0.72,
                          "avg_sentence_length": 12.5, "response_rate": 0.8,
                          "new_idea_rate": 0.3, "topic_cosine_similarity": 0.65,
                          "semantic_cohesion": 0.7, "semantic_uniqueness": 0.4,
                      })
    if r.status_code != 201:
        return _log(False, "EM 创建成功失败（期望 201）", r.text)
    data = r.json()
    ok = data.get("id", "").startswith("em")
    ok &= data.get("session_id") == session_id
    ok &= data.get("user_id") == user_id
    ok &= data.get("user_name") is not None
    fields = ["speaking_ratio", "speaking_frequency", "silence_duration_s",
              "mattr_score", "avg_sentence_length", "response_rate",
              "new_idea_rate", "topic_cosine_similarity", "semantic_cohesion",
              "semantic_uniqueness", "calculated_at"]
    ok &= all(f in data for f in fields)
    return _log(ok, "EM 创建成功，id 前缀/字段完整性场景", data)


def scenario_em_list_basic() -> bool:
    r = requests.get(f"{BASE_URL}/api/admin/engagement-metrics/", headers=ADMIN_HEADERS)
    if r.status_code != 200:
        return _log(False, "EM 基础列表失败", r.text)
    data = r.json()
    ok = "items" in data and "meta" in data
    ok &= isinstance(data["items"], list)
    ok &= all(k in data["meta"] for k in ["total", "page", "page_size"])
    return _log(ok, "EM 基础列表 Page 结构场景", data.get("meta"))


def scenario_em_filter_session() -> bool:
    user_id, session_id = _setup_session("EMFilterSess")
    _create_metric(session_id, user_id)
    r = requests.get(f"{BASE_URL}/api/admin/engagement-metrics/",
                     headers=ADMIN_HEADERS, params={"session_id": session_id})
    r.raise_for_status()
    items = r.json()["items"]
    ok = all(i["session_id"] == session_id for i in items) and len(items) >= 1
    return _log(ok, "EM session_id 过滤场景", {"count": len(items)})


def scenario_em_filter_user() -> bool:
    user_id, session_id = _setup_session("EMFilterUser")
    _create_metric(session_id, user_id)
    r = requests.get(f"{BASE_URL}/api/admin/engagement-metrics/",
                     headers=ADMIN_HEADERS, params={"user_id": user_id})
    r.raise_for_status()
    items = r.json()["items"]
    ok = all(i["user_id"] == user_id for i in items) and len(items) >= 1
    return _log(ok, "EM user_id 过滤场景", {"count": len(items)})


def scenario_em_filter_time_range() -> bool:
    user_id, session_id = _setup_session("EMTimeRange")
    _create_metric(session_id, user_id)
    r = requests.get(f"{BASE_URL}/api/admin/engagement-metrics/",
                     headers=ADMIN_HEADERS,
                     params={"session_id": session_id,
                             "calculated_from": "2020-01-01T00:00:00",
                             "calculated_to": "2099-01-01T00:00:00"})
    r.raise_for_status()
    ok = len(r.json()["items"]) >= 1
    # 区间外
    r2 = requests.get(f"{BASE_URL}/api/admin/engagement-metrics/",
                      headers=ADMIN_HEADERS,
                      params={"session_id": session_id,
                              "calculated_from": "2099-01-01T00:00:00",
                              "calculated_to": "2099-12-31T00:00:00"})
    r2.raise_for_status()
    ok &= len(r2.json()["items"]) == 0
    return _log(ok, "EM calculated_from/to 时间区间过滤场景")


def scenario_em_pagination() -> bool:
    user_id, session_id = _setup_session("EMPage")
    for _ in range(3):
        _create_metric(session_id, user_id)
    r = requests.get(f"{BASE_URL}/api/admin/engagement-metrics/",
                     headers=ADMIN_HEADERS,
                     params={"session_id": session_id, "page": 1, "page_size": 2})
    r.raise_for_status()
    data = r.json()
    ok = len(data["items"]) == 2
    ok &= data["meta"]["total"] >= 3
    # page 2
    r2 = requests.get(f"{BASE_URL}/api/admin/engagement-metrics/",
                      headers=ADMIN_HEADERS,
                      params={"session_id": session_id, "page": 2, "page_size": 2})
    r2.raise_for_status()
    ok &= len(r2.json()["items"]) >= 1
    return _log(ok, "EM 分页场景", data["meta"])


def scenario_em_page_size_over_limit() -> bool:
    r = requests.get(f"{BASE_URL}/api/admin/engagement-metrics/",
                     headers=ADMIN_HEADERS, params={"page_size": 101})
    ok = r.status_code == 422
    return _log(ok, "EM page_size=101 超限返回 422", {"status": r.status_code})


def scenario_em_sort_desc() -> bool:
    user_id, session_id = _setup_session("EMSort")
    _create_metric(session_id, user_id, speaking_ratio=0.1)
    time.sleep(1)
    _create_metric(session_id, user_id, speaking_ratio=0.9)
    r = requests.get(f"{BASE_URL}/api/admin/engagement-metrics/",
                     headers=ADMIN_HEADERS, params={"session_id": session_id})
    r.raise_for_status()
    items = r.json()["items"]
    ok = len(items) >= 2 and items[0]["speaking_ratio"] == 0.9
    return _log(ok, "EM 排序 calculated_at DESC，最新记录在 items[0] 场景",
                {"first_ratio": items[0].get("speaking_ratio") if items else None})


# ──────────────────────────────
# C. Admin discussion-states
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
                      json={"session_id": session_id, "state_type": "low_participation",
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
    _create_state(session_id, "low_participation", target_user_id=user_id)
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
                     headers=ADMIN_HEADERS, params={"page_size": 101})
    ok = r.status_code == 422
    return _log(ok, "DS page_size=101 超限返回 422", {"status": r.status_code})


# ──────────────────────────────
# D. Admin discussion-rules
# ──────────────────────────────

def scenario_rules_no_token() -> bool:
    r = requests.get(f"{BASE_URL}/api/admin/discussion-rules/")
    ok = r.status_code == 403
    return _log(ok, "Rules 无 token GET 返回 403", {"status": r.status_code})


def scenario_rules_get_defaults() -> bool:
    r = requests.get(f"{BASE_URL}/api/admin/discussion-rules/", headers=ADMIN_HEADERS)
    if r.status_code != 200:
        return _log(False, "Rules GET 失败（期望 200）", r.text)
    data = r.json()
    required = ["silence_threshold_minutes", "speaking_ratio_min", "speaking_ratio_max",
                "cosine_similarity_threshold", "min_session_duration_minutes",
                "push_interval_minutes", "max_push_per_member",
                "analysis_enabled", "updated_at"]
    ok = all(f in data for f in required)
    return _log(ok, "Rules GET 返回默认值，所有字段存在场景", data)


def scenario_rules_put_single_field() -> bool:
    # 先 GET 当前值
    before = requests.get(f"{BASE_URL}/api/admin/discussion-rules/",
                          headers=ADMIN_HEADERS).json()
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
    r = requests.put(f"{BASE_URL}/api/admin/discussion-rules/",
                     headers=ADMIN_HEADERS, json={})
    ok = r.status_code == 400
    return _log(ok, "Rules PUT 空 body 返回 400", {"status": r.status_code})


def scenario_rules_put_persist() -> bool:
    """GET → PUT → GET，验证持久化。"""
    val = 6
    requests.put(f"{BASE_URL}/api/admin/discussion-rules/",
                 headers=ADMIN_HEADERS,
                 json={"silence_threshold_minutes": val}).raise_for_status()
    r = requests.get(f"{BASE_URL}/api/admin/discussion-rules/", headers=ADMIN_HEADERS)
    r.raise_for_status()
    ok = r.json().get("silence_threshold_minutes") == val
    return _log(ok, "Rules PUT 后 GET 持久化验证场景", {"value": r.json().get("silence_threshold_minutes")})


def scenario_rules_put_invalid_values() -> bool:
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
    ok = True
    for expected in [True, False, True]:
        r = requests.put(f"{BASE_URL}/api/admin/discussion-rules/",
                         headers=ADMIN_HEADERS,
                         json={"analysis_enabled": expected})
        ok &= r.status_code == 200 and r.json().get("analysis_enabled") == expected
    return _log(ok, "Rules analysis_enabled 反复切换场景")


def run_all() -> bool:
    print("=== 开始 Admin Engagement 管理端接口测试 ===")
    ok = True

    print("\n--- B. Admin engagement-metrics ---")
    ok &= scenario_em_no_token()
    ok &= scenario_em_create_missing_fields()
    ok &= scenario_em_create_session_not_found()
    ok &= scenario_em_create_user_not_found()
    ok &= scenario_em_create_success()
    ok &= scenario_em_list_basic()
    ok &= scenario_em_filter_session()
    ok &= scenario_em_filter_user()
    ok &= scenario_em_filter_time_range()
    ok &= scenario_em_pagination()
    ok &= scenario_em_page_size_over_limit()
    ok &= scenario_em_sort_desc()

    print("\n--- C. Admin discussion-states ---")
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

    print("\n--- D. Admin discussion-rules ---")
    ok &= scenario_rules_no_token()
    ok &= scenario_rules_get_defaults()
    ok &= scenario_rules_put_single_field()
    ok &= scenario_rules_put_all_fields()
    ok &= scenario_rules_put_empty_body()
    ok &= scenario_rules_put_persist()
    ok &= scenario_rules_put_invalid_values()
    ok &= scenario_rules_toggle_analysis_enabled()

    print("\n=== Admin Engagement 测试结果: {} ===".format("全部通过 ✅" if ok else "有失败 ❌"))
    return ok


if __name__ == "__main__":
    import sys
    sys.exit(0 if run_all() else 1)
