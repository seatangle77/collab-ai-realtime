"""
Live integration test for task score entry save/read APIs.

Prerequisites:
- backend is running at BASE_URL (default: http://127.0.0.1:8000)
- task_score_entries table exists

Usage:
  python -m backend.tests.test_task_score_entries
"""
from __future__ import annotations

from pathlib import Path
import sys
import uuid
from typing import Any

import requests


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.analysis.task_score_config import TASK_SCORE_CONFIG


BASE_URL = "http://127.0.0.1:8000"
ADMIN_HEADERS = {"X-Admin-Token": "TestAdminKey123"}
RUN_ID = uuid.uuid4().hex[:6]


def _log(ok: bool, message: str, extra: Any | None = None) -> bool:
    print(f"{'✅' if ok else '❌'} {message}")
    if not ok and extra is not None:
        print("   详情:", extra)
    return ok


def _expert_order(task_id: str) -> list[str]:
    return [
        item["key"]
        for item in sorted(TASK_SCORE_CONFIG[task_id]["items"], key=lambda item: item["expert_rank"])
    ]


def _register_and_login(label: str) -> dict[str, str]:
    email = f"task_score_{label}_{RUN_ID}_{uuid.uuid4().hex[:6]}@example.com"
    password = "1234"
    r = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={"name": f"TaskScore {label}", "email": email, "password": password},
    )
    r.raise_for_status()
    user = r.json()

    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    return {"user_id": user["id"], "token": r.json()["access_token"], "name": user["name"]}


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_three_member_group() -> dict[str, Any]:
    leader = _register_and_login("leader")
    member1 = _register_and_login("member1")
    member2 = _register_and_login("member2")

    r = requests.post(
        f"{BASE_URL}/api/groups",
        headers=_auth(leader["token"]),
        json={"name": f"TaskScore API Group {RUN_ID}"},
    )
    r.raise_for_status()
    group_id = r.json()["group"]["id"]

    for member in [member1, member2]:
        r = requests.post(f"{BASE_URL}/api/groups/{group_id}/join", headers=_auth(member["token"]))
        r.raise_for_status()

    return {"group_id": group_id, "members": [leader, member1, member2]}


def scenario_save_and_read_task_score_entry() -> bool:
    setup = _create_three_member_group()
    group_id = setup["group_id"]
    members = setup["members"]
    task_id = "moon_survival"
    expert = _expert_order(task_id)
    reversed_order = list(reversed(expert))

    payload = {
        "group_id": group_id,
        "task_id": task_id,
        "answers": {
            "individual": [
                {"participant_id": members[0]["user_id"], "participant_name": members[0]["name"], "ordered_items": expert},
                {"participant_id": members[1]["user_id"], "participant_name": members[1]["name"], "ordered_items": reversed_order},
                {"participant_id": members[2]["user_id"], "participant_name": members[2]["name"], "ordered_items": expert},
            ],
            "group_final": {"ordered_items": expert},
        },
    }

    r = requests.post(f"{BASE_URL}/api/admin/task-score-entries/", headers=ADMIN_HEADERS, json=payload)
    if r.status_code != 200:
        return _log(False, "保存任务分数失败（期望 200）", {"status": r.status_code, "body": r.text})

    saved = r.json()
    result = saved["result_json"]
    ok = True
    ok &= saved["group_id"] == group_id
    ok &= saved["task_id"] == task_id
    ok &= saved["condition"] in {"no_assistance", "glasses", "app_notification"}
    ok &= saved["answers_json"]["group_final"]["ordered_items"] == expert
    ok &= result["gs"] == 0
    ok &= result["best_is"] == 0
    ok &= result["strong_synergy"] == 0
    ok &= len(result["individual_scores"]) == 3
    if not _log(ok, "POST 保存并计算任务分数", saved if not ok else None):
        return False

    r = requests.get(
        f"{BASE_URL}/api/admin/task-score-entries/",
        headers=ADMIN_HEADERS,
        params={"group_id": group_id, "task_id": task_id},
    )
    if r.status_code != 200:
        return _log(False, "读取任务分数失败（期望 200）", {"status": r.status_code, "body": r.text})
    loaded = r.json()
    ok = loaded["id"] == saved["id"] and loaded["result_json"] == saved["result_json"]
    return _log(ok, "GET 读取已保存任务分数", loaded if not ok else None)


def scenario_reject_duplicate_items() -> bool:
    setup = _create_three_member_group()
    group_id = setup["group_id"]
    members = setup["members"]
    task_id = "winter_survival"
    expert = _expert_order(task_id)
    bad = [expert[0], *expert[:-1]]
    payload = {
        "group_id": group_id,
        "task_id": task_id,
        "answers": {
            "individual": [
                {"participant_id": members[0]["user_id"], "ordered_items": bad},
                {"participant_id": members[1]["user_id"], "ordered_items": expert},
                {"participant_id": members[2]["user_id"], "ordered_items": expert},
            ],
            "group_final": {"ordered_items": expert},
        },
    }

    r = requests.post(f"{BASE_URL}/api/admin/task-score-entries/", headers=ADMIN_HEADERS, json=payload)
    return _log(r.status_code == 422, "重复物品会被接口拒绝（期望 422）", {"status": r.status_code, "body": r.text})


def main() -> None:
    checks = [
        scenario_save_and_read_task_score_entry(),
        scenario_reject_duplicate_items(),
    ]
    if not all(checks):
        raise SystemExit(1)
    print("🎉 task_score_entries live integration tests passed")


if __name__ == "__main__":
    main()

