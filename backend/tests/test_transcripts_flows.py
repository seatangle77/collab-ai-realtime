"""
Integration tests for transcript endpoints:
  用户端: GET /api/sessions/{session_id}/transcripts
  管理端: POST/GET/PATCH/DELETE/batch-delete /api/admin/transcripts/
"""
from __future__ import annotations

import uuid
from typing import Any

import requests

BASE_URL = "http://127.0.0.1:8000"
RUN_ID = uuid.uuid4().hex[:6]

ADMIN_TOKEN = "TestAdminKey123"
ADMIN_HEADERS = {"X-Admin-Token": ADMIN_TOKEN}


# ─────────────────────────── helpers ────────────────────────────────────────

def _log(ok: bool, msg: str, extra: Any = None) -> bool:
    print(f"{'✅' if ok else '❌'} {msg}")
    if not ok and extra is not None:
        print("   详情:", extra)
    return ok


def _register_login(suffix: str) -> tuple[str, str]:
    email = f"tr_{suffix}_{uuid.uuid4().hex[:6]}@example.com"
    r = requests.post(f"{BASE_URL}/api/auth/register", json={
        "name": f"tr_{suffix}",
        "email": email,
        "password": "1234",
        "device_token": f"dev-tr-{suffix}-{uuid.uuid4().hex[:8]}",
    })
    r.raise_for_status()
    user_id = r.json()["id"]
    r2 = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": "1234"})
    r2.raise_for_status()
    return r2.json()["access_token"], user_id


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _setup() -> dict:
    """
    创建完整测试环境：leader + member + outsider → 建群 → member 加入
    → 建会话 → start 会话，返回上下文 ctx。
    """
    leader_token, leader_id = _register_login(f"leader_{RUN_ID}")
    member_token, member_id = _register_login(f"member_{RUN_ID}")
    outsider_token, outsider_id = _register_login(f"outsider_{RUN_ID}")

    # leader 建群（注册时已有 default group，这里建一个测试专用群）
    r = requests.post(f"{BASE_URL}/api/groups", json={"name": f"tr_group_{RUN_ID}"},
                      headers=_auth(leader_token))
    r.raise_for_status()
    group = r.json()["group"]
    group_id = group["id"]

    # member 加入
    requests.post(f"{BASE_URL}/api/groups/{group_id}/join", headers=_auth(member_token)).raise_for_status()

    # leader 建会话
    r = requests.post(f"{BASE_URL}/api/groups/{group_id}/sessions",
                      json={"session_title": f"tr_session_{RUN_ID}"},
                      headers=_auth(leader_token))
    r.raise_for_status()
    session_id = r.json()["id"]

    # leader 发起会话（start）
    requests.post(f"{BASE_URL}/api/sessions/{session_id}/start",
                  headers=_auth(leader_token)).raise_for_status()

    return {
        "leader_token": leader_token, "leader_id": leader_id,
        "member_token": member_token, "member_id": member_id,
        "outsider_token": outsider_token,
        "group_id": group_id,
        "session_id": session_id,
    }


def _create_transcript(ctx: dict, **overrides) -> dict:
    """通过 admin 创建一条 transcript，返回完整 JSON。"""
    payload = {
        "session_id": ctx["session_id"],
        "group_id": ctx["group_id"],
        "text": "测试内容",
        "start": "2026-03-17T10:00:00",
        "end": "2026-03-17T10:00:05",
        "speaker": "张三",
        "duration": 5.0,
        "confidence": 0.95,
    }
    payload.update(overrides)
    r = requests.post(f"{BASE_URL}/api/admin/transcripts/", json=payload, headers=ADMIN_HEADERS)
    r.raise_for_status()
    return r.json()


# ═══════════════════════════════════════════════════════════════════════════
# A. 用户端 GET /api/sessions/{session_id}/transcripts
# ═══════════════════════════════════════════════════════════════════════════

def scenario_user_get_transcripts_unauth(ctx: dict) -> bool:
    r = requests.get(f"{BASE_URL}/api/sessions/{ctx['session_id']}/transcripts")
    ok = _log(r.status_code == 401, "A1 未登录查询 → 401", r.text)
    return ok


def scenario_user_get_transcripts_not_member(ctx: dict) -> bool:
    r = requests.get(f"{BASE_URL}/api/sessions/{ctx['session_id']}/transcripts",
                     headers=_auth(ctx["outsider_token"]))
    ok = _log(r.status_code == 403, "A2 非成员查询 → 403", r.text)
    return ok


def scenario_user_get_transcripts_not_found(ctx: dict) -> bool:
    r = requests.get(f"{BASE_URL}/api/sessions/s_nonexist_999/transcripts",
                     headers=_auth(ctx["leader_token"]))
    ok = _log(r.status_code == 404, "A3 不存在的 session → 404", r.text)
    return ok


def scenario_user_get_transcripts_empty(ctx: dict) -> bool:
    r = requests.get(f"{BASE_URL}/api/sessions/{ctx['session_id']}/transcripts",
                     headers=_auth(ctx["leader_token"]))
    ok = r.status_code == 200 and isinstance(r.json(), list)
    _log(ok, "A4 成员查询空列表 → 200 list", r.text if not ok else None)
    return ok


def scenario_user_get_transcripts_with_data(ctx: dict) -> bool:
    tr = _create_transcript(ctx)
    r = requests.get(f"{BASE_URL}/api/sessions/{ctx['session_id']}/transcripts",
                     headers=_auth(ctx["member_token"]))
    items = r.json()
    ok = r.status_code == 200 and any(i["transcript_id"] == tr["transcript_id"] for i in items)
    _log(ok, "A5 admin 创建后成员可见 → 200 含新记录", r.text if not ok else None)
    return ok


def scenario_user_get_transcripts_fields(ctx: dict) -> bool:
    r = requests.get(f"{BASE_URL}/api/sessions/{ctx['session_id']}/transcripts",
                     headers=_auth(ctx["leader_token"]))
    items = r.json()
    if not items:
        _log(False, "A6 字段校验：列表为空，无法校验")
        return False
    item = items[0]
    required = {"transcript_id", "group_id", "session_id", "user_id", "speaker",
                 "text", "start", "end", "duration", "confidence", "created_at"}
    missing = required - set(item.keys())
    ok = not missing
    _log(ok, "A6 TranscriptOut 字段完整", missing if not ok else None)
    # 管理端专用字段不应出现
    admin_only = {"audio_url", "original_text", "is_edited"}
    leaked = admin_only & set(item.keys())
    ok2 = not leaked
    _log(ok2, "A6 用户端不含管理端专用字段", leaked if not ok2 else None)
    return ok and ok2


def scenario_user_get_transcripts_order_asc(ctx: dict) -> bool:
    """验证排序 start ASC"""
    _create_transcript(ctx, start="2026-03-17T10:00:10", end="2026-03-17T10:00:15")
    r = requests.get(f"{BASE_URL}/api/sessions/{ctx['session_id']}/transcripts",
                     headers=_auth(ctx["leader_token"]))
    items = r.json()
    if len(items) < 2:
        _log(False, "A7 排序校验：记录不足 2 条")
        return False
    starts = [i["start"] for i in items]
    ok = starts == sorted(starts)
    _log(ok, "A7 排序 start ASC 正确", starts if not ok else None)
    return ok


# ═══════════════════════════════════════════════════════════════════════════
# B. Admin 创建 transcript
# ═══════════════════════════════════════════════════════════════════════════

def scenario_admin_create_unauth(ctx: dict) -> bool:
    r = requests.post(f"{BASE_URL}/api/admin/transcripts/", json={
        "session_id": ctx["session_id"], "group_id": ctx["group_id"],
        "text": "hi", "start": "2026-03-17T10:00:00", "end": "2026-03-17T10:00:05",
    })
    ok = _log(r.status_code in (401, 403), "B1 无 admin token → 401/403", r.text)
    return ok


def scenario_admin_create_invalid_session(ctx: dict) -> bool:
    r = requests.post(f"{BASE_URL}/api/admin/transcripts/", json={
        "session_id": "s_nonexist_999", "group_id": ctx["group_id"],
        "text": "hi", "start": "2026-03-17T10:00:00", "end": "2026-03-17T10:00:05",
    }, headers=ADMIN_HEADERS)
    ok = _log(r.status_code == 404, "B2 session 不存在 → 404", r.text)
    return ok


def scenario_admin_create_invalid_group(ctx: dict) -> bool:
    r = requests.post(f"{BASE_URL}/api/admin/transcripts/", json={
        "session_id": ctx["session_id"], "group_id": "g_nonexist_999",
        "text": "hi", "start": "2026-03-17T10:00:00", "end": "2026-03-17T10:00:05",
    }, headers=ADMIN_HEADERS)
    ok = _log(r.status_code == 404, "B3 group 不存在 → 404", r.text)
    return ok


def scenario_admin_create_missing_fields(ctx: dict) -> bool:
    # 缺少 start / end
    r = requests.post(f"{BASE_URL}/api/admin/transcripts/", json={
        "session_id": ctx["session_id"], "group_id": ctx["group_id"], "text": "hi",
    }, headers=ADMIN_HEADERS)
    ok = _log(r.status_code == 422, "B4 缺少必填字段 → 422", r.text)
    return ok


def scenario_admin_create_success(ctx: dict) -> bool:
    tr = _create_transcript(ctx)
    ok1 = tr["transcript_id"].startswith("tr")
    ok2 = tr["is_edited"] is False
    ok3 = tr["original_text"] is None
    ok = ok1 and ok2 and ok3
    _log(ok, "B5 admin 创建成功：tr 前缀 / is_edited=false / original_text=null",
         tr if not ok else None)
    return ok


# ═══════════════════════════════════════════════════════════════════════════
# C. Admin GET 列表
# ═══════════════════════════════════════════════════════════════════════════

def scenario_admin_list_unauth(ctx: dict) -> bool:
    r = requests.get(f"{BASE_URL}/api/admin/transcripts/")
    ok = _log(r.status_code in (401, 403), "C1 无 admin token 列表 → 401/403", r.text)
    return ok


def scenario_admin_list_basic(ctx: dict) -> bool:
    r = requests.get(f"{BASE_URL}/api/admin/transcripts/", headers=ADMIN_HEADERS)
    d = r.json()
    ok = r.status_code == 200 and "items" in d and "meta" in d
    _log(ok, "C2 默认分页结构 items+meta", r.text if not ok else None)
    return ok


def scenario_admin_list_filter_session(ctx: dict) -> bool:
    r = requests.get(f"{BASE_URL}/api/admin/transcripts/",
                     params={"session_id": ctx["session_id"]},
                     headers=ADMIN_HEADERS)
    items = r.json()["items"]
    ok = r.status_code == 200 and all(i["session_id"] == ctx["session_id"] for i in items)
    _log(ok, "C3 按 session_id 过滤", r.text if not ok else None)
    return ok


def scenario_admin_list_filter_group(ctx: dict) -> bool:
    r = requests.get(f"{BASE_URL}/api/admin/transcripts/",
                     params={"group_id": ctx["group_id"]},
                     headers=ADMIN_HEADERS)
    items = r.json()["items"]
    ok = r.status_code == 200 and all(i["group_id"] == ctx["group_id"] for i in items)
    _log(ok, "C4 按 group_id 过滤", r.text if not ok else None)
    return ok


def scenario_admin_list_filter_speaker_user(ctx: dict) -> bool:
    # 创建一条绑定 user_id 的记录
    tr = _create_transcript(ctx, user_id=ctx["leader_id"])
    r = requests.get(f"{BASE_URL}/api/admin/transcripts/",
                     params={"speaker_user_id": ctx["leader_id"]},
                     headers=ADMIN_HEADERS)
    items = r.json()["items"]
    ok = r.status_code == 200 and any(i["transcript_id"] == tr["transcript_id"] for i in items)
    _log(ok, "C5 按 speaker_user_id(user_id) 过滤", r.text if not ok else None)
    return ok


def scenario_admin_list_filter_date_range(ctx: dict) -> bool:
    r = requests.get(f"{BASE_URL}/api/admin/transcripts/",
                     params={
                         "session_id": ctx["session_id"],
                         "created_from": "2020-01-01T00:00:00",
                         "created_to": "2099-01-01T00:00:00",
                     },
                     headers=ADMIN_HEADERS)
    ok = r.status_code == 200
    _log(ok, "C6 时间区间过滤不报错", r.text if not ok else None)
    return ok


def scenario_admin_list_pagination(ctx: dict) -> bool:
    r = requests.get(f"{BASE_URL}/api/admin/transcripts/",
                     params={"session_id": ctx["session_id"], "page": 1, "page_size": 1},
                     headers=ADMIN_HEADERS)
    d = r.json()
    ok = r.status_code == 200 and len(d["items"]) <= 1 and d["meta"]["page_size"] == 1
    _log(ok, "C7 page_size=1 分页正确", r.text if not ok else None)
    return ok


def scenario_admin_list_page_size_over_limit(ctx: dict) -> bool:
    r = requests.get(f"{BASE_URL}/api/admin/transcripts/",
                     params={"page_size": 101},
                     headers=ADMIN_HEADERS)
    ok = _log(r.status_code == 422, "C8 page_size=101 超限 → 422", r.text)
    return ok


def scenario_admin_list_order_asc(ctx: dict) -> bool:
    r = requests.get(f"{BASE_URL}/api/admin/transcripts/",
                     params={"session_id": ctx["session_id"]},
                     headers=ADMIN_HEADERS)
    items = r.json()["items"]
    if len(items) < 2:
        _log(True, "C9 排序校验：记录不足 2 条，跳过")
        return True
    starts = [i["start"] for i in items]
    ok = starts == sorted(starts)
    _log(ok, "C9 列表排序 start ASC", starts if not ok else None)
    return ok


# ═══════════════════════════════════════════════════════════════════════════
# D. Admin PATCH 修正文本
# ═══════════════════════════════════════════════════════════════════════════

def scenario_admin_patch_unauth(ctx: dict) -> bool:
    tr = _create_transcript(ctx)
    r = requests.patch(f"{BASE_URL}/api/admin/transcripts/{tr['transcript_id']}",
                       json={"text": "修正"})
    ok = _log(r.status_code in (401, 403), "D1 无 admin token PATCH → 401/403", r.text)
    return ok


def scenario_admin_patch_not_found(ctx: dict) -> bool:
    r = requests.patch(f"{BASE_URL}/api/admin/transcripts/tr_nonexist_999",
                       json={"text": "修正"}, headers=ADMIN_HEADERS)
    ok = _log(r.status_code == 404, "D2 不存在的 transcript → 404", r.text)
    return ok


def scenario_admin_patch_missing_text(ctx: dict) -> bool:
    tr = _create_transcript(ctx)
    r = requests.patch(f"{BASE_URL}/api/admin/transcripts/{tr['transcript_id']}",
                       json={}, headers=ADMIN_HEADERS)
    ok = _log(r.status_code == 422, "D3 缺少 text 字段 → 422", r.text)
    return ok


def scenario_admin_patch_success(ctx: dict) -> bool:
    tr = _create_transcript(ctx, text="原始内容")
    r = requests.patch(f"{BASE_URL}/api/admin/transcripts/{tr['transcript_id']}",
                       json={"text": "修正后内容"}, headers=ADMIN_HEADERS)
    d = r.json()
    ok = (r.status_code == 200
          and d["text"] == "修正后内容"
          and d["original_text"] == "原始内容"
          and d["is_edited"] is True)
    _log(ok, "D4 首次修正：text 更新 / original_text 备份 / is_edited=true",
         d if not ok else None)
    return ok


def scenario_admin_patch_original_text_preserved(ctx: dict) -> bool:
    """第二次修正：original_text 保留第一次的原始内容"""
    tr = _create_transcript(ctx, text="最初内容")
    tid = tr["transcript_id"]
    requests.patch(f"{BASE_URL}/api/admin/transcripts/{tid}",
                   json={"text": "第一次修正"}, headers=ADMIN_HEADERS).raise_for_status()
    r = requests.patch(f"{BASE_URL}/api/admin/transcripts/{tid}",
                       json={"text": "第二次修正"}, headers=ADMIN_HEADERS)
    d = r.json()
    ok = (r.status_code == 200
          and d["text"] == "第二次修正"
          and d["original_text"] == "最初内容")
    _log(ok, "D5 二次修正：original_text 保留最初内容", d if not ok else None)
    return ok


def scenario_admin_patch_visible_to_user(ctx: dict) -> bool:
    tr = _create_transcript(ctx, text="修正前")
    requests.patch(f"{BASE_URL}/api/admin/transcripts/{tr['transcript_id']}",
                   json={"text": "修正后"}, headers=ADMIN_HEADERS).raise_for_status()
    r = requests.get(f"{BASE_URL}/api/sessions/{ctx['session_id']}/transcripts",
                     headers=_auth(ctx["leader_token"]))
    items = r.json()
    target = next((i for i in items if i["transcript_id"] == tr["transcript_id"]), None)
    ok = target is not None and target["text"] == "修正后"
    _log(ok, "D6 修正后用户端可见修正内容", target if not ok else None)
    return ok


# ═══════════════════════════════════════════════════════════════════════════
# E. Admin DELETE 单条
# ═══════════════════════════════════════════════════════════════════════════

def scenario_admin_delete_unauth(ctx: dict) -> bool:
    tr = _create_transcript(ctx)
    r = requests.delete(f"{BASE_URL}/api/admin/transcripts/{tr['transcript_id']}")
    ok = _log(r.status_code in (401, 403), "E1 无 admin token DELETE → 401/403", r.text)
    return ok


def scenario_admin_delete_not_found(ctx: dict) -> bool:
    r = requests.delete(f"{BASE_URL}/api/admin/transcripts/tr_nonexist_999",
                        headers=ADMIN_HEADERS)
    ok = _log(r.status_code == 404, "E2 不存在的 transcript → 404", r.text)
    return ok


def scenario_admin_delete_success(ctx: dict) -> bool:
    tr = _create_transcript(ctx)
    r = requests.delete(f"{BASE_URL}/api/admin/transcripts/{tr['transcript_id']}",
                        headers=ADMIN_HEADERS)
    ok = _log(r.status_code == 204, "E3 正常删除 → 204", r.text)
    return ok


def scenario_admin_delete_idempotent(ctx: dict) -> bool:
    tr = _create_transcript(ctx)
    requests.delete(f"{BASE_URL}/api/admin/transcripts/{tr['transcript_id']}",
                    headers=ADMIN_HEADERS).raise_for_status()
    r = requests.delete(f"{BASE_URL}/api/admin/transcripts/{tr['transcript_id']}",
                        headers=ADMIN_HEADERS)
    ok = _log(r.status_code == 404, "E4 重复删除 → 404", r.text)
    return ok


def scenario_admin_delete_invisible_to_user(ctx: dict) -> bool:
    tr = _create_transcript(ctx)
    tid = tr["transcript_id"]
    requests.delete(f"{BASE_URL}/api/admin/transcripts/{tid}",
                    headers=ADMIN_HEADERS).raise_for_status()
    r = requests.get(f"{BASE_URL}/api/sessions/{ctx['session_id']}/transcripts",
                     headers=_auth(ctx["leader_token"]))
    items = r.json()
    ok = not any(i["transcript_id"] == tid for i in items)
    _log(ok, "E5 删除后用户端不可见", None)
    return ok


# ═══════════════════════════════════════════════════════════════════════════
# F. Admin 批量删除
# ═══════════════════════════════════════════════════════════════════════════

def scenario_admin_batch_delete_unauth(ctx: dict) -> bool:
    r = requests.post(f"{BASE_URL}/api/admin/transcripts/batch-delete",
                      json={"ids": ["tr_x"]})
    ok = _log(r.status_code in (401, 403), "F1 无 admin token 批量删除 → 401/403", r.text)
    return ok


def scenario_admin_batch_delete_empty_ids(ctx: dict) -> bool:
    r = requests.post(f"{BASE_URL}/api/admin/transcripts/batch-delete",
                      json={"ids": []}, headers=ADMIN_HEADERS)
    ok = _log(r.status_code in (400, 422), "F2 ids 为空 → 400/422", r.text)
    return ok


def scenario_admin_batch_delete_over_100(ctx: dict) -> bool:
    ids = [f"tr_{i}" for i in range(101)]
    r = requests.post(f"{BASE_URL}/api/admin/transcripts/batch-delete",
                      json={"ids": ids}, headers=ADMIN_HEADERS)
    ok = _log(r.status_code in (400, 422), "F3 ids 超 100 → 400/422", r.text)
    return ok


def scenario_admin_batch_delete_success(ctx: dict) -> bool:
    tr1 = _create_transcript(ctx)
    tr2 = _create_transcript(ctx)
    tr3 = _create_transcript(ctx)
    r = requests.post(f"{BASE_URL}/api/admin/transcripts/batch-delete",
                      json={"ids": [tr1["transcript_id"], tr2["transcript_id"], tr3["transcript_id"]]},
                      headers=ADMIN_HEADERS)
    ok = r.status_code == 200 and r.json()["deleted"] == 3
    _log(ok, "F4 批量删除 3 条 → deleted=3", r.json() if not ok else None)
    return ok


def scenario_admin_batch_delete_partial_not_found(ctx: dict) -> bool:
    tr = _create_transcript(ctx)
    r = requests.post(f"{BASE_URL}/api/admin/transcripts/batch-delete",
                      json={"ids": [tr["transcript_id"], "tr_nonexist_999"]},
                      headers=ADMIN_HEADERS)
    ok = r.status_code == 200 and r.json()["deleted"] == 1
    _log(ok, "F5 混合有效+无效 ID → deleted=1", r.json() if not ok else None)
    return ok


def scenario_admin_batch_delete_all_not_found(ctx: dict) -> bool:
    r = requests.post(f"{BASE_URL}/api/admin/transcripts/batch-delete",
                      json={"ids": ["tr_nonexist_a", "tr_nonexist_b"]},
                      headers=ADMIN_HEADERS)
    ok = r.status_code == 200 and r.json()["deleted"] == 0
    _log(ok, "F6 全部 ID 不存在 → deleted=0", r.json() if not ok else None)
    return ok


def scenario_admin_batch_delete_count_check(ctx: dict) -> bool:
    # 批量删除后列表数量减少
    before = requests.get(f"{BASE_URL}/api/admin/transcripts/",
                          params={"session_id": ctx["session_id"]},
                          headers=ADMIN_HEADERS).json()["meta"]["total"]
    tr1 = _create_transcript(ctx)
    tr2 = _create_transcript(ctx)
    requests.post(f"{BASE_URL}/api/admin/transcripts/batch-delete",
                  json={"ids": [tr1["transcript_id"], tr2["transcript_id"]]},
                  headers=ADMIN_HEADERS).raise_for_status()
    after = requests.get(f"{BASE_URL}/api/admin/transcripts/",
                         params={"session_id": ctx["session_id"]},
                         headers=ADMIN_HEADERS).json()["meta"]["total"]
    ok = after == before
    _log(ok, "F7 批量删除后列表数量正确减少", f"before={before} after={after}" if not ok else None)
    return ok


# ═══════════════════════════════════════════════════════════════════════════
# run_all
# ═══════════════════════════════════════════════════════════════════════════

def run_all():
    print(f"\n{'='*60}")
    print(f"  Transcript Flows Tests  [RUN_ID={RUN_ID}]")
    print(f"{'='*60}\n")

    ctx = _setup()
    results: list[bool] = []

    print("── A. 用户端 GET transcripts ──")
    results.append(scenario_user_get_transcripts_unauth(ctx))
    results.append(scenario_user_get_transcripts_not_member(ctx))
    results.append(scenario_user_get_transcripts_not_found(ctx))
    results.append(scenario_user_get_transcripts_empty(ctx))
    results.append(scenario_user_get_transcripts_with_data(ctx))
    results.append(scenario_user_get_transcripts_fields(ctx))
    results.append(scenario_user_get_transcripts_order_asc(ctx))

    print("\n── B. Admin 创建 transcript ──")
    results.append(scenario_admin_create_unauth(ctx))
    results.append(scenario_admin_create_invalid_session(ctx))
    results.append(scenario_admin_create_invalid_group(ctx))
    results.append(scenario_admin_create_missing_fields(ctx))
    results.append(scenario_admin_create_success(ctx))

    print("\n── C. Admin 列表 ──")
    results.append(scenario_admin_list_unauth(ctx))
    results.append(scenario_admin_list_basic(ctx))
    results.append(scenario_admin_list_filter_session(ctx))
    results.append(scenario_admin_list_filter_group(ctx))
    results.append(scenario_admin_list_filter_speaker_user(ctx))
    results.append(scenario_admin_list_filter_date_range(ctx))
    results.append(scenario_admin_list_pagination(ctx))
    results.append(scenario_admin_list_page_size_over_limit(ctx))
    results.append(scenario_admin_list_order_asc(ctx))

    print("\n── D. Admin PATCH 修正文本 ──")
    results.append(scenario_admin_patch_unauth(ctx))
    results.append(scenario_admin_patch_not_found(ctx))
    results.append(scenario_admin_patch_missing_text(ctx))
    results.append(scenario_admin_patch_success(ctx))
    results.append(scenario_admin_patch_original_text_preserved(ctx))
    results.append(scenario_admin_patch_visible_to_user(ctx))

    print("\n── E. Admin DELETE 单条 ──")
    results.append(scenario_admin_delete_unauth(ctx))
    results.append(scenario_admin_delete_not_found(ctx))
    results.append(scenario_admin_delete_success(ctx))
    results.append(scenario_admin_delete_idempotent(ctx))
    results.append(scenario_admin_delete_invisible_to_user(ctx))

    print("\n── F. Admin 批量删除 ──")
    results.append(scenario_admin_batch_delete_unauth(ctx))
    results.append(scenario_admin_batch_delete_empty_ids(ctx))
    results.append(scenario_admin_batch_delete_over_100(ctx))
    results.append(scenario_admin_batch_delete_success(ctx))
    results.append(scenario_admin_batch_delete_partial_not_found(ctx))
    results.append(scenario_admin_batch_delete_all_not_found(ctx))
    results.append(scenario_admin_batch_delete_count_check(ctx))

    total = len(results)
    passed = sum(results)
    print(f"\n{'='*60}")
    print(f"  结果：{passed}/{total} 通过")
    print(f"{'='*60}\n")
    if passed < total:
        raise SystemExit(1)


if __name__ == "__main__":
    run_all()
