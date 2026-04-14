"""
speech_transcripts 后台接口专项测试
覆盖：增删改查、鉴权、异常、边界、极端文本场景

用法：
  python -m backend.tests.test_admin_speech_transcripts
"""
from __future__ import annotations

import sys
import uuid
from typing import Any

import requests

BASE_URL = "http://127.0.0.1:8000"
RUN_ID = uuid.uuid4().hex[:6]
ADMIN_HEADERS = {"X-Admin-Token": "TestAdminKey123"}

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
    print("   详情:", response.text[:300])
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


def _register_and_login(suffix: str) -> tuple[dict[str, Any], str]:
    email = f"st_{suffix}_{uuid.uuid4().hex[:6]}@example.com"
    register = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={
            "name": f"ST {suffix}",
            "email": email,
            "password": "1234",
            "device_token": f"dev-{uuid.uuid4().hex[:8]}",
        },
    )
    register.raise_for_status()
    login = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": "1234"},
    )
    login.raise_for_status()
    return register.json(), login.json()["access_token"]


def _setup_context() -> dict[str, Any]:
    leader, token = _register_and_login(f"leader_{RUN_ID}")

    group_resp = requests.post(
        f"{BASE_URL}/api/groups",
        headers=_auth(token),
        json={"name": f"ST Group {RUN_ID}"},
    )
    group_resp.raise_for_status()
    group_id = group_resp.json()["group"]["id"]

    session_resp = requests.post(
        f"{BASE_URL}/api/groups/{group_id}/sessions",
        headers=_auth(token),
        json={"session_title": f"ST Session {RUN_ID}"},
    )
    session_resp.raise_for_status()
    session_id = session_resp.json()["id"]

    requests.post(f"{BASE_URL}/api/sessions/{session_id}/start", headers=_auth(token)).raise_for_status()
    return {
        "leader_id": leader["id"],
        "group_id": group_id,
        "session_id": session_id,
    }


def _create_transcript(
    ctx: dict[str, Any],
    *,
    text: str = "默认转写文本",
    speaker: str = "speaker-A",
    start: str = "2026-04-14T08:00:00",
    end: str = "2026-04-14T08:00:05",
    duration: float = 5.0,
    confidence: float = 0.91,
) -> dict[str, Any]:
    payload = {
        "session_id": ctx["session_id"],
        "group_id": ctx["group_id"],
        "user_id": ctx["leader_id"],
        "speaker": speaker,
        "text": text,
        "start": start,
        "end": end,
        "duration": duration,
        "confidence": confidence,
    }
    response = requests.post(f"{BASE_URL}/api/admin/transcripts/", headers=ADMIN_HEADERS, json=payload)
    response.raise_for_status()
    return response.json()


def _title(name: str) -> None:
    print(f"\n{'=' * 68}\n{name}\n{'=' * 68}")


def run() -> None:
    print(f"\n[RUN_ID={RUN_ID}] admin speech transcripts tests\n")
    ctx = _setup_context()

    _title("A. 鉴权与异常")
    _check("GET /speech-transcripts 无 token -> 403", requests.get(f"{BASE_URL}/api/admin/speech-transcripts/"), 403)
    _check(
        "POST /admin/transcripts 无 token -> 403",
        requests.post(
            f"{BASE_URL}/api/admin/transcripts/",
            json={
                "session_id": ctx["session_id"],
                "group_id": ctx["group_id"],
                "text": "x",
                "start": "2026-04-14T08:00:00",
                "end": "2026-04-14T08:00:01",
            },
        ),
        403,
    )
    _check(
        "PATCH 不存在 transcript -> 404",
        requests.patch(
            f"{BASE_URL}/api/admin/transcripts/tr_not_exists_999",
            headers=ADMIN_HEADERS,
            json={"text": "updated"},
        ),
        404,
    )
    _check(
        "GET 非法时间 created_from=bad -> 422",
        requests.get(f"{BASE_URL}/api/admin/speech-transcripts/?created_from=bad", headers=ADMIN_HEADERS),
        422,
    )
    _check(
        "GET page_size=101 -> 422",
        requests.get(f"{BASE_URL}/api/admin/speech-transcripts/?page_size=101", headers=ADMIN_HEADERS),
        422,
    )
    _check(
        "batch-delete ids 空数组 -> 422",
        requests.post(
            f"{BASE_URL}/api/admin/speech-transcripts/batch-delete",
            headers=ADMIN_HEADERS,
            json={"ids": []},
        ),
        422,
    )

    _title("B. Create（增）+ 极端文本")
    extreme_text = "语音转写极端内容|" + ("超长文本片段_" * 600) + "|%_';DROP TABLE"
    created = _create_transcript(
        ctx,
        text=extreme_text,
        speaker="speaker-extreme",
        duration=9999.123,
        confidence=0.0001,
    )
    _ok("创建成功并返回 transcript_id", created.get("transcript_id", "").startswith("tr"), created)
    _ok("创建后 is_edited 默认 false", created.get("is_edited") is False, created)

    _title("C. Read（查）+ 过滤/边界")
    list_all = requests.get(
        f"{BASE_URL}/api/admin/speech-transcripts/",
        headers=ADMIN_HEADERS,
        params={"session_id": ctx["session_id"], "page": 1, "page_size": 20},
    )
    _check("按 session_id 列表查询 -> 200", list_all, 200)
    data = list_all.json() if list_all.ok else {"items": [], "meta": {"total": 0}}
    _ok("返回分页结构 items/meta", "items" in data and "meta" in data, data)
    _ok(
        "列表包含刚创建记录",
        any(it.get("transcript_id") == created["transcript_id"] for it in data.get("items", [])),
        data.get("items", [])[:3],
    )

    _check(
        "speaker 模糊过滤 -> 200",
        requests.get(
            f"{BASE_URL}/api/admin/speech-transcripts/",
            headers=ADMIN_HEADERS,
            params={"speaker": "extreme", "session_id": ctx["session_id"]},
        ),
        200,
    )
    _check(
        "text 关键词过滤(含特殊字符 %) -> 200",
        requests.get(
            f"{BASE_URL}/api/admin/speech-transcripts/",
            headers=ADMIN_HEADERS,
            params={"text": "%_", "session_id": ctx["session_id"]},
        ),
        200,
    )
    _check(
        "超大页码 page=999999 -> 200",
        requests.get(
            f"{BASE_URL}/api/admin/speech-transcripts/",
            headers=ADMIN_HEADERS,
            params={"page": 999999, "session_id": ctx["session_id"]},
        ),
        200,
    )

    _title("D. Update（改）")
    patch = requests.patch(
        f"{BASE_URL}/api/admin/transcripts/{created['transcript_id']}",
        headers=ADMIN_HEADERS,
        json={"text": "修正后的转写文本"},
    )
    _check("PATCH 已有 transcript -> 200", patch, 200)
    patched = patch.json() if patch.ok else {}
    _ok("PATCH 后 is_edited=true", patched.get("is_edited") is True, patched)
    _ok("PATCH 后 original_text 被保存", patched.get("original_text") == extreme_text, patched)

    _check(
        "PATCH 缺少 text -> 422",
        requests.patch(
            f"{BASE_URL}/api/admin/transcripts/{created['transcript_id']}",
            headers=ADMIN_HEADERS,
            json={},
        ),
        422,
    )

    _title("E. Delete（删）单条 + 批量")
    delete_single_target = _create_transcript(ctx, text="待单删", speaker="speaker-del-single")
    _check(
        "DELETE 单条 -> 204",
        requests.delete(
            f"{BASE_URL}/api/admin/speech-transcripts/{delete_single_target['transcript_id']}",
            headers=ADMIN_HEADERS,
        ),
        204,
    )
    _check(
        "DELETE 同一条再次删除 -> 404",
        requests.delete(
            f"{BASE_URL}/api/admin/speech-transcripts/{delete_single_target['transcript_id']}",
            headers=ADMIN_HEADERS,
        ),
        404,
    )

    b1 = _create_transcript(ctx, text="待批删1", speaker="speaker-batch")
    b2 = _create_transcript(ctx, text="待批删2", speaker="speaker-batch")
    b3 = _create_transcript(ctx, text="待批删3", speaker="speaker-batch")

    batch = requests.post(
        f"{BASE_URL}/api/admin/speech-transcripts/batch-delete",
        headers=ADMIN_HEADERS,
        json={"ids": [b1["transcript_id"], b2["transcript_id"], b3["transcript_id"], "tr_not_exists_1"]},
    )
    _check("batch-delete 混合有效+无效 -> 200", batch, 200)
    if batch.ok:
        _ok("batch-delete deleted=3", batch.json().get("deleted") == 3, batch.json())

    _check(
        "batch-delete 100 个不存在 id（边界）-> 200",
        requests.post(
            f"{BASE_URL}/api/admin/speech-transcripts/batch-delete",
            headers=ADMIN_HEADERS,
            json={"ids": [f"tr_fake_{i}" for i in range(100)]},
        ),
        200,
    )
    _check(
        "batch-delete 101 个 id（超限）-> 422",
        requests.post(
            f"{BASE_URL}/api/admin/speech-transcripts/batch-delete",
            headers=ADMIN_HEADERS,
            json={"ids": [f"tr_over_{i}" for i in range(101)]},
        ),
        422,
    )

    total = _pass + _fail
    print(f"\n结果：通过 {_pass}/{total}，失败 {_fail}/{total}")
    if _fail:
        sys.exit(1)


if __name__ == "__main__":
    run()
