from __future__ import annotations

import uuid
from typing import Any, Dict

import requests

BASE_URL = "http://127.0.0.1:8000"
RUN_ID = uuid.uuid4().hex[:6]

ADMIN_HEADERS = {"X-Admin-Token": "TestAdminKey123"}


def _log(ok: bool, message: str, extra: Any | None = None) -> bool:
    prefix = "✅" if ok else "❌"
    print(f"{prefix} {message}")
    if not ok and extra is not None:
        print("   详情:", extra)
    return ok


# ────────────────────────────────────────────────────────────
# 注册场景
# ────────────────────────────────────────────────────────────

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
        },
    )
    ok = resp.status_code == 400
    return _log(ok, "重复邮箱注册应返回 400 场景", {"status": resp.status_code, "body": resp.json()})


def scenario_register_invalid_email() -> bool:
    ok = True
    for bad_email in ["notanemail", "@nodomain.com", "missing_at_sign", "a@", ""]:
        resp = requests.post(
            f"{BASE_URL}/api/auth/register",
            json={"name": "Test", "email": bad_email, "password": "1234"},
        )
        passed = resp.status_code in (400, 422)
        ok &= _log(passed, f"邮箱格式非法应返回 400/422：email={bad_email!r}", {"status": resp.status_code})
    return ok


def scenario_register_password_wrong_length() -> bool:
    ok = True
    base_email = f"pwlen_{uuid.uuid4().hex[:6]}@example.com"
    for pwd, label in [("123", "3位"), ("12345", "5位"), ("", "空字符串")]:
        resp = requests.post(
            f"{BASE_URL}/api/auth/register",
            json={"name": "Test", "email": base_email, "password": pwd},
        )
        passed = resp.status_code in (400, 422)
        ok &= _log(passed, f"密码长度不合法应返回 400/422：password={pwd!r}({label})", {"status": resp.status_code})
    return ok


def scenario_register_missing_required_fields() -> bool:
    ok = True
    # 缺 name
    resp = requests.post(f"{BASE_URL}/api/auth/register", json={"email": "a@b.com", "password": "1234"})
    ok &= _log(resp.status_code == 422, "缺 name 字段应返回 422", {"status": resp.status_code})
    # 缺 email
    resp = requests.post(f"{BASE_URL}/api/auth/register", json={"name": "Test", "password": "1234"})
    ok &= _log(resp.status_code == 422, "缺 email 字段应返回 422", {"status": resp.status_code})
    # 缺 password
    resp = requests.post(f"{BASE_URL}/api/auth/register", json={"name": "Test", "email": "a@b.com"})
    ok &= _log(resp.status_code == 422, "缺 password 字段应返回 422", {"status": resp.status_code})
    return ok


def scenario_register_creates_default_group(ctx: Dict[str, Any]) -> bool:
    """注册后应自动创建 is_default=true 的群组，名称为 '{name} 的群组'。"""
    user_id = ctx.get("user_id")
    if not user_id:
        return _log(False, "register_creates_default_group：ctx 中无 user_id", ctx)

    r = requests.get(
        f"{BASE_URL}/api/admin/users/{user_id}",
        headers=ADMIN_HEADERS,
    )
    if r.status_code != 200:
        return _log(False, "查询用户详情失败", {"status": r.status_code, "body": r.text})

    data = r.json()
    group_ids = data.get("group_ids", [])
    group_names = data.get("group_names", [])

    if not group_ids:
        return _log(False, "注册后用户应有默认群组，但 group_ids 为空", data)

    expected_name = f"{ctx['name']} 的群组"
    ok = expected_name in group_names
    return _log(ok, f"注册自动创建默认群组场景（期望群组名：{expected_name!r}）", data)


def scenario_register_creates_owner_membership(ctx: Dict[str, Any]) -> bool:
    """注册后应自动创建 role=owner, status=active 的成员关系。"""
    user_id = ctx.get("user_id")
    if not user_id:
        return _log(False, "register_creates_owner_membership：ctx 中无 user_id", ctx)

    r = requests.get(
        f"{BASE_URL}/api/admin/memberships",
        params={"user_id": user_id, "page_size": 10},
        headers=ADMIN_HEADERS,
    )
    if r.status_code != 200:
        return _log(False, "查询成员关系失败", {"status": r.status_code, "body": r.text})

    items = r.json().get("items", [])
    owner_active = [m for m in items if m.get("role") == "owner" and m.get("status") == "active"]
    ok = len(owner_active) >= 1
    return _log(ok, "注册自动创建 owner 成员关系场景", {"memberships": items})


# ────────────────────────────────────────────────────────────
# 登录场景
# ────────────────────────────────────────────────────────────

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
        json={"email": ctx["email"], "password": "0000"},
    )
    ok = resp.status_code == 401
    return _log(ok, "登录密码错误应返回 401 场景", {"status": resp.status_code, "body": resp.json()})


def scenario_login_nonexistent_email() -> bool:
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": f"no_{uuid.uuid4().hex[:6]}@example.com", "password": "1234"},
    )
    ok = resp.status_code == 401
    return _log(ok, "登录邮箱不存在应返回 401 场景", {"status": resp.status_code})


def scenario_login_returns_password_needs_reset(ctx: Dict[str, Any]) -> bool:
    """先 admin 标记重置，再登录，验证返回的 user.password_needs_reset=true。"""
    user_id = ctx.get("user_id")
    if not user_id:
        return _log(False, "login_returns_password_needs_reset：ctx 中无 user_id")

    r = requests.post(
        f"{BASE_URL}/api/admin/users/{user_id}/mark-password-reset",
        headers=ADMIN_HEADERS,
    )
    if r.status_code != 200:
        return _log(False, "admin mark-password-reset 失败", {"status": r.status_code, "body": r.text})

    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ctx["email"], "password": ctx["password"]},
    )
    if resp.status_code != 200:
        return _log(False, "标记后登录失败（期望 200）", resp.json())

    data = resp.json()
    ok = data.get("user", {}).get("password_needs_reset") is True
    ctx["access_token"] = data.get("access_token", ctx.get("access_token"))
    return _log(ok, "登录返回 password_needs_reset=true 场景", data)


# ────────────────────────────────────────────────────────────
# /me 场景
# ────────────────────────────────────────────────────────────

def scenario_me_with_valid_token(ctx: Dict[str, Any]) -> bool:
    resp = requests.get(
        f"{BASE_URL}/api/auth/me",
        headers={"Authorization": f"Bearer {ctx['access_token']}"},
    )
    if resp.status_code != 200:
        return _log(False, "带合法 token 调 /me 失败（期望 200）", resp.json())
    data = resp.json()
    ok = data.get("email") == ctx["email"]
    return _log(ok, "获取当前用户信息场景", data)


def scenario_me_without_token() -> bool:
    resp = requests.get(f"{BASE_URL}/api/auth/me")
    ok = resp.status_code in (401, 403)
    return _log(ok, "未带 token 调 /me 应返回 401/403 场景", {"status": resp.status_code})


def scenario_me_with_invalid_token() -> bool:
    resp = requests.get(
        f"{BASE_URL}/api/auth/me",
        headers={"Authorization": "Bearer invalid.token.value"},
    )
    ok = resp.status_code == 401
    return _log(ok, "非法 token 调 /me 应返回 401 场景", {"status": resp.status_code})


# ────────────────────────────────────────────────────────────
# 修改密码场景
# ────────────────────────────────────────────────────────────

def scenario_change_password_wrong_old_password(ctx: Dict[str, Any]) -> bool:
    resp = requests.post(
        f"{BASE_URL}/api/auth/change-password",
        headers={"Authorization": f"Bearer {ctx['access_token']}"},
        json={"old_password": "0000", "new_password": "5678"},
    )
    ok = resp.status_code == 401
    return _log(ok, "旧密码错误修改密码应返回 401 场景", {"status": resp.status_code})


def scenario_change_password_wrong_length(ctx: Dict[str, Any]) -> bool:
    ok = True
    for pwd, label in [("123", "3位"), ("12345", "5位")]:
        resp = requests.post(
            f"{BASE_URL}/api/auth/change-password",
            headers={"Authorization": f"Bearer {ctx['access_token']}"},
            json={"old_password": ctx["password"], "new_password": pwd},
        )
        passed = resp.status_code == 400
        ok &= _log(passed, f"新密码长度非法应返回 400：new_password={pwd!r}({label})", {"status": resp.status_code})
    return ok


def scenario_change_password_clears_reset_flag(ctx: Dict[str, Any]) -> bool:
    """修改密码后 password_needs_reset 应自动变为 false。"""
    # 当前 password_needs_reset 应为 true（前面 scenario_login_returns_password_needs_reset 已标记）
    new_password = "5678"
    resp = requests.post(
        f"{BASE_URL}/api/auth/change-password",
        headers={"Authorization": f"Bearer {ctx['access_token']}"},
        json={"old_password": ctx["password"], "new_password": new_password},
    )
    if resp.status_code != 200:
        return _log(False, "修改密码失败（期望 200）", resp.json())

    data = resp.json()
    ok = data.get("password_needs_reset") is False
    ok &= _log(ok, "修改密码后 password_needs_reset 应清零场景", data)

    # 更新 ctx
    ctx["password"] = new_password
    ctx["access_token"] = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ctx["email"], "password": new_password},
    ).json().get("access_token", ctx["access_token"])
    return ok


def scenario_change_password_old_login_fails(ctx: Dict[str, Any]) -> bool:
    """改完密码后，用旧密码应无法登录。"""
    old_password = "1234"  # 最初注册密码
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ctx["email"], "password": old_password},
    )
    ok = resp.status_code == 401
    return _log(ok, "改密码后旧密码登录应返回 401 场景", {"status": resp.status_code})


def scenario_change_password_new_login_succeeds(ctx: Dict[str, Any]) -> bool:
    """改完密码后，用新密码可以正常登录。"""
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ctx["email"], "password": ctx["password"]},
    )
    if resp.status_code != 200:
        return _log(False, "改密码后新密码登录失败（期望 200）", resp.json())
    ctx["access_token"] = resp.json().get("access_token", ctx["access_token"])
    return _log(True, "改密码后新密码登录成功场景")


# ────────────────────────────────────────────────────────────
# 总入口
# ────────────────────────────────────────────────────────────

def run_all() -> bool:
    print("=== 开始 Auth 注册/登录流程测试 ===\n")

    ctx: Dict[str, Any] = {
        "name": f"James Lin {RUN_ID}",
        "email": f"test_{uuid.uuid4().hex[:8]}@example.com",
        "password": "1234",
        "device_token": f"device-auth-{uuid.uuid4().hex[:8]}",
    }

    ok = True

    print("-- 注册 --")
    ok &= scenario_register_invalid_email()
    ok &= scenario_register_password_wrong_length()
    ok &= scenario_register_missing_required_fields()
    ok &= scenario_register_success(ctx)
    ok &= scenario_register_duplicate_email(ctx)
    ok &= scenario_register_creates_default_group(ctx)
    ok &= scenario_register_creates_owner_membership(ctx)

    print("\n-- 登录 --")
    ok &= scenario_login_success(ctx)
    ok &= scenario_login_wrong_password(ctx)
    ok &= scenario_login_nonexistent_email()

    print("\n-- /me --")
    ok &= scenario_me_with_valid_token(ctx)
    ok &= scenario_me_without_token()
    ok &= scenario_me_with_invalid_token()

    print("\n-- 修改密码 --")
    ok &= scenario_change_password_wrong_old_password(ctx)
    ok &= scenario_change_password_wrong_length(ctx)
    ok &= scenario_login_returns_password_needs_reset(ctx)   # 标记重置，验证登录返回标记
    ok &= scenario_change_password_clears_reset_flag(ctx)    # 改密码，验证标记清零
    ok &= scenario_change_password_old_login_fails(ctx)
    ok &= scenario_change_password_new_login_succeeds(ctx)

    print(f"\n=== 测试结果: {'全部通过 ✅' if ok else '有失败 ❌'} ===")
    return ok


if __name__ == "__main__":
    import sys
    sys.exit(0 if run_all() else 1)
