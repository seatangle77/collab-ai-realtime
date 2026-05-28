"""
Live integration test for questionnaire entries (SRCC + PCS) APIs.

Prerequisites:
- backend is running at BASE_URL (default: http://127.0.0.1:8000)
- questionnaire_entries table exists

Usage:
  python -m backend.tests.test_questionnaire_entries
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Any

import requests

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

BASE_URL = "http://127.0.0.1:8000"
ADMIN_HEADERS = {"X-Admin-Token": "TestAdminKey123"}
RUN_ID = uuid.uuid4().hex[:6]

# 完整的 SRCC 作答（15题，1-7分）
SRCC_FULL = {f"q{i}": (i % 7) + 1 for i in range(1, 16)}

# 完整的 PCS 作答（6题，1-7分）
PCS_FULL = {f"q{i}": 7 - (i % 3) for i in range(1, 7)}


def _log(ok: bool, message: str, extra: Any | None = None) -> bool:
    print(f"{'✅' if ok else '❌'} {message}")
    if not ok and extra is not None:
        print("   详情:", extra)
    return ok


def _register_and_login(label: str) -> dict[str, str]:
    email = f"survey_{label}_{RUN_ID}_{uuid.uuid4().hex[:4]}@example.com"
    password = "1234"
    r = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={"name": f"Survey {label}", "email": email, "password": password},
    )
    r.raise_for_status()
    user = r.json()
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    return {"user_id": user["id"], "token": r.json()["access_token"], "name": user["name"]}


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_three_member_group(condition: str = "glasses") -> dict[str, Any]:
    leader = _register_and_login("leader")
    member1 = _register_and_login("member1")
    member2 = _register_and_login("member2")

    r = requests.post(
        f"{BASE_URL}/api/groups",
        headers=_auth(leader["token"]),
        json={"name": f"Survey Group {RUN_ID}"},
    )
    r.raise_for_status()
    group_id = r.json()["group"]["id"]

    # 用户端建组不含 condition，需通过 admin API 补设
    r = requests.patch(
        f"{BASE_URL}/api/admin/groups/{group_id}",
        headers=ADMIN_HEADERS,
        json={"condition": condition},
    )
    r.raise_for_status()

    for member in [member1, member2]:
        r = requests.post(
            f"{BASE_URL}/api/groups/{group_id}/join",
            headers=_auth(member["token"]),
        )
        r.raise_for_status()

    return {"group_id": group_id, "members": [leader, member1, member2]}


# ─────────────────────────────────────────────────────────────────
# Scenario 1: GET /meta 返回正确的量表结构
# ─────────────────────────────────────────────────────────────────
def scenario_meta() -> bool:
    print("\n── Scenario 1: GET /api/questionnaire/meta ──")
    r = requests.get(f"{BASE_URL}/api/questionnaire/meta")
    if not _log(r.status_code == 200, "meta 接口返回 200", r.text):
        return False

    data = r.json()
    ok = True
    ok &= _log(len(data["srcc_items"]) == 15, f"SRCC 题目数量 = 15（实际 {len(data['srcc_items'])}）")
    ok &= _log(len(data["pcs_items"]) == 6, f"PCS 题目数量 = 6（实际 {len(data['pcs_items'])}）")
    ok &= _log(len(data["srcc_dimensions"]) == 4, "SRCC 维度数 = 4")
    ok &= _log(len(data["pcs_dimensions"]) == 2, "PCS 维度数 = 2")

    srcc_dims = set(item["dimension"] for item in data["srcc_items"])
    ok &= _log(
        srcc_dims == {"clarification", "elaboration", "refuting", "summarization"},
        "SRCC 四个维度均出现",
        srcc_dims,
    )
    pcs_dims = set(item["dimension"] for item in data["pcs_items"])
    ok &= _log(pcs_dims == {"belonging", "morale"}, "PCS 两个维度均出现", pcs_dims)
    return ok


# ─────────────────────────────────────────────────────────────────
# Scenario 2: GET /me 未填写时返回空
# ─────────────────────────────────────────────────────────────────
def scenario_empty_me() -> bool:
    print("\n── Scenario 2: GET /me 返回空（未填写）──")
    setup = _create_three_member_group()
    user = setup["members"][0]

    r = requests.get(f"{BASE_URL}/api/questionnaire/me", headers=_auth(user["token"]))
    if not _log(r.status_code == 200, "GET /me 返回 200", r.text):
        return False

    data = r.json()
    ok = True
    ok &= _log(data["srcc_responses"] is None, "srcc_responses 为 None（未填写）")
    ok &= _log(data["pcs_responses"] is None, "pcs_responses 为 None（未填写）")
    return ok


# ─────────────────────────────────────────────────────────────────
# Scenario 3: 提交 SRCC + PCS，验证均分计算
# ─────────────────────────────────────────────────────────────────
def scenario_submit_and_verify() -> bool:
    print("\n── Scenario 3: 提交 SRCC + PCS，验证均分计算 ──")
    setup = _create_three_member_group()
    user = setup["members"][0]
    headers = _auth(user["token"])

    # 提交 SRCC
    r = requests.post(
        f"{BASE_URL}/api/questionnaire/srcc",
        headers=headers,
        json={"responses": SRCC_FULL},
    )
    if not _log(r.status_code == 200, "POST /srcc 返回 200", r.text):
        return False

    entry = r.json()
    ok = True
    ok &= _log(entry["srcc_responses"] is not None, "srcc_responses 已保存")
    ok &= _log(entry["srcc_result"] is not None, "srcc_result 已计算")
    ok &= _log(entry["pcs_responses"] is None, "pcs_responses 仍为 None（未填写 PCS）")

    result = entry["srcc_result"]
    ok &= _log("clarification_avg" in result, "srcc_result 含 clarification_avg")
    ok &= _log("elaboration_avg" in result, "srcc_result 含 elaboration_avg")
    ok &= _log("refuting_avg" in result, "srcc_result 含 refuting_avg")
    ok &= _log("summarization_avg" in result, "srcc_result 含 summarization_avg")
    ok &= _log("total_avg" in result, "srcc_result 含 total_avg")
    ok &= _log(result["total_avg"] is not None, f"total_avg = {result.get('total_avg')}")

    # 提交 PCS
    r = requests.post(
        f"{BASE_URL}/api/questionnaire/pcs",
        headers=headers,
        json={"responses": PCS_FULL},
    )
    if not _log(r.status_code == 200, "POST /pcs 返回 200", r.text):
        return False

    entry = r.json()
    ok &= _log(entry["pcs_responses"] is not None, "pcs_responses 已保存")
    ok &= _log(entry["pcs_result"] is not None, "pcs_result 已计算")
    ok &= _log(entry["srcc_responses"] is not None, "提交 PCS 后 srcc_responses 仍保留")

    pcs_result = entry["pcs_result"]
    ok &= _log("belonging_avg" in pcs_result, "pcs_result 含 belonging_avg")
    ok &= _log("morale_avg" in pcs_result, "pcs_result 含 morale_avg")
    ok &= _log("total_avg" in pcs_result, "pcs_result 含 total_avg")

    # GET /me 验证持久化
    r = requests.get(f"{BASE_URL}/api/questionnaire/me", headers=headers)
    me = r.json()
    ok &= _log(me["srcc_responses"] == SRCC_FULL, "GET /me 返回的 srcc_responses 与提交一致")
    ok &= _log(me["pcs_responses"] == PCS_FULL, "GET /me 返回的 pcs_responses 与提交一致")

    return ok


# ─────────────────────────────────────────────────────────────────
# Scenario 4: 重复提交会覆盖旧记录（upsert）
# ─────────────────────────────────────────────────────────────────
def scenario_update_overwrites() -> bool:
    print("\n── Scenario 4: 重复提交覆盖旧记录（upsert）──")
    setup = _create_three_member_group()
    user = setup["members"][0]
    headers = _auth(user["token"])

    # 第一次提交
    r = requests.post(
        f"{BASE_URL}/api/questionnaire/srcc",
        headers=headers,
        json={"responses": SRCC_FULL},
    )
    r.raise_for_status()
    first_avg = r.json()["srcc_result"]["total_avg"]

    # 第二次提交（全部填 7）
    all_sevens = {f"q{i}": 7 for i in range(1, 16)}
    r = requests.post(
        f"{BASE_URL}/api/questionnaire/srcc",
        headers=headers,
        json={"responses": all_sevens},
    )
    if not _log(r.status_code == 200, "第二次 POST /srcc 返回 200", r.text):
        return False

    second = r.json()
    ok = True
    ok &= _log(second["srcc_result"]["total_avg"] == 7.0, f"更新后 total_avg = 7.0（原 {first_avg}）")
    ok &= _log(second["srcc_responses"]["q1"] == 7, "q1 已更新为 7")

    # 只有一条记录（唯一约束）
    r = requests.get(f"{BASE_URL}/api/questionnaire/me", headers=headers)
    me = r.json()
    ok &= _log(me["srcc_responses"]["q1"] == 7, "GET /me 确认只有一条记录，内容已覆盖")
    return ok


# ─────────────────────────────────────────────────────────────────
# Scenario 5: 无活跃群组的用户提交返回 400
# ─────────────────────────────────────────────────────────────────
def scenario_no_group_returns_400() -> bool:
    print("\n── Scenario 5: 无活跃群组的用户提交返回 400 ──")
    lone = _register_and_login("lone")
    r = requests.post(
        f"{BASE_URL}/api/questionnaire/srcc",
        headers=_auth(lone["token"]),
        json={"responses": SRCC_FULL},
    )
    return _log(r.status_code == 400, f"无群组用户提交返回 400（实际 {r.status_code}）", r.text)


# ─────────────────────────────────────────────────────────────────
# Scenario 6: 管理员列表查询 + 删除
# ─────────────────────────────────────────────────────────────────
def scenario_admin_list_and_delete() -> bool:
    print("\n── Scenario 6: 管理员列表查询 + 删除 ──")
    setup = _create_three_member_group()
    user = setup["members"][0]
    headers = _auth(user["token"])

    # 用户提交 SRCC
    r = requests.post(
        f"{BASE_URL}/api/questionnaire/srcc",
        headers=headers,
        json={"responses": SRCC_FULL},
    )
    r.raise_for_status()

    # 管理员查询列表
    r = requests.get(f"{BASE_URL}/api/admin/questionnaire-entries", headers=ADMIN_HEADERS)
    if not _log(r.status_code == 200, "GET /admin/questionnaire-entries 返回 200", r.text):
        return False

    body = r.json()
    user_id = user["user_id"]
    ok = True
    ok &= _log("items" in body and "meta" in body, "响应包含 items 和 meta 字段")
    ok &= _log(isinstance(body["meta"]["total"], int), f"meta.total 为整数（{body['meta'].get('total')}）")

    entries = body["items"]
    found = next((e for e in entries if e["user_id"] == user_id), None)

    ok &= _log(found is not None, f"管理员列表中找到 user_id={user_id}")
    if found:
        ok &= _log(found["srcc_responses"] is not None, "列表中 srcc_responses 有数据")
        ok &= _log(found["user_name"] is not None, "列表中 user_name 已 JOIN")
        ok &= _log(found["group_name"] is not None, "列表中 group_name 已 JOIN")

    # 管理员删除
    r = requests.delete(
        f"{BASE_URL}/api/admin/questionnaire-entries/{user_id}",
        headers=ADMIN_HEADERS,
    )
    ok &= _log(r.status_code == 204, f"DELETE 返回 204（实际 {r.status_code}）", r.text)

    # 删除后 GET /me 应返回空
    r = requests.get(f"{BASE_URL}/api/questionnaire/me", headers=headers)
    me = r.json()
    ok &= _log(me["srcc_responses"] is None, "删除后 GET /me 返回空")

    # 重复删除应返回 404
    r = requests.delete(
        f"{BASE_URL}/api/admin/questionnaire-entries/{user_id}",
        headers=ADMIN_HEADERS,
    )
    ok &= _log(r.status_code == 404, f"重复删除返回 404（实际 {r.status_code}）")

    return ok


# ─────────────────────────────────────────────────────────────────
# Scenario 7: 分数范围检验（0分或8分应被拒绝）
# ─────────────────────────────────────────────────────────────────
def scenario_invalid_score_rejected() -> bool:
    print("\n── Scenario 7: 无效分数（超出 1-7 范围）被拒绝 ──")
    setup = _create_three_member_group()
    user = setup["members"][0]
    headers = _auth(user["token"])

    bad_responses = {f"q{i}": 1 for i in range(1, 16)}
    bad_responses["q1"] = 8  # 超出范围

    r = requests.post(
        f"{BASE_URL}/api/questionnaire/srcc",
        headers=headers,
        json={"responses": bad_responses},
    )
    return _log(r.status_code == 422, f"分数=8 被拒绝（期望 422，实际 {r.status_code}）", r.text)


# ─────────────────────────────────────────────────────────────────
# Scenario 8: 管理员列表过滤（group_id、condition、分页）
# ─────────────────────────────────────────────────────────────────
def scenario_admin_filter_and_pagination() -> bool:
    print("\n── Scenario 8: 管理员列表过滤 + 分页 ──")
    setup_a = _create_three_member_group(condition="glasses")
    setup_b = _create_three_member_group(condition="no_assistance")

    user_a = setup_a["members"][0]
    user_b = setup_b["members"][0]
    group_a_id = setup_a["group_id"]
    group_b_id = setup_b["group_id"]

    # 两组各提交一份 SRCC
    for user in [user_a, user_b]:
        r = requests.post(
            f"{BASE_URL}/api/questionnaire/srcc",
            headers=_auth(user["token"]),
            json={"responses": SRCC_FULL},
        )
        r.raise_for_status()

    ok = True

    # 按 group_id 过滤，只应返回 group_a 的记录
    r = requests.get(
        f"{BASE_URL}/api/admin/questionnaire-entries",
        headers=ADMIN_HEADERS,
        params={"group_id": group_a_id},
    )
    if not _log(r.status_code == 200, "按 group_id 过滤返回 200", r.text):
        return False
    body = r.json()
    ids = [e["user_id"] for e in body["items"]]
    ok &= _log(user_a["user_id"] in ids, "group_id 过滤：group_a 的用户出现在结果中")
    ok &= _log(user_b["user_id"] not in ids, "group_id 过滤：group_b 的用户不在结果中")

    # 按 condition 过滤
    r = requests.get(
        f"{BASE_URL}/api/admin/questionnaire-entries",
        headers=ADMIN_HEADERS,
        params={"condition": "no_assistance"},
    )
    if not _log(r.status_code == 200, "按 condition 过滤返回 200", r.text):
        return False
    body = r.json()
    conditions = [e["condition"] for e in body["items"]]
    ok &= _log(all(c == "no_assistance" for c in conditions), "condition 过滤：结果全为 no_assistance")

    # 分页：page_size=1，验证 meta 字段正确
    r = requests.get(
        f"{BASE_URL}/api/admin/questionnaire-entries",
        headers=ADMIN_HEADERS,
        params={"group_id": group_b_id, "page": 1, "page_size": 1},
    )
    if not _log(r.status_code == 200, "分页请求返回 200", r.text):
        return False
    body = r.json()
    ok &= _log(len(body["items"]) == 1, f"page_size=1 时 items 长度为 1（实际 {len(body['items'])}）")
    ok &= _log(body["meta"]["page"] == 1, "meta.page = 1")
    ok &= _log(body["meta"]["page_size"] == 1, "meta.page_size = 1")

    # 不存在的 group_id 应返回空列表
    r = requests.get(
        f"{BASE_URL}/api/admin/questionnaire-entries",
        headers=ADMIN_HEADERS,
        params={"group_id": "nonexistent-group-id"},
    )
    body = r.json()
    ok &= _log(body["items"] == [] and body["meta"]["total"] == 0, "不存在的 group_id 返回空列表 + total=0")

    return ok


# ─────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────
def main() -> None:
    results = [
        scenario_meta(),
        scenario_empty_me(),
        scenario_submit_and_verify(),
        scenario_update_overwrites(),
        scenario_no_group_returns_400(),
        scenario_admin_list_and_delete(),
        scenario_invalid_score_rejected(),
        scenario_admin_filter_and_pagination(),
    ]
    passed = sum(results)
    total = len(results)
    print(f"\n{'🎉' if passed == total else '💥'} {passed}/{total} scenarios passed")
    if not all(results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
