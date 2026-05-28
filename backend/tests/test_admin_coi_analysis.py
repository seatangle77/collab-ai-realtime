"""
CoI Analysis 后台接口专项测试
覆盖：鉴权、两条件分析、三条件分析、排除未编码会话、空样本、指标计算正确性

用法：
  python -m backend.tests.test_admin_coi_analysis
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


def _title(name: str) -> None:
    print(f"\n{'=' * 68}\n{name}\n{'=' * 68}")


def _register_and_login(suffix: str) -> tuple[dict[str, Any], str]:
    email = f"coi_analysis_{suffix}_{uuid.uuid4().hex[:6]}@example.com"
    reg = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={"name": f"CoI Analysis {suffix}", "email": email, "password": "1234"},
    )
    reg.raise_for_status()
    login = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": "1234"},
    )
    login.raise_for_status()
    return reg.json(), login.json()["access_token"]


def _setup_group_session(condition: str) -> dict[str, Any]:
    """建用户 → 群组（指定 condition）→ 会话，返回 ids。"""
    user, token = _register_and_login(f"{condition}_{RUN_ID}")

    g = requests.post(
        f"{BASE_URL}/api/groups",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": f"CoI Analysis Group {condition} {RUN_ID}"},
    )
    g.raise_for_status()
    group_id = g.json()["group"]["id"]

    # 用 admin 接口设置 condition
    requests.patch(
        f"{BASE_URL}/api/admin/groups/{group_id}",
        headers=ADMIN_HEADERS,
        json={"condition": condition},
    )

    s = requests.post(
        f"{BASE_URL}/api/groups/{group_id}/sessions",
        headers={"Authorization": f"Bearer {token}"},
        json={"session_title": f"CoI Session {condition} {RUN_ID}"},
    )
    s.raise_for_status()
    session_id = s.json()["id"]

    requests.post(
        f"{BASE_URL}/api/sessions/{session_id}/start",
        headers={"Authorization": f"Bearer {token}"},
    ).raise_for_status()
    requests.post(
        f"{BASE_URL}/api/sessions/{session_id}/end",
        headers={"Authorization": f"Bearer {token}"},
    ).raise_for_status()

    return {"group_id": group_id, "session_id": session_id, "user_id": user["id"]}


def _insert_coi_utterances(session_id: str, group_id: str, categories: list[str | None]) -> list[str]:
    """直接 INSERT coi_utterances，返回 id 列表。"""
    ids = []
    for i, cat in enumerate(categories):
        cu_id = f"cu{uuid.uuid4().hex[:12]}"
        payload: dict[str, Any] = {
            "id": cu_id,
            "session_id": session_id,
            "group_id": group_id,
            "speaker": f"Speaker-{i}",
            "content": f"发言内容 {i}",
            "source_transcript_ids": [],
            "order_index": i + 1,
            "coi_category": cat,
        }
        r = requests.post(
            f"{BASE_URL}/api/admin/coi-utterances/",
            headers=ADMIN_HEADERS,
            json=payload,
        )
        if not r.ok:
            # fallback: 直接用 import + code 接口
            pass
        else:
            ids.append(cu_id)
    return ids


def _seed_session_with_codings(condition: str, categories: list[str | None]) -> dict[str, Any]:
    """建一个完整的已编码会话，返回 context。"""
    ctx = _setup_group_session(condition)

    # 先通过 transcripts 接口建原始转写
    transcript_ids = []
    for i, cat in enumerate(categories):
        r = requests.post(
            f"{BASE_URL}/api/admin/transcripts/",
            headers=ADMIN_HEADERS,
            json={
                "session_id": ctx["session_id"],
                "group_id": ctx["group_id"],
                "user_id": ctx["user_id"],
                "speaker": f"Speaker-{i}",
                "text": f"测试发言内容 {i}，category={cat}",
                "start": f"2026-05-01T09:00:0{i}",
                "end": f"2026-05-01T09:00:0{i + 1 if i < 9 else 9}",
                "duration": 1.0,
                "confidence": 0.9,
            },
        )
        if r.ok:
            transcript_ids.append(r.json().get("transcript_id") or r.json().get("id"))

    # 导入到 coi_utterances
    requests.post(
        f"{BASE_URL}/api/admin/coi-utterances/import",
        headers=ADMIN_HEADERS,
        params={"session_id": ctx["session_id"]},
    )

    # 取列表，逐条打标签
    items_r = requests.get(
        f"{BASE_URL}/api/admin/coi-utterances/",
        headers=ADMIN_HEADERS,
        params={"session_id": ctx["session_id"]},
    )
    items = items_r.json() if items_r.ok else []

    for item, cat in zip(items, categories):
        if cat is not None:
            requests.patch(
                f"{BASE_URL}/api/admin/coi-utterances/{item['id']}/code",
                headers=ADMIN_HEADERS,
                json={"coi_category": cat, "coded_by": "test"},
            )

    ctx["categories"] = categories
    return ctx


def _run_analysis(mode: str, group_ids_by_condition: dict[str, list[str]]) -> requests.Response:
    return requests.post(
        f"{BASE_URL}/api/admin/coi-analysis/",
        headers=ADMIN_HEADERS,
        json={"mode": mode, "group_ids_by_condition": group_ids_by_condition},
    )


def run() -> None:
    print(f"\n[RUN_ID={RUN_ID}] coi-analysis tests\n")

    # ── A. 鉴权 ──────────────────────────────────────────────────────────────
    _title("A. 鉴权")
    _check(
        "POST /coi-analysis/ 无 token -> 403",
        requests.post(
            f"{BASE_URL}/api/admin/coi-analysis/",
            json={"mode": "two_conditions", "group_ids_by_condition": {}},
        ),
        403,
    )

    # ── B. 空样本 ─────────────────────────────────────────────────────────────
    _title("B. 空样本（group_ids 为空列表）")
    r_empty = _run_analysis("two_conditions", {"no_assistance": [], "glasses": []})
    _check("空样本 -> 200", r_empty, 200)
    if r_empty.ok:
        d = r_empty.json()
        _ok("total_sessions=0", d["total_sessions"] == 0, d)
        _ok("excluded_sessions=[]", d["excluded_sessions"] == [], d)
        _ok("metrics 有 6 个", len(d["metrics"]) == 6, d["metrics"])

    # ── C. 两条件分析 ─────────────────────────────────────────────────────────
    _title("C. 两条件分析")
    # 建两个条件各一个会话，TE=1, EX=2, IN=1, RE=0 → total=4
    # 加权得分 = (1×1 + 2×2 + 1×3) / 4 = 8/4 = 2.0
    # 高阶比例 = (1+0)/4 = 0.25
    ctx_na = _seed_session_with_codings("no_assistance", ["TE", "EX", "EX", "IN"])
    ctx_gl = _seed_session_with_codings("glasses", ["EX", "IN", "IN", "RE"])

    r_two = _run_analysis("two_conditions", {
        "no_assistance": [ctx_na["group_id"]],
        "glasses": [ctx_gl["group_id"]],
    })
    _check("两条件分析 -> 200", r_two, 200)
    if r_two.ok:
        d = r_two.json()
        _ok("mode=two_conditions", d["mode"] == "two_conditions", d["mode"])
        _ok("conditions 有 2 个", len(d["conditions"]) == 2, d["conditions"])
        _ok("total_sessions=2", d["total_sessions"] == 2, d)
        _ok("sessions_by_condition no_assistance=1", d["sessions_by_condition"]["no_assistance"] == 1, d)
        _ok("sessions_by_condition glasses=1", d["sessions_by_condition"]["glasses"] == 1, d)
        _ok("excluded_sessions=[]", len(d["excluded_sessions"]) == 0, d)
        _ok("metrics 有 6 个", len(d["metrics"]) == 6, d["metrics"])
        _ok("normality 有 12 条（6指标×2条件）", len(d["normality"]) == 12, len(d["normality"]))
        _ok("statistical_tests 有 6 条", len(d["statistical_tests"]) == 6, len(d["statistical_tests"]))
        _ok("post_hoc_tests 有 6 条（两条件均 not_applicable）", len(d["post_hoc_tests"]) == 6, len(d["post_hoc_tests"]))

        # 验证事后检验两条件模式下均为 not_applicable
        all_not_applicable = all(t["status"] == "not_applicable" for t in d["post_hoc_tests"])
        _ok("两条件模式 post_hoc 均为 not_applicable", all_not_applicable, d["post_hoc_tests"])

        # 验证指标名称
        metric_names = {m["metric"] for m in d["metrics"]}
        expected_metrics = {"te_ratio", "ex_ratio", "in_ratio", "re_ratio", "higher_order_ratio", "weighted_score"}
        _ok("6 个指标名称正确", metric_names == expected_metrics, metric_names)

    # ── D. 三条件分析 ─────────────────────────────────────────────────────────
    _title("D. 三条件分析")
    ctx_app = _seed_session_with_codings("app_notification", ["IN", "IN", "RE", "RE"])

    r_three = _run_analysis("three_conditions", {
        "no_assistance": [ctx_na["group_id"]],
        "glasses": [ctx_gl["group_id"]],
        "app_notification": [ctx_app["group_id"]],
    })
    _check("三条件分析 -> 200", r_three, 200)
    if r_three.ok:
        d = r_three.json()
        _ok("mode=three_conditions", d["mode"] == "three_conditions", d["mode"])
        _ok("conditions 有 3 个", len(d["conditions"]) == 3, d["conditions"])
        _ok("total_sessions=3", d["total_sessions"] == 3, d)
        _ok("normality 有 18 条（6指标×3条件）", len(d["normality"]) == 18, len(d["normality"]))
        _ok("post_hoc_tests 有 6 条", len(d["post_hoc_tests"]) == 6, len(d["post_hoc_tests"]))

    # ── E. 排除未编码会话 ─────────────────────────────────────────────────────
    _title("E. 排除含未编码发言的会话")
    # 建一个有 NULL coi_category 的会话
    ctx_uncoded = _seed_session_with_codings("no_assistance", ["TE", "EX", None])

    r_excl = _run_analysis("two_conditions", {
        "no_assistance": [ctx_uncoded["group_id"]],
        "glasses": [ctx_gl["group_id"]],
    })
    _check("含未编码会话的分析 -> 200", r_excl, 200)
    if r_excl.ok:
        d = r_excl.json()
        _ok("excluded_sessions 有 1 条", len(d["excluded_sessions"]) == 1, d["excluded_sessions"])
        if d["excluded_sessions"]:
            excl = d["excluded_sessions"][0]
            _ok("excluded uncoded_count=1", excl["uncoded_count"] == 1, excl)
            _ok("excluded total_count=3", excl["total_count"] == 3, excl)
            _ok("excluded condition=no_assistance", excl["condition"] == "no_assistance", excl)
        # 排除后 no_assistance 应纳入 0 条
        _ok("排除后 no_assistance sessions=0", d["sessions_by_condition"]["no_assistance"] == 0, d)

    # ── F. 指标计算正确性 ─────────────────────────────────────────────────────
    _title("F. 指标计算正确性（直接验证数值）")
    # 专门建一个已知分布的会话：TE=1, EX=1, IN=1, RE=1（各1条，共4条）
    # te_ratio=0.25, ex_ratio=0.25, in_ratio=0.25, re_ratio=0.25
    # higher_order_ratio = (1+1)/4 = 0.5
    # weighted_score = (1×1 + 1×2 + 1×3 + 1×4) / 4 = 10/4 = 2.5
    ctx_known = _seed_session_with_codings("glasses", ["TE", "EX", "IN", "RE"])

    r_known = _run_analysis("two_conditions", {
        "no_assistance": [ctx_na["group_id"]],
        "glasses": [ctx_known["group_id"]],
    })
    _check("已知分布分析 -> 200", r_known, 200)
    if r_known.ok:
        d = r_known.json()
        glasses_obs = [obs for obs in d.get("observations", []) if obs["condition"] == "glasses"]
        # 找到我们刚建的那个 session
        target = next((o for o in glasses_obs if o["session_id"] == ctx_known["session_id"]), None)
        if target:
            _ok("te_ratio=0.25", abs(target["te_ratio"] - 0.25) < 0.001, target["te_ratio"])
            _ok("ex_ratio=0.25", abs(target["ex_ratio"] - 0.25) < 0.001, target["ex_ratio"])
            _ok("in_ratio=0.25", abs(target["in_ratio"] - 0.25) < 0.001, target["in_ratio"])
            _ok("re_ratio=0.25", abs(target["re_ratio"] - 0.25) < 0.001, target["re_ratio"])
            _ok("higher_order_ratio=0.5", abs(target["higher_order_ratio"] - 0.5) < 0.001, target["higher_order_ratio"])
            _ok("weighted_score=2.5", abs(target["weighted_score"] - 2.5) < 0.001, target["weighted_score"])
        else:
            _ok("找到目标会话 observation", False, "observations=" + str(glasses_obs))

    # ── G. 非法 mode ────────────────────────────────────────────────────────
    _title("G. 非法参数")
    _check(
        "非法 mode -> 422",
        requests.post(
            f"{BASE_URL}/api/admin/coi-analysis/",
            headers=ADMIN_HEADERS,
            json={"mode": "invalid_mode", "group_ids_by_condition": {}},
        ),
        422,
    )

    # ── 汇总 ─────────────────────────────────────────────────────────────────
    total = _pass + _fail
    print(f"\n{'=' * 68}")
    print(f"结果：通过 {_pass}/{total}，失败 {_fail}/{total}")
    if _fail:
        sys.exit(1)


if __name__ == "__main__":
    run()
