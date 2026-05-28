"""
CoI Utterances 后台接口专项测试
覆盖：导入、列表、编辑、删除、合并、拆分、编码、排序、鉴权、异常

用法：
  python -m backend.tests.test_admin_coi_utterances
"""
from __future__ import annotations

import sys
import uuid
from typing import Any

import requests

BASE_URL = "http://127.0.0.1:8000"
ADMIN_HEADERS = {"X-Admin-Token": "TestAdminKey123"}
RUN_ID = uuid.uuid4().hex[:6]

_pass = 0
_fail = 0


def _check(label: str, response: requests.Response, expect: int) -> bool:
    global _pass, _fail
    ok = response.status_code == expect
    icon = "✅" if ok else "❌"
    print(f"{icon} [{response.status_code}] {label}")
    if ok:
        _pass += 1
        return True
    _fail += 1
    print("   详情:", response.text[:400])
    return False


def _ok(label: str, condition: bool, extra: Any = None) -> bool:
    global _pass, _fail
    icon = "✅" if condition else "❌"
    print(f"{icon} {label}")
    if condition:
        _pass += 1
    else:
        _fail += 1
        if extra is not None:
            print("   详情:", extra)
    return condition


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _title(name: str) -> None:
    print(f"\n{'=' * 68}\n{name}\n{'=' * 68}")


def _register_and_login(suffix: str) -> tuple[dict[str, Any], str]:
    email = f"coi_{suffix}_{uuid.uuid4().hex[:6]}@example.com"
    reg = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={"name": f"COI {suffix}", "email": email, "password": "1234"},
    )
    reg.raise_for_status()
    login = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": "1234"},
    )
    login.raise_for_status()
    return reg.json(), login.json()["access_token"]


def _setup_context() -> dict[str, Any]:
    """建用户 → 群组 → 会话 → 启动会话，返回必要 id。"""
    user, token = _register_and_login(f"leader_{RUN_ID}")

    g = requests.post(
        f"{BASE_URL}/api/groups",
        headers=_auth(token),
        json={"name": f"CoI Group {RUN_ID}"},
    )
    g.raise_for_status()
    group_id = g.json()["group"]["id"]

    s = requests.post(
        f"{BASE_URL}/api/groups/{group_id}/sessions",
        headers=_auth(token),
        json={"session_title": f"CoI Session {RUN_ID}"},
    )
    s.raise_for_status()
    session_id = s.json()["id"]

    requests.post(f"{BASE_URL}/api/sessions/{session_id}/start", headers=_auth(token)).raise_for_status()
    # 立即结束，避免 agent 把测试会话当作真实进行中会话处理
    requests.post(f"{BASE_URL}/api/sessions/{session_id}/end", headers=_auth(token)).raise_for_status()

    return {
        "user_id": user["id"],
        "group_id": group_id,
        "session_id": session_id,
        "token": token,
    }


def _create_transcript(ctx: dict[str, Any], text: str, speaker: str = "Speaker-A") -> dict[str, Any]:
    r = requests.post(
        f"{BASE_URL}/api/admin/transcripts/",
        headers=ADMIN_HEADERS,
        json={
            "session_id": ctx["session_id"],
            "group_id": ctx["group_id"],
            "user_id": ctx["user_id"],
            "speaker": speaker,
            "text": text,
            "start": "2026-05-01T09:00:00",
            "end": "2026-05-01T09:00:05",
            "duration": 5.0,
            "confidence": 0.95,
        },
    )
    r.raise_for_status()
    return r.json()


def _list(session_id: str) -> list[dict]:
    r = requests.get(
        f"{BASE_URL}/api/admin/coi-utterances/",
        headers=ADMIN_HEADERS,
        params={"session_id": session_id},
    )
    r.raise_for_status()
    return r.json()


def run() -> None:
    print(f"\n[RUN_ID={RUN_ID}] coi-utterances tests\n")

    ctx = _setup_context()
    session_id = ctx["session_id"]

    # ── A. 鉴权 ──────────────────────────────────────────────────────────────
    _title("A. 鉴权")
    _check(
        "GET 无 token -> 403",
        requests.get(f"{BASE_URL}/api/admin/coi-utterances/", params={"session_id": session_id}),
        403,
    )
    _check(
        "POST /import 无 token -> 403",
        requests.post(f"{BASE_URL}/api/admin/coi-utterances/import", params={"session_id": session_id}),
        403,
    )
    _check(
        "POST /merge 无 token -> 403",
        requests.post(f"{BASE_URL}/api/admin/coi-utterances/merge", json={"ids": ["x", "y"]}),
        403,
    )

    # ── B. 导入（空 session，再导入有数据的）────────────────────────────────
    _title("B. 导入")
    r_empty = requests.post(
        f"{BASE_URL}/api/admin/coi-utterances/import",
        headers=ADMIN_HEADERS,
        params={"session_id": session_id},
    )
    _check("空 session 导入 -> 200", r_empty, 200)
    if r_empty.ok:
        _ok("空 session imported=0", r_empty.json().get("imported") == 0, r_empty.json())

    # 创建 3 条原始转写
    tr1 = _create_transcript(ctx, "我认为这个方案需要更多的数据支撑。", "张三")
    tr2 = _create_transcript(ctx, "对，我们可以先收集一下相关资料。", "李四")
    tr3 = _create_transcript(ctx, "那我来负责整理数据部分吧。", "王五")

    r_import = requests.post(
        f"{BASE_URL}/api/admin/coi-utterances/import",
        headers=ADMIN_HEADERS,
        params={"session_id": session_id},
    )
    _check("导入 3 条转写 -> 200", r_import, 200)
    if r_import.ok:
        d = r_import.json()
        _ok("imported=3", d.get("imported") == 3, d)
        _ok("skipped=0", d.get("skipped") == 0, d)

    # 重复导入应跳过
    r_dup = requests.post(
        f"{BASE_URL}/api/admin/coi-utterances/import",
        headers=ADMIN_HEADERS,
        params={"session_id": session_id},
    )
    _check("重复导入 -> 200", r_dup, 200)
    if r_dup.ok:
        d2 = r_dup.json()
        _ok("重复导入 imported=0", d2.get("imported") == 0, d2)
        _ok("重复导入 skipped=3", d2.get("skipped") == 3, d2)

    # ── C. 列表查询 ───────────────────────────────────────────────────────────
    _title("C. 列表查询")
    items = _list(session_id)
    _ok("列表返回 3 条", len(items) == 3, items)
    _ok("按 order_index 升序", [i["order_index"] for i in items] == sorted(i["order_index"] for i in items), items)
    _ok("source_transcript_ids 非空", all(len(i["source_transcript_ids"]) > 0 for i in items), items)
    _ok("coi_category 初始为 null", all(i["coi_category"] is None for i in items), items)

    # ── D. 编辑 ───────────────────────────────────────────────────────────────
    _title("D. 编辑（PATCH）")
    uid = items[0]["id"]
    r_patch = requests.patch(
        f"{BASE_URL}/api/admin/coi-utterances/{uid}",
        headers=ADMIN_HEADERS,
        json={"content": "修改后的发言内容", "speaker": "张三（修改）"},
    )
    _check("PATCH 已有记录 -> 200", r_patch, 200)
    if r_patch.ok:
        _ok("内容已更新", r_patch.json()["content"] == "修改后的发言内容", r_patch.json())
        _ok("说话人已更新", r_patch.json()["speaker"] == "张三（修改）", r_patch.json())

    _check(
        "PATCH 空 payload -> 400",
        requests.patch(f"{BASE_URL}/api/admin/coi-utterances/{uid}", headers=ADMIN_HEADERS, json={}),
        400,
    )
    _check(
        "PATCH 不存在记录 -> 404",
        requests.patch(
            f"{BASE_URL}/api/admin/coi-utterances/cu_not_exist_999",
            headers=ADMIN_HEADERS,
            json={"content": "x"},
        ),
        404,
    )

    # ── E. CoI 编码 ───────────────────────────────────────────────────────────
    _title("E. CoI 编码（PATCH /{id}/code）")
    for cat in ["TE", "EX", "IN", "RE"]:
        r_code = requests.patch(
            f"{BASE_URL}/api/admin/coi-utterances/{uid}/code",
            headers=ADMIN_HEADERS,
            json={"coi_category": cat, "coded_by": "test-admin"},
        )
        _check(f"编码为 {cat} -> 200", r_code, 200)
        if r_code.ok:
            _ok(f"coi_category={cat}", r_code.json()["coi_category"] == cat, r_code.json())

    # 清除编码（传 null）
    r_clear = requests.patch(
        f"{BASE_URL}/api/admin/coi-utterances/{uid}/code",
        headers=ADMIN_HEADERS,
        json={"coi_category": None},
    )
    _check("清除编码（null）-> 200", r_clear, 200)
    if r_clear.ok:
        _ok("coi_category=null", r_clear.json()["coi_category"] is None, r_clear.json())

    # 非法分类
    _check(
        "非法 coi_category -> 400",
        requests.patch(
            f"{BASE_URL}/api/admin/coi-utterances/{uid}/code",
            headers=ADMIN_HEADERS,
            json={"coi_category": "XX"},
        ),
        400,
    )
    _check(
        "编码不存在记录 -> 404",
        requests.patch(
            f"{BASE_URL}/api/admin/coi-utterances/cu_not_exist_999/code",
            headers=ADMIN_HEADERS,
            json={"coi_category": "TE"},
        ),
        404,
    )

    # ── F. 拆分 ───────────────────────────────────────────────────────────────
    _title("F. 拆分（POST /{id}/split）")
    # 使用第二条（内容："对，我们可以先收集一下相关资料。"）
    items_now = _list(session_id)
    split_item = items_now[1]
    split_uid = split_item["id"]
    content_len = len(split_item["content"])
    offset = content_len // 2

    r_split = requests.post(
        f"{BASE_URL}/api/admin/coi-utterances/{split_uid}/split",
        headers=ADMIN_HEADERS,
        json={"offset": offset},
    )
    _check("拆分 -> 200", r_split, 200)
    if r_split.ok:
        parts = r_split.json()
        _ok("拆分返回 2 条", len(parts) == 2, parts)
        _ok("第一段非空", len(parts[0]["content"].strip()) > 0, parts[0])
        _ok("第二段非空", len(parts[1]["content"].strip()) > 0, parts[1])
        _ok("两段 order_index 相差 1", parts[1]["order_index"] - parts[0]["order_index"] == 1, parts)

    # 拆分后总数应为 4
    items_after_split = _list(session_id)
    _ok("拆分后列表共 4 条", len(items_after_split) == 4, [i["order_index"] for i in items_after_split])

    # 异常：offset=0
    _check(
        "offset=0 -> 400",
        requests.post(
            f"{BASE_URL}/api/admin/coi-utterances/{split_uid}/split",
            headers=ADMIN_HEADERS,
            json={"offset": 0},
        ),
        400,
    )
    # 异常：offset 超出内容长度
    current = next(i for i in _list(session_id) if i["id"] == split_uid)
    _check(
        "offset >= len(content) -> 400",
        requests.post(
            f"{BASE_URL}/api/admin/coi-utterances/{split_uid}/split",
            headers=ADMIN_HEADERS,
            json={"offset": len(current["content"]) + 100},
        ),
        400,
    )
    # 不存在记录
    _check(
        "拆分不存在记录 -> 404",
        requests.post(
            f"{BASE_URL}/api/admin/coi-utterances/cu_not_exist_999/split",
            headers=ADMIN_HEADERS,
            json={"offset": 5},
        ),
        404,
    )

    # ── G. 合并 ───────────────────────────────────────────────────────────────
    _title("G. 合并（POST /merge）")
    items_before_merge = _list(session_id)
    merge_ids = [items_before_merge[0]["id"], items_before_merge[1]["id"]]
    combined_content = "\n".join(i["content"] for i in items_before_merge[:2])

    r_merge = requests.post(
        f"{BASE_URL}/api/admin/coi-utterances/merge",
        headers=ADMIN_HEADERS,
        json={"ids": merge_ids},
    )
    _check("合并 2 条 -> 200", r_merge, 200)
    if r_merge.ok:
        merged = r_merge.json()
        _ok("合并后内容拼接正确", merged["content"] == combined_content, merged["content"])
        _ok("source_transcript_ids 合并", len(merged["source_transcript_ids"]) >= 1, merged)
        _ok("coi_category 重置为 null", merged["coi_category"] is None, merged)

    # 合并后总数减 1
    items_after_merge = _list(session_id)
    _ok("合并后总数减 1", len(items_after_merge) == len(items_before_merge) - 1, len(items_after_merge))

    # 异常：只传 1 个 id
    _check(
        "merge ids<2 -> 400",
        requests.post(
            f"{BASE_URL}/api/admin/coi-utterances/merge",
            headers=ADMIN_HEADERS,
            json={"ids": [items_after_merge[0]["id"]]},
        ),
        400,
    )
    # 异常：包含不存在 id
    _check(
        "merge 含不存在 id -> 404",
        requests.post(
            f"{BASE_URL}/api/admin/coi-utterances/merge",
            headers=ADMIN_HEADERS,
            json={"ids": [items_after_merge[0]["id"], "cu_not_exist_999"]},
        ),
        404,
    )

    # ── H. 排序 ───────────────────────────────────────────────────────────────
    _title("H. 排序（POST /reorder）")
    current_items = _list(session_id)
    # 把顺序反转
    reversed_order = [
        {"id": item["id"], "order_index": len(current_items) - i}
        for i, item in enumerate(current_items)
    ]
    r_reorder = requests.post(
        f"{BASE_URL}/api/admin/coi-utterances/reorder",
        headers=ADMIN_HEADERS,
        json={"items": reversed_order},
    )
    _check("reorder -> 204", r_reorder, 204)

    # 验证排序已生效
    reordered = _list(session_id)
    _ok(
        "排序后 order_index 已更新",
        set(i["order_index"] for i in reordered) == set(x["order_index"] for x in reversed_order),
        reordered,
    )

    # ── I. 删除 ───────────────────────────────────────────────────────────────
    _title("I. 删除（DELETE）")
    del_item = _list(session_id)[0]
    del_id = del_item["id"]

    r_del = requests.delete(
        f"{BASE_URL}/api/admin/coi-utterances/{del_id}",
        headers=ADMIN_HEADERS,
    )
    _check("DELETE -> 204", r_del, 204)

    _check(
        "重复 DELETE 同一条 -> 404",
        requests.delete(f"{BASE_URL}/api/admin/coi-utterances/{del_id}", headers=ADMIN_HEADERS),
        404,
    )
    _check(
        "DELETE 不存在记录 -> 404",
        requests.delete(f"{BASE_URL}/api/admin/coi-utterances/cu_not_exist_999", headers=ADMIN_HEADERS),
        404,
    )

    # ── J. 汇总 ───────────────────────────────────────────────────────────────
    total = _pass + _fail
    print(f"\n{'=' * 68}")
    print(f"结果：通过 {_pass}/{total}，失败 {_fail}/{total}")
    if _fail:
        sys.exit(1)


if __name__ == "__main__":
    run()
