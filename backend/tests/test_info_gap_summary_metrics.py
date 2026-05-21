"""
集成测试：info-gap / discussion-summary / window-metrics 三组接口
运行前提：后端已启动（http://127.0.0.1:8000）
用法：python tests/test_info_gap_summary_metrics.py
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, Tuple

import requests

BASE_URL = "http://127.0.0.1:8000"
ADMIN_HEADERS = {"X-Admin-Token": "TestAdminKey123"}
RUN_ID = uuid.uuid4().hex[:6]


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _log(ok: bool, msg: str, extra: Any = None) -> bool:
    print(f"{'✅' if ok else '❌'} {msg}")
    if not ok and extra is not None:
        print("   详情:", extra)
    return ok


def _assert_log(ok: bool, msg: str, extra: Any = None) -> None:
    assert _log(ok, msg, extra)


def _register_and_login(label: str) -> Tuple[Dict, str]:
    email = f"igtest_{label}_{RUN_ID}@example.com"
    r = requests.post(f"{BASE_URL}/api/auth/register", json={
        "name": f"IG {label} {RUN_ID}",
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


def _setup_ongoing_session(label: str) -> Tuple[Dict, str, str]:
    user, token = _register_and_login(label)
    g = requests.post(f"{BASE_URL}/api/groups", headers=_auth(token),
                      json={"name": f"IG Group {label} {RUN_ID}"})
    g.raise_for_status()
    group_id = g.json()["group"]["id"]
    s = requests.post(f"{BASE_URL}/api/groups/{group_id}/sessions",
                      headers=_auth(token),
                      json={"session_title": f"IG Session {label}"})
    s.raise_for_status()
    session_id = s.json()["id"]
    requests.post(f"{BASE_URL}/api/sessions/{session_id}/start",
                  headers=_auth(token)).raise_for_status()
    return user, token, session_id


def _seed_button(session_id: str, user_id: str,
                 keyword: str = "人工智能",
                 skw_score: float = 0.25,
                 status: str = "pending") -> str:
    r = requests.post(f"{BASE_URL}/api/admin/test-seed/info-gap-button",
                      headers=ADMIN_HEADERS,
                      json={"session_id": session_id, "user_id": user_id,
                            "keyword": keyword, "skw_score": skw_score, "status": status})
    r.raise_for_status()
    return r.json()["id"]


def _seed_summary(session_id: str, content: str = "测试摘要", version: int = 1) -> str:
    r = requests.post(f"{BASE_URL}/api/admin/test-seed/discussion-summary",
                      headers=ADMIN_HEADERS,
                      json={"session_id": session_id, "content": content, "version": version})
    r.raise_for_status()
    return r.json()["id"]


def _seed_metrics(session_id: str, user_id: str,
                  speaking_ratio: float = 0.4,
                  ttr: float | None = 0.6) -> str:
    r = requests.post(f"{BASE_URL}/api/admin/test-seed/window-metrics",
                      headers=ADMIN_HEADERS,
                      json={"session_id": session_id, "user_id": user_id,
                            "speaking_ratio": speaking_ratio, "ttr": ttr})
    r.raise_for_status()
    return r.json()["id"]


# ══════════════════════════════════════════════════════════════════════════════
# GET /api/sessions/{id}/info-gap/buttons
# ══════════════════════════════════════════════════════════════════════════════

def test_buttons_empty():
    user, token, session_id = _setup_ongoing_session("BtnEmpty")
    r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/info-gap/buttons",
                     headers=_auth(token))
    _assert_log(r.status_code == 200 and r.json() == [],
                "GET buttons 无数据 → 空列表", r.text)


def test_buttons_returns_pending():
    user, token, session_id = _setup_ongoing_session("BtnPend")
    _seed_button(session_id, user["id"], keyword="机器学习")
    r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/info-gap/buttons",
                     headers=_auth(token))
    data = r.json()
    ok = r.status_code == 200 and len(data) == 1 and data[0]["keyword"] == "机器学习"
    _assert_log(ok, "GET buttons 返回 pending 按钮", r.text if not ok else None)


def test_buttons_excludes_non_pending():
    user, token, session_id = _setup_ongoing_session("BtnExcl")
    _seed_button(session_id, user["id"], keyword="A", status="pending")
    _seed_button(session_id, user["id"], keyword="B", status="clicked")
    _seed_button(session_id, user["id"], keyword="C", status="expired")
    r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/info-gap/buttons",
                     headers=_auth(token))
    data = r.json()
    ok = r.status_code == 200 and [d["keyword"] for d in data] == ["A"]
    _assert_log(ok, "GET buttons 过滤 clicked/expired", {"keywords": [d["keyword"] for d in data]})


def test_buttons_include_all_returns_pending_and_clicked():
    user, token, session_id = _setup_ongoing_session("BtnAll")
    _seed_button(session_id, user["id"], keyword="A", status="pending")
    _seed_button(session_id, user["id"], keyword="B", status="clicked")
    _seed_button(session_id, user["id"], keyword="C", status="expired")
    r = requests.get(
        f"{BASE_URL}/api/sessions/{session_id}/info-gap/buttons",
        headers=_auth(token),
        params={"include_all": "true"},
    )
    data = r.json()
    keywords = [d["keyword"] for d in data]
    ok = r.status_code == 200 and keywords == ["B", "A"]
    _assert_log(ok, "GET buttons include_all=true 返回 pending + clicked", {"keywords": keywords})


def test_buttons_403_non_member():
    _, _, session_id = _setup_ongoing_session("BtnForbid")
    _, outsider_token = _register_and_login("BtnOut")
    r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/info-gap/buttons",
                     headers=_auth(outsider_token))
    _assert_log(r.status_code == 403, "GET buttons 非成员 → 403", r.text)


def test_buttons_401_no_token():
    _, _, session_id = _setup_ongoing_session("BtnNoTok")
    r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/info-gap/buttons")
    _assert_log(r.status_code == 401, "GET buttons 无 token → 401", r.text)


# ══════════════════════════════════════════════════════════════════════════════
# GET /api/sessions/{id}/summary
# ══════════════════════════════════════════════════════════════════════════════

def test_summary_no_data():
    user, token, session_id = _setup_ongoing_session("SumEmpty")
    r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/summary",
                     headers=_auth(token))
    _assert_log(r.status_code == 404, "GET summary 无数据 → 404", r.text)


def test_summary_returns_latest_version():
    user, token, session_id = _setup_ongoing_session("SumLatest")
    _seed_summary(session_id, content="第一版", version=1)
    _seed_summary(session_id, content="第二版", version=2)
    _seed_summary(session_id, content="第三版", version=3)
    r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/summary",
                     headers=_auth(token))
    data = r.json()
    ok = r.status_code == 200 and data["version"] == 3 and data["content"] == "第三版"
    _assert_log(ok, "GET summary 返回最新版本", r.text if not ok else None)


def test_summary_history_returns_all_versions_desc():
    user, token, session_id = _setup_ongoing_session("SumHist")
    _seed_summary(session_id, content="第一版", version=1)
    _seed_summary(session_id, content="第二版", version=2)
    _seed_summary(session_id, content="第三版", version=3)
    r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/summaries",
                     headers=_auth(token))
    data = r.json()
    versions = [item["version"] for item in data]
    ok = r.status_code == 200 and versions == [3, 2, 1]
    _assert_log(ok, "GET summaries 返回全部历史版本（最新在前）", {"versions": versions})


def test_summary_fields_complete():
    user, token, session_id = _setup_ongoing_session("SumFields")
    _seed_summary(session_id, content="完整字段", version=1)
    r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/summary",
                     headers=_auth(token))
    data = r.json()
    required = {"id", "session_id", "version", "content", "window_start", "window_end", "created_at"}
    ok = r.status_code == 200 and required.issubset(data.keys())
    _assert_log(ok, "GET summary 字段完整", set(data.keys()) if not ok else None)


def test_summary_403_non_member():
    _, _, session_id = _setup_ongoing_session("SumFb")
    _, outsider_token = _register_and_login("SumFbOut")
    r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/summary",
                     headers=_auth(outsider_token))
    _assert_log(r.status_code == 403, "GET summary 非成员 → 403", r.text)


def test_summary_401_no_token():
    _, _, session_id = _setup_ongoing_session("SumNoTok")
    r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/summary")
    _assert_log(r.status_code == 401, "GET summary 无 token → 401", r.text)


def test_summary_invalid_session():
    _, token, _ = _setup_ongoing_session("SumInv")
    r = requests.get(f"{BASE_URL}/api/sessions/s_nonexistent/summary",
                     headers=_auth(token))
    _assert_log(r.status_code in (403, 404), "GET summary 会话不存在 → 403/404", r.text)


# ══════════════════════════════════════════════════════════════════════════════
# GET /api/sessions/{id}/window-metrics
# ══════════════════════════════════════════════════════════════════════════════

def test_metrics_403_non_admin():
    user, token, session_id = _setup_ongoing_session("WMFb")
    r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/window-metrics",
                     headers=_auth(token))
    _assert_log(r.status_code == 403, "GET window-metrics 普通用户 → 403", r.text)


def test_metrics_404_no_data():
    _, _, session_id = _setup_ongoing_session("WMEmpty")
    r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/window-metrics",
                     headers=ADMIN_HEADERS)
    _assert_log(r.status_code == 404, "GET window-metrics 无数据 → 404", r.text)


def test_metrics_returns_data():
    user, token, session_id = _setup_ongoing_session("WMData")
    _seed_metrics(session_id, user["id"], speaking_ratio=0.6)
    r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/window-metrics",
                     headers=ADMIN_HEADERS)
    data = r.json()
    ok = r.status_code == 200 and len(data) >= 1 and data[0]["speaking_ratio"] == 0.6
    _assert_log(ok, "GET window-metrics 返回数据", r.text if not ok else None)


def test_metrics_fields_complete():
    user, token, session_id = _setup_ongoing_session("WMFields")
    _seed_metrics(session_id, user["id"])
    r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/window-metrics",
                     headers=ADMIN_HEADERS)
    data = r.json()
    required = {"id", "session_id", "user_id", "window_start", "window_end",
                "speaking_ratio", "silence_s", "ttr", "arg_density",
                "srep", "info_gain", "has_reasoning", "has_evidence",
                "reasoning_source", "evidence_source", "created_at"}
    ok = r.status_code == 200 and len(data) > 0 and required.issubset(data[0].keys())
    _assert_log(ok, "GET window-metrics 字段完整", None)


def test_metrics_null_fields_ok():
    user, token, session_id = _setup_ongoing_session("WMNull")
    _seed_metrics(session_id, user["id"], ttr=None)
    r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/window-metrics",
                     headers=ADMIN_HEADERS)
    data = r.json()
    ok = r.status_code == 200 and data[0]["ttr"] is None
    _assert_log(ok, "GET window-metrics null 字段正常返回", r.text if not ok else None)


def test_metrics_invalid_session():
    r = requests.get(f"{BASE_URL}/api/sessions/s_nonexistent/window-metrics",
                     headers=ADMIN_HEADERS)
    _assert_log(r.status_code == 404, "GET window-metrics 会话不存在 → 404", r.text)


# ══════════════════════════════════════════════════════════════════════════════
# 入口
# ══════════════════════════════════════════════════════════════════════════════

def main():
    results = []
    print("\n===== GET info-gap/buttons =====")
    results += [
        test_buttons_empty(),
        test_buttons_returns_pending(),
        test_buttons_excludes_non_pending(),
        test_buttons_include_all_returns_pending_and_clicked(),
        test_buttons_403_non_member(),
        test_buttons_401_no_token(),
    ]
    print("\n===== GET summary =====")
    results += [
        test_summary_no_data(),
        test_summary_returns_latest_version(),
        test_summary_history_returns_all_versions_desc(),
        test_summary_fields_complete(),
        test_summary_403_non_member(),
        test_summary_401_no_token(),
        test_summary_invalid_session(),
    ]
    print("\n===== GET window-metrics =====")
    results += [
        test_metrics_403_non_admin(),
        test_metrics_404_no_data(),
        test_metrics_returns_data(),
        test_metrics_fields_complete(),
        test_metrics_null_fields_ok(),
        test_metrics_invalid_session(),
    ]

    passed = sum(results)
    total = len(results)
    print(f"\n{'='*40}")
    print(f"结果：{passed}/{total} 通过")
    if passed < total:
        print("⚠️  有用例失败，请检查上方详情")


if __name__ == "__main__":
    main()
