from __future__ import annotations

import json
import sys
import time
import uuid
from typing import Any, Dict, Tuple

import requests
import websocket

BASE_URL = "http://127.0.0.1:8000"
WS_BASE = "ws://127.0.0.1:8000"
RUN_ID = uuid.uuid4().hex[:6]
WS_TIMEOUT = 8


def _log(ok: bool, message: str, extra: Any | None = None) -> bool:
    print(f"{'✅' if ok else '❌'} {message}")
    if not ok and extra is not None:
        print("   详情:", extra)
    return ok


def _auth(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def register_and_login(name: str, suffix: str) -> Tuple[str, str]:
    email = f"hostctl_{suffix}_{uuid.uuid4().hex[:6]}@example.com"
    password = "1234"
    reg = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={
            "name": name,
            "email": email,
            "password": password,
            "device_token": f"dev-hostctl-{suffix}-{uuid.uuid4().hex[:8]}",
        },
    )
    reg.raise_for_status()
    user_id = reg.json()["id"]

    login = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
    )
    login.raise_for_status()
    token = login.json()["access_token"]
    return token, user_id


def _create_group(token: str) -> str:
    r = requests.post(
        f"{BASE_URL}/api/groups",
        json={"name": f"HostControl Group {RUN_ID}"},
        headers=_auth(token),
    )
    r.raise_for_status()
    return r.json()["group"]["id"]


def _join_group(token: str, group_id: str) -> None:
    r = requests.post(
        f"{BASE_URL}/api/groups/{group_id}/join",
        headers=_auth(token),
    )
    r.raise_for_status()


def _create_session(token: str, group_id: str, title: str) -> str:
    r = requests.post(
        f"{BASE_URL}/api/groups/{group_id}/sessions",
        json={"session_title": title},
        headers=_auth(token),
    )
    r.raise_for_status()
    return r.json()["id"]


def _start_session(token: str, session_id: str) -> requests.Response:
    return requests.post(
        f"{BASE_URL}/api/sessions/{session_id}/start",
        headers=_auth(token),
    )


def _end_session(token: str, session_id: str) -> requests.Response:
    return requests.post(
        f"{BASE_URL}/api/sessions/{session_id}/end",
        headers=_auth(token),
    )


def _session_status(token: str, group_id: str, session_id: str) -> str | None:
    r = requests.get(
        f"{BASE_URL}/api/groups/{group_id}/sessions",
        params={"include_ended": "true"},
        headers=_auth(token),
    )
    if r.status_code != 200:
        return None
    for s in r.json():
        if s.get("id") == session_id:
            return s.get("status")
    return None


def _ws_connect(session_id: str, token: str) -> websocket.WebSocket:
    ws = websocket.create_connection(f"{WS_BASE}/ws/sessions/{session_id}?token={token}", timeout=WS_TIMEOUT)
    return ws


def _recv_json(ws: websocket.WebSocket) -> dict[str, Any]:
    return json.loads(ws.recv())


def setup_ctx(ctx: Dict[str, Any]) -> bool:
    try:
        ctx["host_token"], ctx["host_user_id"] = register_and_login(f"Host {RUN_ID}", "host")
        ctx["member_token"], ctx["member_user_id"] = register_and_login(f"Member {RUN_ID}", "member")
        ctx["group_id"] = _create_group(ctx["host_token"])
        _join_group(ctx["member_token"], ctx["group_id"])
        return _log(True, "setup: host/member + group 准备完成")
    except Exception as e:
        return _log(False, "setup 失败", str(e))


def case_host_only_start_end(ctx: Dict[str, Any]) -> bool:
    ok = True
    session_id = _create_session(ctx["host_token"], ctx["group_id"], f"HostOnly {RUN_ID}")

    r = _start_session(ctx["member_token"], session_id)
    ok &= _log(r.status_code == 403, "成员发起会话返回 403", {"status": r.status_code, "body": r.text})

    r = _start_session(ctx["host_token"], session_id)
    ok &= _log(r.status_code == 200, "发起人发起会话成功", {"status": r.status_code, "body": r.text})

    r = _end_session(ctx["member_token"], session_id)
    ok &= _log(r.status_code == 403, "成员结束会话返回 403", {"status": r.status_code, "body": r.text})

    r = _end_session(ctx["host_token"], session_id)
    ok &= _log(r.status_code == 200, "发起人结束会话成功", {"status": r.status_code, "body": r.text})
    return ok


def case_end_broadcast(ctx: Dict[str, Any]) -> bool:
    session_id = _create_session(ctx["host_token"], ctx["group_id"], f"Broadcast {RUN_ID}")
    start = _start_session(ctx["host_token"], session_id)
    if start.status_code != 200:
        return _log(False, "广播用例准备失败：无法发起会话", {"status": start.status_code, "body": start.text})

    ws_host = ws_member = None
    try:
        ws_host = _ws_connect(session_id, ctx["host_token"])
        ws_member = _ws_connect(session_id, ctx["member_token"])
        host_connected = _recv_json(ws_host)
        member_connected = _recv_json(ws_member)
        if host_connected.get("type") != "connected" or member_connected.get("type") != "connected":
            return _log(False, "广播用例准备失败：WS 未正常连接", {"host": host_connected, "member": member_connected})

        end_res = _end_session(ctx["host_token"], session_id)
        if end_res.status_code != 200:
            return _log(False, "发起人结束会话失败", {"status": end_res.status_code, "body": end_res.text})

        ws_host.settimeout(WS_TIMEOUT)
        ws_member.settimeout(WS_TIMEOUT)
        host_msg = _recv_json(ws_host)
        member_msg = _recv_json(ws_member)
        ok = True
        ok &= host_msg.get("type") == "session_ended"
        ok &= host_msg.get("data", {}).get("reason") == "host_ended"
        ok &= member_msg.get("type") == "session_ended"
        ok &= member_msg.get("data", {}).get("reason") == "host_ended"
        ok &= _session_status(ctx["host_token"], ctx["group_id"], session_id) == "ended"
        return _log(ok, "发起人结束后 host/member 均收到 session_ended 且 DB=ended", {"host": host_msg, "member": member_msg})
    except Exception as e:
        return _log(False, "广播用例异常", str(e))
    finally:
        for ws in [ws_host, ws_member]:
            if ws is not None:
                try:
                    ws.close()
                except Exception:
                    pass
        time.sleep(0.2)


def run_all() -> bool:
    print("=== 开始 host-only + broadcast 测试 ===")
    ctx: Dict[str, Any] = {}
    if not setup_ctx(ctx):
        return False
    ok = True
    ok &= case_host_only_start_end(ctx)
    ok &= case_end_broadcast(ctx)
    print(f"\n=== 结果: {'全部通过 ✅' if ok else '有失败 ❌'} ===")
    return ok


if __name__ == "__main__":
    sys.exit(0 if run_all() else 1)
