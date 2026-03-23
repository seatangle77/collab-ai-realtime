"""
AudioService 集成测试

测试用例：
  1. create_audio_service → ffmpeg 进程启动
  2. handle_chunk → 不抛异常（ffmpeg 正常接收 WebM）
  3. ffmpeg 死亡后 handle_chunk 安全丢弃（不崩溃）
  4. destroy_audio_service → get_audio_service 返回 None
  5. 端到端：发送 WebM 音频 → insert_speech_transcript_and_broadcast 被调用
     （需要后端运行 + 真实 WebM 文件）

运行方式（在 backend/ 目录下）：
  python tests/test_audio_service.py

注意：
  - 测试 1-4 需要 ffmpeg 已安装
  - 测试 5 需要后端运行 + tests/audio_samples/test_speech.webm
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

# ── 路径 & 环境变量 ──────────────────────────────────────────────
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

env_path = BACKEND_DIR / ".env.local"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

import numpy as np
from app.audio.audio_service import (
    AudioService,
    create_audio_service,
    destroy_audio_service,
    get_audio_service,
    _services,
)

# ── helpers ──────────────────────────────────────────────────────

PASS = 0
FAIL = 0


def _log(ok: bool, msg: str, extra: Any = None) -> None:
    global PASS, FAIL
    print(f"{'✅' if ok else '❌'} {msg}")
    if not ok and extra is not None:
        print("   详情:", extra)
    if ok:
        PASS += 1
    else:
        FAIL += 1


class _MockRow:
    def __init__(self, data: dict):
        self._data = data

    def __getitem__(self, key):
        return self._data[key]


class _MockDB:
    def __init__(self, rows: list[dict] = None):
        self._rows = rows or []

    async def execute(self, query, params=None):
        return self

    def mappings(self):
        return self

    def all(self):
        return [_MockRow(r) for r in self._rows]


def _make_minimal_webm() -> bytes:
    """
    返回一个极小的合法 WebM 文件头（EBML header）。
    ffmpeg 能解析但不会产生有效音频输出，用于测试连接不崩溃。
    """
    # 最小 WebM EBML 头（来自 Matroska 规范）
    return bytes([
        0x1A, 0x45, 0xDF, 0xA3,  # EBML ID
        0x9F,                    # Size
        0x42, 0x86, 0x81, 0x01, # EBMLVersion = 1
        0x42, 0xF7, 0x81, 0x01, # EBMLReadVersion = 1
        0x42, 0xF2, 0x81, 0x04, # EBMLMaxIDLength = 4
        0x42, 0xF3, 0x81, 0x08, # EBMLMaxSizeLength = 8
        0x42, 0x82, 0x84,       # DocType = "webm"
        0x77, 0x65, 0x62, 0x6D,
        0x42, 0x87, 0x81, 0x02, # DocTypeVersion = 2
        0x42, 0x85, 0x81, 0x02, # DocTypeReadVersion = 2
    ])


# ── 测试用例 ──────────────────────────────────────────────────────

async def test_ffmpeg_starts():
    """create_audio_service → ffmpeg 进程正常启动"""
    session_id = "s_ffmpeg_test"
    _services.pop(session_id, None)

    db = _MockDB()
    service = await create_audio_service(session_id, db, [])

    proc = service._ffmpeg_proc
    ok = proc is not None and proc.poll() is None
    _log(ok, "ffmpeg 进程已启动（poll() is None）",
         f"proc={proc}, returncode={proc.returncode if proc else 'N/A'}" if not ok else None)

    await destroy_audio_service(session_id)


async def test_handle_chunk_no_crash():
    """handle_chunk 发送 WebM bytes 不抛异常"""
    session_id = "s_chunk_test"
    _services.pop(session_id, None)

    db = _MockDB()
    service = await create_audio_service(session_id, db, [])
    await asyncio.sleep(0.5)

    try:
        await service.handle_chunk(_make_minimal_webm())
        ok = True
    except Exception as e:
        ok = False
        _log(ok, "handle_chunk 不抛异常", str(e))
        await destroy_audio_service(session_id)
        return

    _log(ok, "handle_chunk 不抛异常")
    await destroy_audio_service(session_id)


async def test_handle_chunk_after_ffmpeg_death():
    """ffmpeg 进程死亡后 handle_chunk 安全丢弃"""
    session_id = "s_ffmpeg_death"
    _services.pop(session_id, None)

    db = _MockDB()
    service = await create_audio_service(session_id, db, [])
    await asyncio.sleep(0.5)

    # 强制 kill ffmpeg
    if service._ffmpeg_proc:
        service._ffmpeg_proc.kill()
        service._ffmpeg_proc.wait()

    try:
        await service.handle_chunk(_make_minimal_webm())
        ok = True
    except Exception as e:
        ok = False
        _log(ok, "ffmpeg 死亡后 handle_chunk 安全丢弃（不崩溃）", str(e))
        await destroy_audio_service(session_id)
        return

    _log(ok, "ffmpeg 死亡后 handle_chunk 安全丢弃（不崩溃）")
    await destroy_audio_service(session_id)


async def test_destroy_removes_service():
    """destroy_audio_service 后 get_audio_service 返回 None"""
    session_id = "s_destroy_test"
    _services.pop(session_id, None)

    db = _MockDB()
    await create_audio_service(session_id, db, [])
    await destroy_audio_service(session_id)

    ok = get_audio_service(session_id) is None
    _log(ok, "destroy 后 get_audio_service 返回 None")


async def test_on_asr_result_calls_broadcast():
    """_on_asr_result 调用 insert_speech_transcript_and_broadcast"""
    session_id = "s_broadcast_test"
    _services.pop(session_id, None)

    db = _MockDB()
    service = await create_audio_service(session_id, db, [])

    with patch(
        "app.audio.audio_service.insert_speech_transcript_and_broadcast",
        new_callable=AsyncMock,
    ) as mock_insert:
        await service._on_asr_result("测试文字", b"\x00" * 32000)
        ok = mock_insert.called
        call_kwargs = mock_insert.call_args
        _log(ok, "_on_asr_result 触发 insert_speech_transcript_and_broadcast",
             f"未被调用" if not ok else None)
        if ok:
            print(f"   调用参数: session_id={call_kwargs[0][0]}, "
                  f"text={call_kwargs[1].get('text')}, "
                  f"speaker={call_kwargs[1].get('speaker')}")

    await destroy_audio_service(session_id)


# ── 真实 WebM 端到端测试（可选）────────────────────────────────────

REAL_WEBM_PATH = BACKEND_DIR / "tests" / "audio_samples" / "test_speech.webm"


async def test_real_webm_e2e():
    """发送真实 WebM → 等待 insert_speech_transcript_and_broadcast 被调用"""
    if not REAL_WEBM_PATH.exists():
        print("⏭️  跳过真实 WebM 测试（请在 tests/audio_samples/ 放置 test_speech.webm）")
        return

    session_id = "s_real_webm"
    _services.pop(session_id, None)

    db = _MockDB()
    received: list[dict] = []

    original = None
    try:
        import app.audio.audio_service as _svc_mod
        original = _svc_mod.insert_speech_transcript_and_broadcast

        async def _capture(*args, **kwargs):
            received.append({"args": args, "kwargs": kwargs})

        _svc_mod.insert_speech_transcript_and_broadcast = _capture

        service = await create_audio_service(session_id, db, [])
        await asyncio.sleep(1)

        webm_bytes = REAL_WEBM_PATH.read_bytes()
        chunk_size = 4096
        for i in range(0, len(webm_bytes), chunk_size):
            await service.handle_chunk(webm_bytes[i:i + chunk_size])
            await asyncio.sleep(0.05)

        # 等待回调最多 20 秒
        for _ in range(40):
            if received:
                break
            await asyncio.sleep(0.5)

    finally:
        if original:
            import app.audio.audio_service as _svc_mod
            _svc_mod.insert_speech_transcript_and_broadcast = original
        await destroy_audio_service(session_id)

    ok = len(received) > 0
    if ok:
        r = received[0]
        print(f"   text={r['kwargs'].get('text')}, speaker={r['kwargs'].get('speaker')}")
    _log(ok, "真实 WebM 端到端：insert_speech_transcript_and_broadcast 被调用",
         "20 秒内未收到回调" if not ok else None)


# ── 入口 ──────────────────────────────────────────────────────────

async def main():
    print("=" * 60)
    print("AudioService 集成测试")
    print("=" * 60)

    await test_ffmpeg_starts()
    await test_handle_chunk_no_crash()
    await test_handle_chunk_after_ffmpeg_death()
    await test_destroy_removes_service()
    await test_on_asr_result_calls_broadcast()
    await test_real_webm_e2e()

    print("=" * 60)
    total = PASS + FAIL
    print(f"{'✅' if FAIL == 0 else '❌'} {PASS}/{total} 通过")
    print("=" * 60)
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
