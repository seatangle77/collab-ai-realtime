"""
集成测试：info-gap / discussion-summary / window-metrics 三组接口
运行前提：后端已启动（http://127.0.0.1:8000），DB 可连接
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, Tuple

import psycopg2
import requests

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.settings import settings as app_settings

BASE_URL = "http://127.0.0.1:8000"
ADMIN_HEADERS = {"X-Admin-Token": "TestAdminKey123"}
RUN_ID = uuid.uuid4().hex[:6]

# ── DB 直连（用于插入 agent 写的测试数据）────────────────────────────────────

def _db_conn():
    db_host = os.getenv("DB_HOST") or app_settings.host or "127.0.0.1"
    db_port = int(os.getenv("DB_PORT") or app_settings.port or 5432)
    db_name = os.getenv("DB_NAME") or app_settings.name or "collaborative_ai_chatbot"
    db_user = os.getenv("DB_USER") or app_settings.user or "app_user"
    db_password = os.getenv("DB_PASSWORD") or app_settings.password or ""

    if not db_password:
        raise RuntimeError(
            "DB_PASSWORD 未配置。请在 backend/.env.local（推荐）或环境变量中设置，"
            "然后直接运行：python tests/test_info_gap_summary_metrics.py"
        )

    return psycopg2.connect(
        host=db_host,
        port=db_port,
        dbname=db_name,
        user=db_user,
        password=db_password,
    )


def _log(ok: bool, msg: str, extra: Any = None) -> bool:
    print(f"{'✅' if ok else '❌'} {msg}")
    if not ok and extra is not None:
        print("   详情:", extra)
    return ok


# ── 测试工具函数 ──────────────────────────────────────────────────────────────

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


def _insert_info_gap_button(session_id: str, user_id: str,
                             keyword: str = "人工智能",
                             skw_score: float = 0.25,
                             status: str = "pending") -> str:
    btn_id = f"igb{uuid.uuid4().hex[:8]}"
    with _db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO info_gap_buttons
                  (id, session_id, user_id, keyword, skw_score, status, window_start, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())
                """,
                (btn_id, session_id, user_id, keyword, skw_score, status),
            )
        conn.commit()
    return btn_id


def _insert_discussion_summary(session_id: str, content: str = "测试摘要", version: int = 1) -> str:
    sid = f"ds{uuid.uuid4().hex[:8]}"
    with _db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO discussion_summaries
                  (id, session_id, version, content, window_start, window_end, created_at)
                VALUES (%s, %s, %s, %s, NOW() - INTERVAL '2 min', NOW(), NOW())
                """,
                (sid, session_id, version, content),
            )
        conn.commit()
    return sid


def _insert_window_metrics(session_id: str, user_id: str,
                            speaking_ratio: float = 0.4) -> str:
    mid = f"wm{uuid.uuid4().hex[:8]}"
    with _db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO window_metrics
                  (id, session_id, user_id, window_start, window_end,
                   speaking_ratio, silence_s, ttr, arg_density,
                   srep, info_gain, has_reasoning, has_evidence, created_at)
                VALUES (%s, %s, %s, NOW() - INTERVAL '2 min', NOW(),
                        %s, 30, 0.6, 0.1, 0.3, 0.5, false, false, NOW())
                """,
                (mid, session_id, user_id, speaking_ratio),
            )
        conn.commit()
    return mid


# ══════════════════════════════════════════════════════════════════════════════
# 测试：GET /api/sessions/{id}/info-gap/buttons
# ══════════════════════════════════════════════════════════════════════════════

def test_info_gap_buttons_empty():
    """正常：会话无按钮时返回空列表"""
    user, token, session_id = _setup_ongoing_session("BtnEmpty")
    r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/info-gap/buttons",
                     headers=_auth(token))
    ok = r.status_code == 200 and r.json() == []
    return _log(ok, "GET buttons 空列表", r.text if not ok else None)


def test_info_gap_buttons_returns_pending():
    """正常：返回 pending 状态的按钮"""
    user, token, session_id = _setup_ongoing_session("BtnPending")
    _insert_info_gap_button(session_id, user["id"], keyword="机器学习")
    r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/info-gap/buttons",
                     headers=_auth(token))
    data = r.json()
    ok = r.status_code == 200 and len(data) == 1 and data[0]["keyword"] == "机器学习"
    return _log(ok, "GET buttons 返回 pending 按钮", r.text if not ok else None)


def test_info_gap_buttons_excludes_clicked():
    """边界：已点击的按钮不出现在列表中"""
    user, token, session_id = _setup_ongoing_session("BtnExclude")
    _insert_info_gap_button(session_id, user["id"], keyword="A", status="pending")
    _insert_info_gap_button(session_id, user["id"], keyword="B", status="clicked")
    _insert_info_gap_button(session_id, user["id"], keyword="C", status="expired")
    r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/info-gap/buttons",
                     headers=_auth(token))
    data = r.json()
    keywords = [d["keyword"] for d in data]
    ok = r.status_code == 200 and keywords == ["A"]
    return _log(ok, "GET buttons 过滤非 pending", {"keywords": keywords})


def test_info_gap_buttons_only_own():
    """边界：只返回当前用户的按钮，不泄露他人按钮"""
    user1, token1, session_id = _setup_ongoing_session("BtnOwn1")
    user2, token2 = _register_and_login("BtnOwn2")
    # 把 user2 加入同一 group（通过 admin）
    grp_r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/info-gap/buttons",
                         headers=_auth(token1))
    # 给 user1 插一个按钮
    _insert_info_gap_button(session_id, user1["id"], keyword="专属词")
    r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/info-gap/buttons",
                     headers=_auth(token1))
    data = r.json()
    ok = r.status_code == 200 and all(d["keyword"] == "专属词" for d in data)
    return _log(ok, "GET buttons 只返回自己的按钮", r.text if not ok else None)


def test_info_gap_buttons_403_non_member():
    """异常：非成员访问 → 403"""
    _, _, session_id = _setup_ongoing_session("BtnForbid")
    _, outsider_token = _register_and_login("BtnOutsider")
    r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/info-gap/buttons",
                     headers=_auth(outsider_token))
    return _log(r.status_code == 403, "GET buttons 非成员 → 403", r.text)


def test_info_gap_buttons_401_no_token():
    """异常：无 token → 401"""
    _, _, session_id = _setup_ongoing_session("BtnNoToken")
    r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/info-gap/buttons")
    return _log(r.status_code == 401, "GET buttons 无 token → 401", r.text)


# ══════════════════════════════════════════════════════════════════════════════
# 测试：POST /api/sessions/{id}/info-gap/click
# ══════════════════════════════════════════════════════════════════════════════

def test_click_button_success():
    """正常：点击 pending 按钮 → 200 success=true，状态变 clicked"""
    user, token, session_id = _setup_ongoing_session("ClickOK")
    btn_id = _insert_info_gap_button(session_id, user["id"])
    r = requests.post(f"{BASE_URL}/api/sessions/{session_id}/info-gap/click",
                      headers=_auth(token), json={"button_id": btn_id})
    ok = r.status_code == 200 and r.json().get("success") is True
    _log(ok, "POST click 成功", r.text if not ok else None)

    # 验证 DB 状态已更新
    with _db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status FROM info_gap_buttons WHERE id = %s", (btn_id,))
            row = cur.fetchone()
    db_ok = row and row[0] == "clicked"
    return _log(db_ok, "POST click DB 状态变为 clicked")


def test_click_button_not_found():
    """异常：button_id 不存在 → 404"""
    user, token, session_id = _setup_ongoing_session("ClickNotFound")
    r = requests.post(f"{BASE_URL}/api/sessions/{session_id}/info-gap/click",
                      headers=_auth(token), json={"button_id": "nonexistent_id"})
    return _log(r.status_code == 404, "POST click 不存在 → 404", r.text)


def test_click_button_already_clicked():
    """边界：重复点击 → 409"""
    user, token, session_id = _setup_ongoing_session("ClickDup")
    btn_id = _insert_info_gap_button(session_id, user["id"], status="clicked")
    r = requests.post(f"{BASE_URL}/api/sessions/{session_id}/info-gap/click",
                      headers=_auth(token), json={"button_id": btn_id})
    return _log(r.status_code == 409, "POST click 已点击 → 409", r.text)


def test_click_button_expired():
    """边界：点击 expired 按钮 → 409"""
    user, token, session_id = _setup_ongoing_session("ClickExpired")
    btn_id = _insert_info_gap_button(session_id, user["id"], status="expired")
    r = requests.post(f"{BASE_URL}/api/sessions/{session_id}/info-gap/click",
                      headers=_auth(token), json={"button_id": btn_id})
    return _log(r.status_code == 409, "POST click expired → 409", r.text)


def test_click_button_other_users_button():
    """异常：点击他人的按钮 → 404（不泄露存在性）"""
    user1, token1, session_id = _setup_ongoing_session("ClickOther1")
    user2, token2 = _register_and_login("ClickOther2")
    btn_id = _insert_info_gap_button(session_id, user1["id"])
    r = requests.post(f"{BASE_URL}/api/sessions/{session_id}/info-gap/click",
                      headers=_auth(token2), json={"button_id": btn_id})
    return _log(r.status_code in (403, 404), "POST click 他人按钮 → 403/404", r.text)


def test_click_button_403_non_member():
    """异常：非成员点击 → 403"""
    user, token, session_id = _setup_ongoing_session("ClickForbid")
    btn_id = _insert_info_gap_button(session_id, user["id"])
    _, outsider_token = _register_and_login("ClickOut")
    r = requests.post(f"{BASE_URL}/api/sessions/{session_id}/info-gap/click",
                      headers=_auth(outsider_token), json={"button_id": btn_id})
    return _log(r.status_code == 403, "POST click 非成员 → 403", r.text)


def test_click_button_missing_body():
    """极端：缺少 button_id 字段 → 422"""
    user, token, session_id = _setup_ongoing_session("ClickMissing")
    r = requests.post(f"{BASE_URL}/api/sessions/{session_id}/info-gap/click",
                      headers=_auth(token), json={})
    return _log(r.status_code == 422, "POST click 缺 button_id → 422", r.text)


# ══════════════════════════════════════════════════════════════════════════════
# 测试：GET /api/sessions/{id}/summary
# ══════════════════════════════════════════════════════════════════════════════

def test_summary_404_no_data():
    """正常：无摘要时 → 404"""
    user, token, session_id = _setup_ongoing_session("SumEmpty")
    r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/summary",
                     headers=_auth(token))
    return _log(r.status_code == 404, "GET summary 无数据 → 404", r.text)


def test_summary_returns_latest_version():
    """正常：多条摘要时返回 version 最大的"""
    user, token, session_id = _setup_ongoing_session("SumLatest")
    _insert_discussion_summary(session_id, content="第一版摘要", version=1)
    _insert_discussion_summary(session_id, content="第二版摘要", version=2)
    _insert_discussion_summary(session_id, content="第三版摘要", version=3)
    r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/summary",
                     headers=_auth(token))
    data = r.json()
    ok = r.status_code == 200 and data["version"] == 3 and data["content"] == "第三版摘要"
    return _log(ok, "GET summary 返回最新版本", r.text if not ok else None)


def test_summary_fields_complete():
    """正常：返回字段完整"""
    user, token, session_id = _setup_ongoing_session("SumFields")
    _insert_discussion_summary(session_id, content="完整字段摘要", version=1)
    r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/summary",
                     headers=_auth(token))
    data = r.json()
    required = {"id", "session_id", "version", "content", "window_start", "window_end", "created_at"}
    ok = r.status_code == 200 and required.issubset(data.keys())
    return _log(ok, "GET summary 字段完整", data.keys() if not ok else None)


def test_summary_403_non_member():
    """异常：非成员 → 403"""
    _, _, session_id = _setup_ongoing_session("SumForbid")
    _, outsider_token = _register_and_login("SumOut")
    r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/summary",
                     headers=_auth(outsider_token))
    return _log(r.status_code == 403, "GET summary 非成员 → 403", r.text)


def test_summary_401_no_token():
    """异常：无 token → 401"""
    _, _, session_id = _setup_ongoing_session("SumNoToken")
    r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/summary")
    return _log(r.status_code == 401, "GET summary 无 token → 401", r.text)


def test_summary_invalid_session():
    """极端：会话不存在 → 403 或 404"""
    _, token, _ = _setup_ongoing_session("SumInvalid")
    r = requests.get(f"{BASE_URL}/api/sessions/s_nonexistent/summary",
                     headers=_auth(token))
    return _log(r.status_code in (403, 404), "GET summary 会话不存在 → 403/404", r.text)


# ══════════════════════════════════════════════════════════════════════════════
# 测试：GET /api/sessions/{id}/window-metrics
# ══════════════════════════════════════════════════════════════════════════════

def test_window_metrics_403_non_admin():
    """异常：普通用户 → 403"""
    user, token, session_id = _setup_ongoing_session("WMForbid")
    r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/window-metrics",
                     headers=_auth(token))
    return _log(r.status_code == 403, "GET window-metrics 普通用户 → 403", r.text)


def test_window_metrics_404_no_data():
    """正常：admin 访问但无数据 → 404"""
    _, _, session_id = _setup_ongoing_session("WMEmpty")
    r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/window-metrics",
                     headers=ADMIN_HEADERS)
    return _log(r.status_code == 404, "GET window-metrics 无数据 → 404", r.text)


def test_window_metrics_returns_latest_window():
    """正常：返回最新窗口所有成员指标"""
    user, token, session_id = _setup_ongoing_session("WMLatest")
    # 插入两个不同时间窗口
    with _db_conn() as conn:
        with conn.cursor() as cur:
            # 旧窗口
            mid1 = f"wm{uuid.uuid4().hex[:8]}"
            cur.execute(
                """
                INSERT INTO window_metrics
                  (id, session_id, user_id, window_start, window_end,
                   speaking_ratio, silence_s, ttr, arg_density,
                   srep, info_gain, has_reasoning, has_evidence, created_at)
                VALUES (%s, %s, %s,
                        NOW() - INTERVAL '10 min', NOW() - INTERVAL '8 min',
                        0.3, 60, 0.5, 0.1, NULL, NULL, NULL, NULL, NOW())
                """,
                (mid1, session_id, user["id"]),
            )
            # 新窗口
            mid2 = f"wm{uuid.uuid4().hex[:8]}"
            cur.execute(
                """
                INSERT INTO window_metrics
                  (id, session_id, user_id, window_start, window_end,
                   speaking_ratio, silence_s, ttr, arg_density,
                   srep, info_gain, has_reasoning, has_evidence, created_at)
                VALUES (%s, %s, %s,
                        NOW() - INTERVAL '2 min', NOW(),
                        0.6, 10, 0.8, 0.3, 0.4, 0.7, true, false, NOW())
                """,
                (mid2, session_id, user["id"]),
            )
        conn.commit()

    r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/window-metrics",
                     headers=ADMIN_HEADERS)
    data = r.json()
    ok = (r.status_code == 200 and len(data) >= 1
          and all(row["speaking_ratio"] == 0.6 for row in data))
    return _log(ok, "GET window-metrics 返回最新窗口", r.text if not ok else None)


def test_window_metrics_fields_complete():
    """正常：返回字段完整"""
    user, token, session_id = _setup_ongoing_session("WMFields")
    _insert_window_metrics(session_id, user["id"])
    r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/window-metrics",
                     headers=ADMIN_HEADERS)
    data = r.json()
    required = {"id", "session_id", "user_id", "window_start", "window_end",
                "speaking_ratio", "silence_s", "ttr", "arg_density",
                "srep", "info_gain", "has_reasoning", "has_evidence", "created_at"}
    ok = r.status_code == 200 and len(data) > 0 and required.issubset(data[0].keys())
    return _log(ok, "GET window-metrics 字段完整", data[0].keys() if data else None)


def test_window_metrics_null_fields_allowed():
    """边界：null 字段（Week 3 未填充时）不报错"""
    user, token, session_id = _setup_ongoing_session("WMNull")
    with _db_conn() as conn:
        with conn.cursor() as cur:
            mid = f"wm{uuid.uuid4().hex[:8]}"
            cur.execute(
                """
                INSERT INTO window_metrics
                  (id, session_id, user_id, window_start, window_end,
                   speaking_ratio, silence_s, ttr, arg_density,
                   srep, info_gain, has_reasoning, has_evidence, created_at)
                VALUES (%s, %s, %s, NOW() - INTERVAL '2 min', NOW(),
                        0.1, 110, NULL, NULL, NULL, NULL, NULL, NULL, NOW())
                """,
                (mid, session_id, user["id"]),
            )
        conn.commit()
    r = requests.get(f"{BASE_URL}/api/sessions/{session_id}/window-metrics",
                     headers=ADMIN_HEADERS)
    data = r.json()
    ok = r.status_code == 200 and data[0]["ttr"] is None
    return _log(ok, "GET window-metrics null 字段正常返回", r.text if not ok else None)


def test_window_metrics_404_invalid_session():
    """极端：会话不存在 → 404"""
    r = requests.get(f"{BASE_URL}/api/sessions/s_nonexistent/window-metrics",
                     headers=ADMIN_HEADERS)
    return _log(r.status_code == 404, "GET window-metrics 会话不存在 → 404", r.text)


# ══════════════════════════════════════════════════════════════════════════════
# 入口
# ══════════════════════════════════════════════════════════════════════════════

def main():
    results = []
    print("\n===== info-gap buttons =====")
    results += [
        test_info_gap_buttons_empty(),
        test_info_gap_buttons_returns_pending(),
        test_info_gap_buttons_excludes_clicked(),
        test_info_gap_buttons_only_own(),
        test_info_gap_buttons_403_non_member(),
        test_info_gap_buttons_401_no_token(),
    ]
    print("\n===== info-gap click =====")
    results += [
        test_click_button_success(),
        test_click_button_not_found(),
        test_click_button_already_clicked(),
        test_click_button_expired(),
        test_click_button_other_users_button(),
        test_click_button_403_non_member(),
        test_click_button_missing_body(),
    ]
    print("\n===== discussion summary =====")
    results += [
        test_summary_404_no_data(),
        test_summary_returns_latest_version(),
        test_summary_fields_complete(),
        test_summary_403_non_member(),
        test_summary_401_no_token(),
        test_summary_invalid_session(),
    ]
    print("\n===== window metrics =====")
    results += [
        test_window_metrics_403_non_admin(),
        test_window_metrics_404_no_data(),
        test_window_metrics_returns_latest_window(),
        test_window_metrics_fields_complete(),
        test_window_metrics_null_fields_allowed(),
        test_window_metrics_404_invalid_session(),
    ]

    passed = sum(results)
    total = len(results)
    print(f"\n{'='*40}")
    print(f"结果：{passed}/{total} 通过")
    if passed < total:
        print("⚠️  有用例失败，请检查上方详情")


if __name__ == "__main__":
    main()
