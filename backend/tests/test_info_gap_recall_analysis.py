"""
关键词召回分析接口测试
覆盖：稳定 seed 数据、查询过滤、分页边界、DELETE / batch-delete、参数异常、认证鉴权

用法（在 backend/ 目录下）：
    python -m tests.test_info_gap_recall_analysis

前置条件：
    后端已启动：uvicorn app.main:app --reload --port 8000
"""
import asyncio
import atexit
import sys
import uuid
from pathlib import Path

import requests
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.settings import settings

BASE = "http://localhost:8000"
HEADERS = {"X-Admin-Token": "TestAdminKey123"}
URL = f"{BASE}/api/admin/info-gap-recall-analysis"
SESSION_PREFIX = f"sess_test_kra_{uuid.uuid4().hex[:8]}"
SEEDED_IDS: list[str] = []

_pass = 0
_fail = 0


def check(label: str, r: requests.Response, expect: int = 200) -> dict | None:
    global _pass, _fail
    ok = r.status_code == expect
    icon = "✓" if ok else "✗"
    print(f"  {icon} [{r.status_code}] {label}")
    if not ok:
        _fail += 1
        print(f"      → {r.text[:400]}")
        return None
    _pass += 1
    if r.status_code == 204:
        return {}
    try:
        return r.json()
    except Exception:
        return None


def section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def require_db() -> None:
    try:
        settings.sqlalchemy_database_url()
    except RuntimeError as exc:
        print(f"数据库配置缺失，无法执行稳定 seed 测试: {exc}")
        sys.exit(1)


async def exec_sql(sql: str, params: dict | None = None) -> None:
    engine = create_async_engine(
        settings.sqlalchemy_database_url(),
        connect_args={"ssl": False},
        pool_pre_ping=True,
    )
    try:
        async with engine.begin() as conn:
            await conn.execute(text(sql), params or {})
    finally:
        await engine.dispose()


def cleanup_seed_rows() -> None:
    if not SEEDED_IDS:
        return
    try:
        asyncio.run(exec_sql("DELETE FROM info_gap_recall_analysis WHERE id = ANY(:ids)", {"ids": SEEDED_IDS}))
    except Exception as exc:
        print(f"[cleanup] 删除测试数据失败: {exc}")


def seed_rows() -> None:
    rows = [
        {
            "id": f"kra_test_{uuid.uuid4().hex[:8]}",
            "session_id": SESSION_PREFIX,
            "window_start": "2025-01-01 11:00:00",
            "keyword": "机器学习",
            "needs_prompt": "true",
            "target_user_id": "'u_kra_true'",
            "llm_reason": "'该成员明确表示听不懂机器学习概念'",
        },
        {
            "id": f"kra_test_{uuid.uuid4().hex[:8]}",
            "session_id": SESSION_PREFIX,
            "window_start": "2025-01-01 11:01:00",
            "keyword": "深度 学习",
            "needs_prompt": "false",
            "target_user_id": "'u_kra_false'",
            "llm_reason": "'当前无需额外提示'",
        },
        {
            "id": f"kra_test_{uuid.uuid4().hex[:8]}",
            "session_id": SESSION_PREFIX,
            "window_start": "2025-01-01 11:02:00",
            "keyword": "关键词_特殊%字符",
            "needs_prompt": "true",
            "target_user_id": "NULL",
            "llm_reason": "NULL",
        },
        {
            "id": f"kra_test_{uuid.uuid4().hex[:8]}",
            "session_id": SESSION_PREFIX,
            "window_start": "2025-01-01 11:03:00",
            "keyword": "A",
            "needs_prompt": "false",
            "target_user_id": "NULL",
            "llm_reason": "'单字符关键词也应正常返回'",
        },
        {
            "id": f"kra_test_{uuid.uuid4().hex[:8]}",
            "session_id": SESSION_PREFIX,
            "window_start": "2025-01-01 11:04:00",
            "keyword": "MVP 方案",
            "needs_prompt": "true",
            "target_user_id": "'u_kra_mvp'",
            "llm_reason": "'用户表示对 MVP 缩写不理解'",
        },
    ]
    SEEDED_IDS.extend(row["id"] for row in rows)
    values = ",\n".join(
        "('{id}', '{session_id}', '{window_start}', '{keyword}', "
        "{needs_prompt}, {target_user_id}, {llm_reason}, NOW())".format(**row)
        for row in rows
    )
    sql = f"""
    INSERT INTO info_gap_recall_analysis
      (id, session_id, window_start, keyword, needs_prompt, target_user_id, llm_reason, created_at)
    VALUES
      {values}
    ON CONFLICT (id) DO NOTHING;
    """
    asyncio.run(exec_sql(sql))


def assert_items_all(data: dict, predicate, label: str) -> None:
    items = data.get("items", [])
    assert all(predicate(item) for item in items), label


require_db()
atexit.register(cleanup_seed_rows)
cleanup_seed_rows()
seed_rows()

section("1. 认证鉴权")

check("无 Token → 403", requests.get(f"{URL}/"), 403)
check("错误 Token → 403", requests.get(f"{URL}/", headers={"X-Admin-Token": "wrong"}), 403)
check("正确 Token → 200", requests.get(f"{URL}/", headers=HEADERS), 200)

section("2. 基本列表查询")

data = check("GET 全量列表", requests.get(f"{URL}/?session_id={SESSION_PREFIX}", headers=HEADERS))
if data:
    assert data["meta"]["total"] >= 5, "seed 数据数量异常"
    assert len(data["items"]) >= 5, "seed 数据未查到"
    print(f"      total={data['meta']['total']}, page={data['meta']['page']}, page_size={data['meta']['page_size']}")

check("GET 列表（默认分页）结构正确",
      requests.get(f"{URL}/?session_id={SESSION_PREFIX}&page=1&page_size=20", headers=HEADERS))

section("3. 过滤条件")

data = check("filter: session_id 精确匹配",
             requests.get(f"{URL}/?session_id={SESSION_PREFIX}", headers=HEADERS))
if data:
    assert_items_all(data, lambda item: item["session_id"] == SESSION_PREFIX, "session_id 过滤错误")

for keyword in ["机器学习", "关键词", "MVP", "A", "特殊%字符"]:
    data = check(f"filter: keyword 模糊匹配={keyword}",
                 requests.get(f"{URL}/?session_id={SESSION_PREFIX}&keyword={keyword}", headers=HEADERS))
    if data:
        assert data["items"], f"keyword={keyword} 应命中 seed 数据"

data = check("filter: needs_prompt=true",
             requests.get(f"{URL}/?session_id={SESSION_PREFIX}&needs_prompt=true", headers=HEADERS))
if data:
    assert_items_all(data, lambda item: item["needs_prompt"] is True, "needs_prompt=true 过滤错误")

data = check("filter: needs_prompt=false",
             requests.get(f"{URL}/?session_id={SESSION_PREFIX}&needs_prompt=false", headers=HEADERS))
if data:
    assert_items_all(data, lambda item: item["needs_prompt"] is False, "needs_prompt=false 过滤错误")

check("filter: needs_prompt=invalid → 422",
      requests.get(f"{URL}/?needs_prompt=maybe", headers=HEADERS), 422)

data = check("filter: window_start_from=2025-01-01T11:02:00Z",
             requests.get(f"{URL}/?session_id={SESSION_PREFIX}&window_start_from=2025-01-01T11:02:00Z", headers=HEADERS))
if data:
    assert_items_all(data, lambda item: item["window_start"] >= "2025-01-01T11:02:00", "window_start_from 过滤错误")

data = check("filter: window_start_to=2025-01-01T11:03:00Z",
             requests.get(f"{URL}/?session_id={SESSION_PREFIX}&window_start_to=2025-01-01T11:03:00Z", headers=HEADERS))
if data:
    assert_items_all(data, lambda item: item["window_start"] <= "2025-01-01T11:03:00", "window_start_to 过滤错误")

check("filter: window_start_from 非法格式 → 422",
      requests.get(f"{URL}/?window_start_from=not-a-date", headers=HEADERS), 422)
check("filter: window_start_to 非法格式 → 422",
      requests.get(f"{URL}/?window_start_to=not-a-date", headers=HEADERS), 422)

data = check("filter: session_id + keyword",
             requests.get(f"{URL}/?session_id={SESSION_PREFIX}&keyword=MVP", headers=HEADERS))
if data:
    assert_items_all(data, lambda item: "MVP" in item["keyword"], "session_id + keyword 组合过滤错误")

data = check("filter: needs_prompt + window_start 范围",
             requests.get(
                 f"{URL}/?session_id={SESSION_PREFIX}&needs_prompt=true"
                 "&window_start_from=2025-01-01T11:00:00Z&window_start_to=2025-01-01T11:04:00Z",
                 headers=HEADERS,
             ))
if data:
    assert_items_all(data, lambda item: item["needs_prompt"] is True, "needs_prompt + 时间范围过滤错误")

section("4. 分页边界")

data = check("page=1 page_size=1（最小合法分页）",
             requests.get(f"{URL}/?session_id={SESSION_PREFIX}&page=1&page_size=1", headers=HEADERS))
if data:
    assert len(data["items"]) == 1, "page_size=1 应只返回 1 条"

check("page_size=200（最大合法）",
      requests.get(f"{URL}/?session_id={SESSION_PREFIX}&page_size=200", headers=HEADERS))
data = check("page=999999（超大页码，应返回空 items）",
             requests.get(f"{URL}/?session_id={SESSION_PREFIX}&page=999999", headers=HEADERS))
if data:
    assert data["items"] == [], "超大页码应返回空列表"

check("page=0 → 422", requests.get(f"{URL}/?page=0", headers=HEADERS), 422)
check("page_size=0 → 422", requests.get(f"{URL}/?page_size=0", headers=HEADERS), 422)
check("page_size=201 → 422", requests.get(f"{URL}/?page_size=201", headers=HEADERS), 422)
check("page=-1 → 422", requests.get(f"{URL}/?page=-1", headers=HEADERS), 422)
check("page=abc → 422", requests.get(f"{URL}/?page=abc", headers=HEADERS), 422)

section("5. DELETE 单条")

check("DELETE 不存在的 id → 404",
      requests.delete(f"{URL}/nonexistent_id_xyz", headers=HEADERS), 404)
check("DELETE 路径为空（method not allowed）→ 405",
      requests.delete(f"{URL}/", headers=HEADERS), 405)

delete_id = SEEDED_IDS.pop()
resp = requests.delete(f"{URL}/{delete_id}", headers=HEADERS)
check(f"DELETE 真实存在的记录 id={delete_id[:16]}... → 204", resp, 204)
check("再次 DELETE 同一 id → 404",
      requests.delete(f"{URL}/{delete_id}", headers=HEADERS), 404)

section("6. batch-delete")

check("batch-delete 空 ids → 422",
      requests.post(f"{URL}/batch-delete", json={"ids": []}, headers=HEADERS), 422)
check("batch-delete 101 条（超限）→ 422",
      requests.post(f"{URL}/batch-delete", json={"ids": [f"fake_{i}" for i in range(101)]}, headers=HEADERS), 422)
r_bd = check("batch-delete 100 条不存在 id（边界，deleted=0）",
             requests.post(f"{URL}/batch-delete",
                           json={"ids": [f"fake_{i}" for i in range(100)]},
                           headers=HEADERS))
if r_bd:
    assert r_bd.get("deleted") == 0, f"deleted 应为 0，实际={r_bd.get('deleted')}"
    print(f"      deleted={r_bd['deleted']} ✓")

check("batch-delete 缺少 ids 字段 → 422",
      requests.post(f"{URL}/batch-delete", json={}, headers=HEADERS), 422)
check("batch-delete ids 不是数组 → 422",
      requests.post(f"{URL}/batch-delete", json={"ids": "abc"}, headers=HEADERS), 422)
check("batch-delete ids 含 null → 422",
      requests.post(f"{URL}/batch-delete", json={"ids": [None]}, headers=HEADERS), 422)
check("batch-delete ids 含整数 → 422",
      requests.post(f"{URL}/batch-delete", json={"ids": [1, 2, 3]}, headers=HEADERS), 422)
check("batch-delete body 为空 → 422",
      requests.post(f"{URL}/batch-delete", data="", headers=HEADERS), 422)

batch_ids = SEEDED_IDS[:2]
r_bd2 = check(f"batch-delete {len(batch_ids)} 条真实记录",
              requests.post(f"{URL}/batch-delete", json={"ids": batch_ids}, headers=HEADERS))
if r_bd2:
    assert r_bd2.get("deleted") == len(batch_ids), f"deleted 应为 {len(batch_ids)}，实际={r_bd2.get('deleted')}"
    print(f"      deleted={r_bd2['deleted']} ✓")
    SEEDED_IDS[:] = [row_id for row_id in SEEDED_IDS if row_id not in batch_ids]

section("7. 极端 / 边界参数")

check("session_id 超长字符串（1000 字符）",
      requests.get(f"{URL}/?session_id={'x' * 1000}", headers=HEADERS))
check("keyword 为空字符串（应被忽略，返回全量）",
      requests.get(f"{URL}/?keyword=", headers=HEADERS))
check("keyword SQL 注入尝试",
      requests.get(f"{URL}/?keyword='; DROP TABLE info_gap_recall_analysis; --", headers=HEADERS))
data = check("window_start_from 等于 window_start_to（精确时间点）",
             requests.get(
                 f"{URL}/?session_id={SESSION_PREFIX}"
                 "&window_start_from=2025-01-01T11:03:00Z&window_start_to=2025-01-01T11:03:00Z",
                 headers=HEADERS,
             ))
if data:
    assert len(data["items"]) == 1, "精确时间点应命中 1 条"

data = check("window_start_from > window_start_to（时间倒置，应返回空）",
             requests.get(
                 f"{URL}/?session_id={SESSION_PREFIX}"
                 "&window_start_from=2099-01-01T00:00:00Z&window_start_to=2024-01-01T00:00:00Z",
                 headers=HEADERS,
             ))
if data:
    assert data["items"] == [], "时间倒置应返回空列表"

print(f"\n{'=' * 60}")
print(f"  结果汇总：通过 {_pass}，失败 {_fail}")
print(f"{'=' * 60}\n")

if _fail > 0:
    sys.exit(1)
