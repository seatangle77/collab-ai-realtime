"""
窗口论证批量日志接口测试
覆盖：稳定 seed 数据、查询过滤、分页边界、DELETE / batch-delete、参数异常、认证鉴权

用法（在 backend/ 目录下）：
    python -m tests.test_window_metrics_batch_reasoning

前置条件：
    后端已启动：uvicorn app.main:app --reload --port 8000
"""
import asyncio
import atexit
import json
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
URL = f"{BASE}/api/admin/window-metrics-batch-reasoning"
SESSION_PREFIX = f"sess_test_wmbr_{uuid.uuid4().hex[:8]}"
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
        asyncio.run(
            exec_sql(
                "DELETE FROM window_metrics_batch_reasoning WHERE id = ANY(:ids)",
                {"ids": SEEDED_IDS},
            )
        )
    except Exception as exc:
        print(f"[cleanup] 删除测试数据失败: {exc}")


def _members_json(members: list[dict]) -> str:
    return json.dumps(members, ensure_ascii=False).replace("'", "''")


def seed_rows() -> None:
    rows = [
        {
            "id": f"wmbr_test_{uuid.uuid4().hex[:8]}",
            "session_id": SESSION_PREFIX,
            "window_start": "2025-01-01 14:00:00",
            "members": [
                {
                    "user_id": "u_reasoning_1",
                    "reasoning_status": True,
                    "evidence_status": False,
                    "reasoning_source": "表达了明确原因。",
                    "evidence_source": "没有给出案例。",
                },
                {
                    "user_id": "u_reasoning_2",
                    "reasoning_status": False,
                    "evidence_status": True,
                    "reasoning_source": "只有结论，没有推理。",
                    "evidence_source": "引用了具体案例。",
                },
            ],
        },
        {
            "id": f"wmbr_test_{uuid.uuid4().hex[:8]}",
            "session_id": SESSION_PREFIX,
            "window_start": "2025-01-01 14:01:00",
            "members": [],
        },
        {
            "id": f"wmbr_test_{uuid.uuid4().hex[:8]}",
            "session_id": SESSION_PREFIX,
            "window_start": "2025-01-01 14:02:00",
            "members": [
                {
                    "user_id": "u_reasoning_3",
                    "reasoning_status": None,
                    "evidence_status": None,
                    "reasoning_source": None,
                    "evidence_source": None,
                }
            ],
        },
    ]
    SEEDED_IDS.extend(row["id"] for row in rows)
    values = ",\n".join(
        "('{id}', '{session_id}', '{window_start}', '{members}'::jsonb, NOW())".format(
            id=row["id"],
            session_id=row["session_id"],
            window_start=row["window_start"],
            members=_members_json(row["members"]),
        )
        for row in rows
    )
    sql = f"""
    INSERT INTO window_metrics_batch_reasoning
      (id, session_id, window_start, members, created_at)
    VALUES
      {values}
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
    assert data["meta"]["total"] >= 3, "seed 数据数量异常"
    assert len(data["items"]) >= 3, "seed 数据未查到"
    sample = data["items"][0]
    for field in ["id", "session_id", "window_start", "members", "created_at"]:
        assert field in sample, f"缺少字段: {field}"
    assert isinstance(sample["members"], list), "members 应为数组"

section("3. 过滤条件")

data = check("filter: session_id 精确匹配",
             requests.get(f"{URL}/?session_id={SESSION_PREFIX}", headers=HEADERS))
if data:
    assert_items_all(data, lambda item: item["session_id"] == SESSION_PREFIX, "session_id 过滤错误")

data = check("filter: window_start_from",
             requests.get(f"{URL}/?session_id={SESSION_PREFIX}&window_start_from=2025-01-01T14:01:00Z", headers=HEADERS))
if data:
    assert_items_all(data, lambda item: item["window_start"] >= "2025-01-01T14:01:00", "window_start_from 过滤错误")

data = check("filter: window_start_to",
             requests.get(f"{URL}/?session_id={SESSION_PREFIX}&window_start_to=2025-01-01T14:01:00Z", headers=HEADERS))
if data:
    assert_items_all(data, lambda item: item["window_start"] <= "2025-01-01T14:01:00", "window_start_to 过滤错误")

data = check("filter: 组合=session_id + 时间范围",
             requests.get(
                 f"{URL}/?session_id={SESSION_PREFIX}"
                 "&window_start_from=2025-01-01T14:00:00Z&window_start_to=2025-01-01T14:01:00Z",
                 headers=HEADERS,
             ))
if data:
    assert_items_all(data, lambda item: item["session_id"] == SESSION_PREFIX, "组合过滤错误")

data = check("filter: window_start_from > window_start_to（时间倒置）",
             requests.get(
                 f"{URL}/?session_id={SESSION_PREFIX}"
                 "&window_start_from=2099-01-01T00:00:00Z&window_start_to=2024-01-01T00:00:00Z",
                 headers=HEADERS,
             ))
if data:
    assert data["items"] == [], "时间倒置应返回空列表"

section("4. 分页边界")

data = check("page=1 page_size=1",
             requests.get(f"{URL}/?session_id={SESSION_PREFIX}&page=1&page_size=1", headers=HEADERS))
if data:
    assert len(data["items"]) == 1, "page_size=1 应只返回 1 条"

data = check("page=999999（超大页码）",
             requests.get(f"{URL}/?session_id={SESSION_PREFIX}&page=999999", headers=HEADERS))
if data:
    assert data["items"] == [], "超大页码应返回空列表"

check("page=0 → 422", requests.get(f"{URL}/?page=0", headers=HEADERS), 422)
check("page_size=201 → 422", requests.get(f"{URL}/?page_size=201", headers=HEADERS), 422)

section("5. members 内容")

data = check("members 数组字段结构正确",
             requests.get(f"{URL}/?session_id={SESSION_PREFIX}&window_start_from=2025-01-01T14:00:00Z&page_size=20", headers=HEADERS))
if data:
    non_empty = next(item for item in data["items"] if item["members"])
    member = non_empty["members"][0]
    for field in ["user_id", "reasoning_status", "evidence_status", "reasoning_source", "evidence_source"]:
        assert field in member, f"members 缺少字段: {field}"

    empty_members = next(item for item in data["items"] if item["window_start"].startswith("2025-01-01T14:01:00"))
    assert empty_members["members"] == [], "空 members 应返回 []"

section("6. DELETE 单条")

check("DELETE 不存在 → 404",
      requests.delete(f"{URL}/nonexistent_id_xyz", headers=HEADERS), 404)

delete_id = SEEDED_IDS.pop()
check(f"DELETE 真实存在记录 id={delete_id[:16]}...",
      requests.delete(f"{URL}/{delete_id}", headers=HEADERS), 204)
check("重复删除 → 404", requests.delete(f"{URL}/{delete_id}", headers=HEADERS), 404)

section("7. batch-delete")

check("batch-delete 空 ids → 422",
      requests.post(f"{URL}/batch-delete", json={"ids": []}, headers=HEADERS), 422)
check("batch-delete 101 条超限 → 422",
      requests.post(f"{URL}/batch-delete", json={"ids": [f'fake_{i}' for i in range(101)]}, headers=HEADERS), 422)

r_bd = check("batch-delete 不存在 ids → deleted=0",
             requests.post(f"{URL}/batch-delete", json={"ids": ["fake_1", "fake_2"]}, headers=HEADERS))
if r_bd:
    assert r_bd.get("deleted") == 0, "不存在 ids 时 deleted 应为 0"

batch_ids = SEEDED_IDS[:2]
r_bd2 = check("batch-delete 真实记录",
              requests.post(f"{URL}/batch-delete", json={"ids": batch_ids}, headers=HEADERS))
if r_bd2:
    assert r_bd2.get("deleted") == len(batch_ids), "batch-delete 删除数量错误"
    SEEDED_IDS[:] = [row_id for row_id in SEEDED_IDS if row_id not in batch_ids]

section("8. 极端参数")

check("session_id 超长字符串",
      requests.get(f"{URL}/?session_id={'x' * 1000}", headers=HEADERS))
check("window_start_from 非法 → 422",
      requests.get(f"{URL}/?window_start_from=not-a-date", headers=HEADERS), 422)
check("window_start_to 非法 → 422",
      requests.get(f"{URL}/?window_start_to=not-a-date", headers=HEADERS), 422)

print(f"\n{'=' * 60}")
print(f"  结果汇总：通过 {_pass}，失败 {_fail}")
print(f"{'=' * 60}\n")

if _fail > 0:
    sys.exit(1)
