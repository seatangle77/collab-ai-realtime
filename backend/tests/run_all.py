#!/usr/bin/env python3
"""
一键运行后端所有测试脚本。

用法（需在 backend 目录下，且已启动服务）:
  python tests/run_all.py

或从项目根目录:
  cd backend && python tests/run_all.py
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys

# 与各 test_*.py 中的 BASE_URL 一致
TEST_HOST = "127.0.0.1"
TEST_PORT = 8000

# 当前脚本所在目录
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
# 测试脚本列表（按执行顺序）
TEST_SCRIPTS = [
    "test_auth_flows.py",
    "test_group_flows.py",
    "test_sessions_flows.py",
    "test_app_sessions.py",
    "test_voice_profiles.py",
    "test_admin_voice_profiles.py",
    "test_admin_users.py",
    "test_admin_groups.py",
    "test_admin_memberships.py",
    "test_admin_chat_sessions.py",
]


def is_server_up() -> bool:
    """检测后端是否在 TEST_HOST:TEST_PORT 监听。"""
    try:
        with socket.create_connection((TEST_HOST, TEST_PORT), timeout=2):
            return True
    except (socket.error, OSError):
        return False


def main() -> int:
    backend_dir = os.path.dirname(TESTS_DIR)
    if os.getcwd() != backend_dir:
        os.chdir(backend_dir)

    if not is_server_up():
        print(
            f"无法连接到 {TEST_HOST}:{TEST_PORT}，请先启动后端服务。\n"
            "例如在 backend 目录下执行:\n  uvicorn app.main:app --reload\n"
            "或:\n  python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
        )
        return 1

    failed: list[str] = []
    for name in TEST_SCRIPTS:
        path = os.path.join(TESTS_DIR, name)
        if not os.path.isfile(path):
            print(f"跳过（不存在）: {name}")
            continue
        print(f"\n{'='*60}\n运行: {name}\n{'='*60}")
        ret = subprocess.run(
            [sys.executable, path],
            cwd=backend_dir,
        )
        if ret.returncode != 0:
            failed.append(name)

    print("\n" + "=" * 60)
    if failed:
        print(f"失败: {', '.join(failed)}")
        return 1
    print("全部测试通过 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
