"""
窗口关键词接口测试
覆盖：稳定 seed 数据、查询过滤、分页边界、DELETE / batch-delete、参数异常、认证鉴权

用法（在 backend/ 目录下）：
    python -m tests.test_window_metrics_keywords

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
URL = f"{BASE}/api/admin/window-metrics-keywords"
SESSION_PREFIX = f"sess_test_wmk_{uuid.uuid4().hex[:8]}"
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
        asyncio.run(exec_sql("DELETE FROM window_metrics_keywords WHERE id = ANY(:ids)", {"ids": SEEDED_IDS}))
    except Exception as exc:
        print(f"[cleanup] 删除测试数据失败: {exc}")


def seed_rows() -> None:
    rows = [
        {
            "id": f"wmk_test_{uuid.uuid4().hex[:8]}",
            "session_id": SESSION_PREFIX,
            "window_start": "2025-01-01 13:00:00",
            "keyword": "机器学习",
        },
        {
            "id": f"wmk_test_{uuid.uuid4().hex[:8]}",
            "session_id": SESSION_PREFIX,
            "window_start": "2025-01-01 13:01:00",
            "keyword": "MVP 方案",
        },
        {
            "id": f"wmk_test_{uuid.uuid4().hex[:8]}",
            "session_id": SESSION_PREFIX,
            "window_start": "2025-01-01 13:02:00",
            "keyword": "A",
        },
        {
            "id": f"wmk_test_{uuid.uuid4().hex[:8]}",
            "session_id": SESSION_PREFIX,
            "window_start": "2025-01-01 13:03:00",
            "keyword": "关键词_特殊%字符",
        },
        {
            "id": f"wmk_test_{uuid.uuid4().hex[:8]}",
            "session_id": SESSION_PREFIX,
            "window_start": "2025-01-01 13:04:00",
            "keyword": "上下文同步",
        },
    ]
    SEEDED_IDS.extend(row["id"] for row in rows)
    values = ",\n".join(
        "('{id}', '{session_id}', '{window_start}', '{keyword}', NOW())".format(**row)
        for row in rows
    )
    sql = f"""
    INSERT INTO window_metrics_keywords
      (id, session_id, window_start, keyword, created_at)
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
    sample = data["items"][0]
    for field in ["id", "session_id", "window_start", "keyword", "created_at"]:
        assert field in sample, f"缺少字段: {field}"

data = check("GET + session_id 过滤", requests.get(f"{URL}/?session_id={SESSION_PREFIX}", headers=HEADERS))
if data:
    assert_items_all(data, lambda item: item["session_id"] == SESSION_PREFIX, "session_id 过滤错误")

section("3. 过滤条件")

data = check("filter: session_id 精确匹配",
             requests.get(f"{URL}/?session_id={SESSION_PREFIX}", headers=HEADERS))
if data:
    assert_items_all(data, lambda item: item["session_id"] == SESSION_PREFIX, "session_id 精确匹配错误")

for keyword in ["机器学习", "MVP", "A", "关键词", "特殊%字符"]:
    data = check(f"filter: keyword 模糊匹配={keyword}",
                 requests.get(f"{URL}/?session_id={SESSION_PREFIX}&keyword={keyword}", headers=HEADERS))
    if data:
        assert data["items"], f"keyword={keyword} 应命中 seed 数据"

data = check("filter: window_start_from / window_start_to 时间范围",
             requests.get(
                 f"{URL}/?session_id={SESSION_PREFIX}"
                 "&window_start_from=2025-01-01T13:01:00Z&window_start_to=2025-01-01T13:03:00Z",
                 headers=HEADERS,
             ))
if data:
    assert_items_all(
        data,
        lambda item: "2025-01-01T13:01:00" <= item["window_start"] <= "2025-01-01T13:03:00",
        "window_start 范围过滤错误",
    )

data = check("filter: 组合=session_id + keyword + window_start_from",
             requests.get(
                 f"{URL}/?session_id={SESSION_PREFIX}&keyword=关键词&window_start_from=2025-01-01T13:02:00Z",
                 headers=HEADERS,
             ))
if data:
    assert_items_all(data, lambda item: item["session_id"] == SESSION_PREFIX, "组合过滤 session_id 错误")

data = check("filter: window_start_from = window_start_to（精确时间点）",
             requests.get(
                 f"{URL}/?session_id={SESSION_PREFIX}"
                 "&window_start_from=2025-01-01T13:03:00Z&window_start_to=2025-01-01T13:03:00Z",
                 headers=HEADERS,
             ))
if data:
    assert len(data["items"]) == 1, "精确时间点应命中 1 条"

data = check("filter: window_start_from > window_start_to（时间倒置）",
             requests.get(
                 f"{URL}/?session_id={SESSION_PREFIX}"
                 "&window_start_from=2099-01-01T00:00:00Z&window_start_to=2024-01-01T00:00:00Z",
                 headers=HEADERS,
             ))
if data:
    assert data["items"] == [], "时间倒置应返回空列表"

check("filter: window_start_from 非法格式 → 422",
      requests.get(f"{URL}/?window_start_from=not-a-date", headers=HEADERS), 422)

section("4. 边界分页")

data = check("page=1, page_size=1",
             requests.get(f"{URL}/?session_id={SESSION_PREFIX}&page=1&page_size=1", headers=HEADERS))
if data:
    assert len(data["items"]) == 1, "page_size=1 应只返回 1 条"

check("page_size=200（最大合法）",
      requests.get(f"{URL}/?session_id={SESSION_PREFIX}&page_size=200", headers=HEADERS))
data = check("page=999999",
             requests.get(f"{URL}/?session_id={SESSION_PREFIX}&page=999999", headers=HEADERS))
if data:
    assert data["items"] == [], "超大页码应返回空列表"

check("page=0 → 422", requests.get(f"{URL}/?page=0", headers=HEADERS), 422)
check("page_size=0 → 422", requests.get(f"{URL}/?page_size=0", headers=HEADERS), 422)
check("page_size=201 → 422", requests.get(f"{URL}/?page_size=201", headers=HEADERS), 422)
check("page=-1 → 422", requests.get(f"{URL}/?page=-1", headers=HEADERS), 422)
check("page=abc → 422", requests.get(f"{URL}/?page=abc", headers=HEADERS), 422)

section("5. DELETE 单条")

check("DELETE 不存在 id → 404",
      requests.delete(f"{URL}/nonexistent_id_xyz", headers=HEADERS), 404)
check("DELETE 路径为空 → 405",
      requests.delete(f"{URL}/", headers=HEADERS), 405)

delete_id = SEEDED_IDS.pop()
resp = requests.delete(f"{URL}/{delete_id}", headers=HEADERS)
check(f"DELETE 真实记录 id={delete_id[:16]}... → 204", resp, 204)
check("二次 DELETE 同一 id → 404",
      requests.delete(f"{URL}/{delete_id}", headers=HEADERS), 404)

section("6. batch-delete")

check("空 ids → 422",
      requests.post(f"{URL}/batch-delete", json={"ids": []}, headers=HEADERS), 422)
check("101 条（超限）→ 422",
      requests.post(f"{URL}/batch-delete", json={"ids": [f'fake_{i}' for i in range(101)]}, headers=HEADERS), 422)
r_bd = check("100 条不存在 id → 200，deleted=0",
             requests.post(f"{URL}/batch-delete",
                           json={"ids": [f"fake_{i}" for i in range(100)]},
                           headers=HEADERS))
if r_bd:
    assert r_bd.get("deleted") == 0, f"deleted 应为 0，实际={r_bd.get('deleted')}"

batch_ids = SEEDED_IDS[:2]
r_bd2 = check("真实 2 条 → 200，deleted=2",
              requests.post(f"{URL}/batch-delete", json={"ids": batch_ids}, headers=HEADERS))
if r_bd2:
    assert r_bd2.get("deleted") == 2, f"deleted 应为 2，实际={r_bd2.get('deleted')}"
    SEEDED_IDS[:] = [row_id for row_id in SEEDED_IDS if row_id not in batch_ids]

check("缺少 ids 字段 → 422",
      requests.post(f"{URL}/batch-delete", json={}, headers=HEADERS), 422)
check("ids 含 null → 422",
      requests.post(f"{URL}/batch-delete", json={"ids": [None]}, headers=HEADERS), 422)
check("ids 含整数 → 422",
      requests.post(f"{URL}/batch-delete", json={"ids": [1, 2]}, headers=HEADERS), 422)
check("ids 不是数组 → 422",
      requests.post(f"{URL}/batch-delete", json={"ids": "abc"}, headers=HEADERS), 422)
check("body 为空 → 422",
      requests.post(f"{URL}/batch-delete", data="", headers=HEADERS), 422)

section("7. 极端参数")

check("session_id 超长 1000 字符 → 200（不崩溃）",
      requests.get(f"{URL}/?session_id={'x' * 1000}", headers=HEADERS))
check("keyword SQL 注入尝试 → 200（数据不受影响）",
      requests.get(f"{URL}/?keyword='; DROP TABLE window_metrics_keywords; --", headers=HEADERS))
check("keyword 空字符串 → 200（被忽略，返回全量）",
      requests.get(f"{URL}/?keyword=", headers=HEADERS))

print(f"\n{'=' * 60}")
print(f"  结果汇总：通过 {_pass}，失败 {_fail}")
print(f"{'=' * 60}\n")

if _fail > 0:
    sys.exit(1)
