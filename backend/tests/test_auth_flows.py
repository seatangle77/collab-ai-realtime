from __future__ import annotations

import uuid
from typing import Any, Dict

import requests


BASE_URL = "http://127.0.0.1:8000"


def _log(ok: bool, message: str, extra: Any | None = None) -> bool:
    prefix = "✅" if ok else "❌"
    print(f"{prefix} {message}")
    if not ok and extra is not None:
        print("   详情:", extra)
    return ok


def scenario_register_success(ctx: Dict[str, Any]) -> bool:
    resp = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={
            "name": ctx["name"],
            "email": ctx["email"],
            "password": ctx["password"],
            "device_token": ctx["device_token"],
        },
    )
    if resp.status_code != 200:
        return _log(False, "注册失败（期望 200）", resp.json())

    data = resp.json()
    ok = data.get("email") == ctx["email"]
    if ok:
        ctx["user_id"] = data.get("id")
    return _log(ok, "注册成功场景", data)


def scenario_register_duplicate_email(ctx: Dict[str, Any]) -> bool:
    resp = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={
            "name": ctx["name"],
            "email": ctx["email"],
            "password": ctx["password"],
            "device_token": ctx["device_token"],
        },
    )
    if resp.status_code != 400:
        return _log(False, "重复邮箱注册应返回 400", resp.json())
    return _log(True, "重复邮箱注册场景")


def scenario_login_success(ctx: Dict[str, Any]) -> bool:
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ctx["email"], "password": ctx["password"]},
    )
    if resp.status_code != 200:
        return _log(False, "登录失败（期望 200）", resp.json())

    data = resp.json()
    token = data.get("access_token")
    ok = bool(token) and data.get("user", {}).get("email") == ctx["email"]
    if ok:
        ctx["access_token"] = token
    return _log(ok, "登录成功场景", data)


def scenario_login_wrong_password(ctx: Dict[str, Any]) -> bool:
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ctx["email"], "password": ctx["password"] + "_wrong"},
    )
    ok = resp.status_code == 401
    return _log(ok, "登录密码错误场景", resp.json())


def scenario_login_nonexistent_email() -> bool:
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={
            "email": f"nonexistent_{uuid.uuid4().hex[:6]}@example.com",
            "password": "whatever",
        },
    )
    ok = resp.status_code == 401
    return _log(ok, "登录邮箱不存在场景", resp.json())


def scenario_me_with_valid_token(ctx: Dict[str, Any]) -> bool:
    headers = {"Authorization": f"Bearer {ctx['access_token']}"}
    resp = requests.get(f"{BASE_URL}/api/auth/me", headers=headers)
    if resp.status_code != 200:
        return _log(False, "带合法 token 调 /me 失败（期望 200）", resp.json())

    data = resp.json()
    ok = data.get("email") == ctx["email"]
    return _log(ok, "获取当前用户信息场景", data)


def scenario_me_without_token() -> bool:
    resp = requests.get(f"{BASE_URL}/api/auth/me")
    ok = resp.status_code in (401, 403)
    return _log(ok, "未带 token 调 /me 场景", {"status_code": resp.status_code, "body": resp.json()})


def scenario_me_with_invalid_token() -> bool:
    headers = {"Authorization": "Bearer invalid.token.value"}
    resp = requests.get(f"{BASE_URL}/api/auth/me", headers=headers)
    ok = resp.status_code == 401
    return _log(ok, "非法 token 调 /me 场景", {"status_code": resp.status_code, "body": resp.json()})


def run_all() -> bool:
    print("=== 开始 Auth 注册/登录流程测试 ===")

    ctx: Dict[str, Any] = {
        "name": "测试用户",
        "email": f"test_{uuid.uuid4().hex[:8]}@example.com",
        "password": "test_password_123",
        "device_token": "test_device_token",
    }

    ok = True
    ok &= scenario_register_success(ctx)
    ok &= scenario_register_duplicate_email(ctx)
    ok &= scenario_login_success(ctx)
    ok &= scenario_login_wrong_password(ctx)
    ok &= scenario_login_nonexistent_email()
    ok &= scenario_me_with_valid_token(ctx)
    ok &= scenario_me_without_token()
    ok &= scenario_me_with_invalid_token()

    print("\n=== 测试结果: {} ===".format("全部通过 ✅" if ok else "有失败 ❌"))
    return ok


if __name__ == "__main__":
    import sys
    sys.exit(0 if run_all() else 1)

