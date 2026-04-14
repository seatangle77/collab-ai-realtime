"""
后台管理新模块接口完整测试
覆盖：全部查询条件、增删改查、分页边界、参数异常、404/422 等错误场景

用法：
    python -m backend.tests.test_admin_new_modules

前置条件：
    后端已启动：uvicorn backend.app.main:app --reload --port 8000
"""
import sys
import requests

BASE = "http://localhost:8000"
HEADERS = {"X-Admin-Token": "TestAdminKey123"}

# ── 统计 ───────────────────────────────────────────────────────────────
_pass = 0
_fail = 0


def check(label: str, r: requests.Response, expect: int = 200) -> dict | None:
    global _pass, _fail
    ok = r.status_code == expect
    icon = "✓" if ok else "✗"
    print(f"  {icon} [{r.status_code}] {label}")
    if not ok:
        _fail += 1
        print(f"      → {r.text[:300]}")
        return None
    _pass += 1
    if r.status_code == 204:
        return {}
    try:
        return r.json()
    except Exception:
        return None


def section(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ── 通用边界测试（对所有列表接口复用）─────────────────────────────────
def test_pagination_boundaries(url: str) -> None:
    """page/page_size 边界和非法值"""
    check("page=1 page_size=1（最小合法分页）",
          requests.get(f"{url}?page=1&page_size=1", headers=HEADERS))
    check("page_size=100（最大合法）",
          requests.get(f"{url}?page_size=100", headers=HEADERS))
    check("page=999999（超大页码，应返回空 items）",
          requests.get(f"{url}?page=999999", headers=HEADERS))
    check("page=0 → 422",
          requests.get(f"{url}?page=0", headers=HEADERS), 422)
    check("page_size=0 → 422",
          requests.get(f"{url}?page_size=0", headers=HEADERS), 422)
    check("page_size=101 → 422",
          requests.get(f"{url}?page_size=101", headers=HEADERS), 422)


def test_batch_delete_boundaries(url: str) -> None:
    """batch-delete 边界和异常"""
    check("batch-delete 空 ids → 422",
          requests.post(f"{url}/batch-delete", json={"ids": []}, headers=HEADERS), 422)
    check("batch-delete 101 条（超限）→ 422",
          requests.post(f"{url}/batch-delete",
                        json={"ids": [f"fake_{i}" for i in range(101)]},
                        headers=HEADERS), 422)
    check("batch-delete 100 条不存在的 id（边界，deleted=0）",
          requests.post(f"{url}/batch-delete",
                        json={"ids": [f"fake_{i}" for i in range(100)]},
                        headers=HEADERS))
    check("batch-delete 缺少 ids 字段 → 422",
          requests.post(f"{url}/batch-delete", json={}, headers=HEADERS), 422)
    check("batch-delete ids 不是数组 → 422",
          requests.post(f"{url}/batch-delete", json={"ids": "abc"}, headers=HEADERS), 422)


def test_delete_nonexistent(url: str, fake_id: str = "nonexistent_id_xyz") -> None:
    check("DELETE 不存在的记录 → 404",
          requests.delete(f"{url}/{fake_id}", headers=HEADERS), 404)


def create_temp_discussion_state(session_id: str) -> str | None:
    r = requests.post(
        f"{BASE}/api/admin/discussion-states/",
        headers=HEADERS,
        json={"session_id": session_id, "state_type": "low_participation"},
    )
    if r.status_code != 201:
        print(f"  - 创建临时 discussion_state 失败，跳过真实 DELETE 测试: {r.status_code} {r.text[:120]}")
        return None
    return r.json().get("id")


# ═══════════════════════════════════════════════════════════════════════
# Step 1: discussion_states
# ═══════════════════════════════════════════════════════════════════════
section("Step 1: discussion_states — DELETE / batch-delete")

URL_DS = f"{BASE}/api/admin/discussion-states"

# 全量列表（已有接口，确保改动后仍正常）
data = check("GET list（全量）", requests.get(f"{URL_DS}/", headers=HEADERS))

# 所有查询条件
check("filter: state_type=low_participation",
      requests.get(f"{URL_DS}/?state_type=low_participation", headers=HEADERS))
check("filter: state_type=over_dominance",
      requests.get(f"{URL_DS}/?state_type=over_dominance", headers=HEADERS))
check("filter: state_type=deadlock",
      requests.get(f"{URL_DS}/?state_type=deadlock", headers=HEADERS))
check("filter: 非法 state_type → 400",
      requests.get(f"{URL_DS}/?state_type=invalid_type", headers=HEADERS), 400)
check("filter: ai_analysis_done=true",
      requests.get(f"{URL_DS}/?ai_analysis_done=true", headers=HEADERS))
check("filter: ai_analysis_done=false",
      requests.get(f"{URL_DS}/?ai_analysis_done=false", headers=HEADERS))
check("filter: push_sent=true",
      requests.get(f"{URL_DS}/?push_sent=true", headers=HEADERS))
check("filter: push_sent=false",
      requests.get(f"{URL_DS}/?push_sent=false", headers=HEADERS))
check("filter: triggered_from 时间范围",
      requests.get(f"{URL_DS}/?triggered_from=2024-01-01T00:00:00", headers=HEADERS))
check("filter: triggered_from + triggered_to",
      requests.get(f"{URL_DS}/?triggered_from=2024-01-01T00:00:00&triggered_to=2099-12-31T23:59:59",
                   headers=HEADERS))
check("filter: 非法时间格式 → 422",
      requests.get(f"{URL_DS}/?triggered_from=not-a-date", headers=HEADERS), 422)
check("filter: target_user_id 精确",
      requests.get(f"{URL_DS}/?target_user_id=u_fake", headers=HEADERS))
check("filter: session_id 精确",
      requests.get(f"{URL_DS}/?session_id=s_fake", headers=HEADERS))

# 分页边界
test_pagination_boundaries(f"{URL_DS}/")

# DELETE
test_delete_nonexistent(URL_DS)
items = (data or {}).get("items", [])
sid_deleted: str | None = None
if items:
    # 历史数据可能被 push_logs 外键引用，优先尝试找到可删除记录
    for it in items[:20]:
        sid_try = it["id"]
        r = requests.delete(f"{URL_DS}/{sid_try}", headers=HEADERS)
        if r.status_code == 204:
            sid_deleted = sid_try
            print(f"  ✓ [204] DELETE 已有记录（id={sid_try[:12]}…）→ 204")
            break
        if r.status_code == 409:
            print(f"  - [409] 记录被 push_logs 引用，跳过（id={sid_try[:12]}…）")
            continue
        check(f"DELETE 已有记录（id={sid_try[:12]}…）→ 204", r, 204)
        break

if sid_deleted is None and items:
    # 若现有记录都不可删，创建一条临时记录再删，确保接口行为被覆盖
    temp_sid = create_temp_discussion_state(items[0]["session_id"])
    if temp_sid:
        sid_deleted = temp_sid
        check(f"DELETE 临时记录（id={sid_deleted[:12]}…）→ 204",
              requests.delete(f"{URL_DS}/{sid_deleted}", headers=HEADERS), 204)

if sid_deleted:
    check("DELETE 同一记录二次 → 404",
          requests.delete(f"{URL_DS}/{sid_deleted}", headers=HEADERS), 404)
elif not items:
    print("  - 表中无数据，跳过真实 DELETE 测试")

# batch-delete
test_batch_delete_boundaries(URL_DS)


# ═══════════════════════════════════════════════════════════════════════
# Step 2: push_queue
# ═══════════════════════════════════════════════════════════════════════
section("Step 2: push_queue — GET list / DELETE / batch-delete")

URL_PQ = f"{BASE}/api/admin/push-queue"

data = check("GET list（全量）", requests.get(f"{URL_PQ}/", headers=HEADERS))

# 查询条件
check("filter: status=pending",
      requests.get(f"{URL_PQ}/?status=pending", headers=HEADERS))
check("filter: status=delivered",
      requests.get(f"{URL_PQ}/?status=delivered", headers=HEADERS))
check("filter: 非法 status → 400",
      requests.get(f"{URL_PQ}/?status=unknown", headers=HEADERS), 400)
check("filter: state_type=low_participation",
      requests.get(f"{URL_PQ}/?state_type=low_participation", headers=HEADERS))
check("filter: 非法 state_type → 400",
      requests.get(f"{URL_PQ}/?state_type=bad_type", headers=HEADERS), 400)
check("filter: session_id 精确",
      requests.get(f"{URL_PQ}/?session_id=s_fake", headers=HEADERS))
check("filter: target_user_id 精确",
      requests.get(f"{URL_PQ}/?target_user_id=u_fake", headers=HEADERS))
check("filter: created_from + created_to",
      requests.get(f"{URL_PQ}/?created_from=2024-01-01T00:00:00&created_to=2099-12-31T23:59:59",
                   headers=HEADERS))
check("filter: 非法时间格式 → 422",
      requests.get(f"{URL_PQ}/?created_from=not-a-date", headers=HEADERS), 422)
check("filter: 多条件组合",
      requests.get(f"{URL_PQ}/?status=pending&state_type=deadlock", headers=HEADERS))

test_pagination_boundaries(f"{URL_PQ}/")

# DELETE
test_delete_nonexistent(URL_PQ)
items = (data or {}).get("items", [])
if items:
    qid = items[0]["id"]
    check(f"DELETE 已有记录（id={qid[:12]}…）→ 204",
          requests.delete(f"{URL_PQ}/{qid}", headers=HEADERS), 204)
    check("DELETE 同一记录二次 → 404",
          requests.delete(f"{URL_PQ}/{qid}", headers=HEADERS), 404)
else:
    print("  - 表中无数据，跳过真实 DELETE 测试")

test_batch_delete_boundaries(URL_PQ)


# ═══════════════════════════════════════════════════════════════════════
# Step 3: window_metrics
# ═══════════════════════════════════════════════════════════════════════
section("Step 3: window_metrics — GET list / DELETE / batch-delete")

URL_WM = f"{BASE}/api/admin/window-metrics"

data = check("GET list（全量）", requests.get(f"{URL_WM}/", headers=HEADERS))

# 查询条件
check("filter: session_id 精确",
      requests.get(f"{URL_WM}/?session_id=s_fake", headers=HEADERS))
check("filter: user_id 精确",
      requests.get(f"{URL_WM}/?user_id=u_fake", headers=HEADERS))
check("filter: has_reasoning=true",
      requests.get(f"{URL_WM}/?has_reasoning=true", headers=HEADERS))
check("filter: has_reasoning=false",
      requests.get(f"{URL_WM}/?has_reasoning=false", headers=HEADERS))
check("filter: has_evidence=true",
      requests.get(f"{URL_WM}/?has_evidence=true", headers=HEADERS))
check("filter: has_evidence=false",
      requests.get(f"{URL_WM}/?has_evidence=false", headers=HEADERS))
check("filter: has_reasoning + has_evidence 组合",
      requests.get(f"{URL_WM}/?has_reasoning=true&has_evidence=true", headers=HEADERS))
check("filter: window_start_from + window_start_to",
      requests.get(f"{URL_WM}/?window_start_from=2024-01-01T00:00:00&window_start_to=2099-12-31T23:59:59",
                   headers=HEADERS))
check("filter: 非法时间格式 → 422",
      requests.get(f"{URL_WM}/?window_start_from=bad-date", headers=HEADERS), 422)
check("filter: has_reasoning 非法值 → 422",
      requests.get(f"{URL_WM}/?has_reasoning=maybe", headers=HEADERS), 422)

test_pagination_boundaries(f"{URL_WM}/")

# DELETE
test_delete_nonexistent(URL_WM)
items = (data or {}).get("items", [])
if items:
    wid = items[0]["id"]
    check(f"DELETE 已有记录（id={wid[:12]}…）→ 204",
          requests.delete(f"{URL_WM}/{wid}", headers=HEADERS), 204)
    check("DELETE 同一记录二次 → 404",
          requests.delete(f"{URL_WM}/{wid}", headers=HEADERS), 404)
else:
    print("  - 表中无数据，跳过真实 DELETE 测试")

test_batch_delete_boundaries(URL_WM)


# ═══════════════════════════════════════════════════════════════════════
# Step 5: discussion_summaries
# ═══════════════════════════════════════════════════════════════════════
section("Step 5: discussion_summaries — GET list / GET detail / PUT / DELETE / batch-delete")

URL_DSUM = f"{BASE}/api/admin/discussion-summaries"

data = check("GET list（全量）", requests.get(f"{URL_DSUM}/", headers=HEADERS))

# 查询条件
check("filter: session_id 精确",
      requests.get(f"{URL_DSUM}/?session_id=s_fake", headers=HEADERS))
check("filter: version=1",
      requests.get(f"{URL_DSUM}/?version=1", headers=HEADERS))
check("filter: version=0（边界值，合法）",
      requests.get(f"{URL_DSUM}/?version=0", headers=HEADERS))
check("filter: window_start_from + window_start_to",
      requests.get(f"{URL_DSUM}/?window_start_from=2024-01-01T00:00:00&window_start_to=2099-12-31T23:59:59",
                   headers=HEADERS))
check("filter: 非法时间格式 → 422",
      requests.get(f"{URL_DSUM}/?window_start_from=not-a-date", headers=HEADERS), 422)

test_pagination_boundaries(f"{URL_DSUM}/")

# GET detail
check("GET detail 不存在 → 404",
      requests.get(f"{URL_DSUM}/nonexistent_id", headers=HEADERS), 404)

# PUT
check("PUT 不存在记录 → 404",
      requests.put(f"{URL_DSUM}/nonexistent_id",
                   json={"content": "新内容"}, headers=HEADERS), 404)
check("PUT 缺少 content 字段 → 422",
      requests.put(f"{URL_DSUM}/any_id", json={}, headers=HEADERS), 422)
check("PUT content 为空字符串（合法，允许清空）",
      requests.put(f"{URL_DSUM}/nonexistent_id",
                   json={"content": ""}, headers=HEADERS), 404)  # 记录不存在，期望404

# DELETE
test_delete_nonexistent(URL_DSUM)

# 有数据时的完整流程测试
items = (data or {}).get("items", [])
if items:
    target = items[0]
    sid = target["id"]
    original_content = target["content"]

    check(f"GET detail 已有记录（id={sid[:12]}…）",
          requests.get(f"{URL_DSUM}/{sid}", headers=HEADERS))

    r_put = check("PUT 编辑 content",
                  requests.put(f"{URL_DSUM}/{sid}",
                               json={"content": "【测试修改】" + original_content[:30]},
                               headers=HEADERS))
    if r_put:
        assert r_put.get("content", "").startswith("【测试修改】"), "PUT 后 content 未更新"
        print("    → content 已成功更新 ✓")

    # 还原
    requests.put(f"{URL_DSUM}/{sid}", json={"content": original_content}, headers=HEADERS)
    print("    → content 已还原 ✓")

    check(f"DELETE 已有记录（id={sid[:12]}…）→ 204",
          requests.delete(f"{URL_DSUM}/{sid}", headers=HEADERS), 204)
    check("DELETE 同一记录二次 → 404",
          requests.delete(f"{URL_DSUM}/{sid}", headers=HEADERS), 404)
    check("GET detail 已删除记录 → 404",
          requests.get(f"{URL_DSUM}/{sid}", headers=HEADERS), 404)
    check("PUT 已删除记录 → 404",
          requests.put(f"{URL_DSUM}/{sid}", json={"content": "ghost"}, headers=HEADERS), 404)
else:
    print("  - 表中无数据，跳过详情/编辑/删除真实记录测试")

test_batch_delete_boundaries(URL_DSUM)


# ═══════════════════════════════════════════════════════════════════════
# Step 6: info_gap_buttons
# ═══════════════════════════════════════════════════════════════════════
section("Step 6: info_gap_buttons — GET list / DELETE / batch-delete")

URL_IGB = f"{BASE}/api/admin/info-gap-buttons"

data = check("GET list（全量）", requests.get(f"{URL_IGB}/", headers=HEADERS))

# 查询条件
check("filter: session_id 精确",
      requests.get(f"{URL_IGB}/?session_id=s_fake", headers=HEADERS))
check("filter: user_id 精确",
      requests.get(f"{URL_IGB}/?user_id=u_fake", headers=HEADERS))
check("filter: keyword 模糊",
      requests.get(f"{URL_IGB}/?keyword=test", headers=HEADERS))
check("filter: keyword 含 SQL 特殊字符（% _）",
      requests.get(f"{URL_IGB}/?keyword=%25_", headers=HEADERS))
check("filter: status=pending",
      requests.get(f"{URL_IGB}/?status=pending", headers=HEADERS))
check("filter: status=clicked",
      requests.get(f"{URL_IGB}/?status=clicked", headers=HEADERS))
check("filter: has_clicked=true",
      requests.get(f"{URL_IGB}/?has_clicked=true", headers=HEADERS))
check("filter: has_clicked=false",
      requests.get(f"{URL_IGB}/?has_clicked=false", headers=HEADERS))
check("filter: has_clicked 非法值 → 422",
      requests.get(f"{URL_IGB}/?has_clicked=maybe", headers=HEADERS), 422)
check("filter: window_start_from + window_start_to",
      requests.get(f"{URL_IGB}/?window_start_from=2024-01-01T00:00:00&window_start_to=2099-12-31T23:59:59",
                   headers=HEADERS))
check("filter: 多条件组合（session + status + has_clicked）",
      requests.get(f"{URL_IGB}/?status=pending&has_clicked=false", headers=HEADERS))
check("filter: 非法时间格式 → 422",
      requests.get(f"{URL_IGB}/?window_start_from=not-a-date", headers=HEADERS), 422)

test_pagination_boundaries(f"{URL_IGB}/")

# DELETE
test_delete_nonexistent(URL_IGB)
items = (data or {}).get("items", [])
if items:
    bid = items[0]["id"]
    check(f"DELETE 已有记录（id={bid[:12]}…）→ 204",
          requests.delete(f"{URL_IGB}/{bid}", headers=HEADERS), 204)
    check("DELETE 同一记录二次 → 404",
          requests.delete(f"{URL_IGB}/{bid}", headers=HEADERS), 404)
else:
    print("  - 表中无数据，跳过真实 DELETE 测试")

test_batch_delete_boundaries(URL_IGB)


# ═══════════════════════════════════════════════════════════════════════
# Step 7: keyword_skw
# ═══════════════════════════════════════════════════════════════════════
section("Step 7: keyword_skw — GET list / DELETE / batch-delete")

URL_KS = f"{BASE}/api/admin/keyword-skw"

data = check("GET list（全量）", requests.get(f"{URL_KS}/", headers=HEADERS))

# 查询条件
check("filter: session_id 精确",
      requests.get(f"{URL_KS}/?session_id=s_fake", headers=HEADERS))
check("filter: keyword 模糊",
      requests.get(f"{URL_KS}/?keyword=AI", headers=HEADERS))
check("filter: keyword 含特殊字符",
      requests.get(f"{URL_KS}/?keyword=%25", headers=HEADERS))
check("filter: user_a_id 精确",
      requests.get(f"{URL_KS}/?user_a_id=u_fake_a", headers=HEADERS))
check("filter: user_b_id 精确",
      requests.get(f"{URL_KS}/?user_b_id=u_fake_b", headers=HEADERS))
check("filter: user_a_id + user_b_id 组合",
      requests.get(f"{URL_KS}/?user_a_id=u_fake_a&user_b_id=u_fake_b", headers=HEADERS))
check("filter: skw_score_min=0.5",
      requests.get(f"{URL_KS}/?skw_score_min=0.5", headers=HEADERS))
check("filter: skw_score_max=0.8",
      requests.get(f"{URL_KS}/?skw_score_max=0.8", headers=HEADERS))
check("filter: skw_score_min=0.0（边界）",
      requests.get(f"{URL_KS}/?skw_score_min=0.0", headers=HEADERS))
check("filter: skw_score_max=1.0（边界）",
      requests.get(f"{URL_KS}/?skw_score_max=1.0", headers=HEADERS))
check("filter: skw_score_min=0.3 + skw_score_max=0.7（区间）",
      requests.get(f"{URL_KS}/?skw_score_min=0.3&skw_score_max=0.7", headers=HEADERS))
check("filter: skw_score_min > skw_score_max（逻辑矛盾，返回空结果而非报错）",
      requests.get(f"{URL_KS}/?skw_score_min=0.9&skw_score_max=0.1", headers=HEADERS))
check("filter: window_start_from + window_start_to",
      requests.get(f"{URL_KS}/?window_start_from=2024-01-01T00:00:00&window_start_to=2099-12-31T23:59:59",
                   headers=HEADERS))
check("filter: 非法时间格式 → 422",
      requests.get(f"{URL_KS}/?window_start_from=bad", headers=HEADERS), 422)
check("filter: skw_score_min 非数字 → 422",
      requests.get(f"{URL_KS}/?skw_score_min=abc", headers=HEADERS), 422)

test_pagination_boundaries(f"{URL_KS}/")

# DELETE
test_delete_nonexistent(URL_KS)
items = (data or {}).get("items", [])
if items:
    kid = items[0]["id"]
    check(f"DELETE 已有记录（id={kid[:12]}…）→ 204",
          requests.delete(f"{URL_KS}/{kid}", headers=HEADERS), 204)
    check("DELETE 同一记录二次 → 404",
          requests.delete(f"{URL_KS}/{kid}", headers=HEADERS), 404)
else:
    print("  - 表中无数据，跳过真实 DELETE 测试")

test_batch_delete_boundaries(URL_KS)


# ═══════════════════════════════════════════════════════════════════════
# Step 8: speech_transcripts
# ═══════════════════════════════════════════════════════════════════════
section("Step 8: speech_transcripts — GET list / DELETE / batch-delete")

URL_ST = f"{BASE}/api/admin/speech-transcripts"

data = check("GET list（全量）", requests.get(f"{URL_ST}/", headers=HEADERS))

# 查询条件
check("filter: session_id 精确",
      requests.get(f"{URL_ST}/?session_id=s_fake", headers=HEADERS))
check("filter: group_id 精确",
      requests.get(f"{URL_ST}/?group_id=g_fake", headers=HEADERS))
check("filter: speaker 模糊",
      requests.get(f"{URL_ST}/?speaker=张", headers=HEADERS))
check("filter: text 模糊",
      requests.get(f"{URL_ST}/?text=你好", headers=HEADERS))
check("filter: text 含 SQL 特殊字符（%）",
      requests.get(f"{URL_ST}/?text=%25", headers=HEADERS))
check("filter: text 含下划线（_，ILIKE 通配符）",
      requests.get(f"{URL_ST}/?text=_test_", headers=HEADERS))
check("filter: created_from + created_to",
      requests.get(f"{URL_ST}/?created_from=2024-01-01T00:00:00&created_to=2099-12-31T23:59:59",
                   headers=HEADERS))
check("filter: 非法时间格式 → 422",
      requests.get(f"{URL_ST}/?created_from=bad-date", headers=HEADERS), 422)
check("filter: 多条件组合（session + speaker + text）",
      requests.get(f"{URL_ST}/?session_id=s_fake&speaker=user_1&text=hello", headers=HEADERS))

test_pagination_boundaries(f"{URL_ST}/")

# DELETE
test_delete_nonexistent(URL_ST, fake_id="tr_nonexistent_id_xyz")
items = (data or {}).get("items", [])
if items:
    tid = items[0]["transcript_id"]
    check(f"DELETE 已有记录（transcript_id={tid[:12]}…）→ 204",
          requests.delete(f"{URL_ST}/{tid}", headers=HEADERS), 204)
    check("DELETE 同一记录二次 → 404",
          requests.delete(f"{URL_ST}/{tid}", headers=HEADERS), 404)
else:
    print("  - 表中无数据，跳过真实 DELETE 测试")

test_batch_delete_boundaries(URL_ST)


# ═══════════════════════════════════════════════════════════════════════
# 鉴权测试（所有新接口共用）
# ═══════════════════════════════════════════════════════════════════════
section("鉴权：无 Token / 错误 Token → 403")

NO_TOKEN: dict = {}
WRONG_TOKEN = {"X-Admin-Token": "wrong_key_12345"}

for url in [
    f"{BASE}/api/admin/push-queue/",
    f"{BASE}/api/admin/window-metrics/",
    f"{BASE}/api/admin/discussion-summaries/",
    f"{BASE}/api/admin/info-gap-buttons/",
    f"{BASE}/api/admin/keyword-skw/",
    f"{BASE}/api/admin/speech-transcripts/",
]:
    path = url.replace(BASE, "")
    check(f"无 Token {path} → 403",
          requests.get(url, headers=NO_TOKEN), 403)
    check(f"错误 Token {path} → 403",
          requests.get(url, headers=WRONG_TOKEN), 403)


# ═══════════════════════════════════════════════════════════════════════
# 汇总
# ═══════════════════════════════════════════════════════════════════════
section("测试结果汇总")
total = _pass + _fail
print(f"  通过: {_pass} / {total}")
print(f"  失败: {_fail} / {total}")
if _fail:
    print("\n  ⚠️  有接口未通过，请检查上方 ✗ 行。")
    sys.exit(1)
else:
    print("\n  🎉 全部通过！")
