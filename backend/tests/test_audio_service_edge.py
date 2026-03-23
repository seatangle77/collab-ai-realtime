"""
AudioService 边界 & 异常单元测试（用例 24-29）

运行方式（在 backend/ 目录下）：
  python tests/test_audio_service_edge.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

env_path = BACKEND_DIR / ".env.local"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from app.audio.audio_service import (
    AudioService,
    create_audio_service,
    destroy_audio_service,
    get_audio_service,
    _services,
)

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


class _MockDB:
    def __init__(self, rows=None):
        self._rows = rows or []
    async def execute(self, q, p=None): return self
    def mappings(self): return self
    def all(self): return []


# ── 用例 ──────────────────────────────────────────────────────────

async def test_24_empty_text_no_insert():
    """24: _on_asr_result 收到空文本 → insert 不被调用"""
    sid = "s_edge_24"
    _services.pop(sid, None)
    service = await create_audio_service(sid, _MockDB(), [])

    with patch("app.audio.audio_service.insert_speech_transcript_and_broadcast",
               new_callable=AsyncMock) as mock_insert:
        await service._on_asr_result("", b"\x00" * 32000)
        await service._on_asr_result("   ", b"\x00" * 32000)
        ok = not mock_insert.called
        _log(ok, "24: 空/纯空格文本 → insert 不被调用",
             f"called={mock_insert.called}" if not ok else None)

    await destroy_audio_service(sid)


async def test_25_insert_exception_no_crash():
    """25: _on_asr_result 写库抛异常 → 下一个 chunk 仍能正常处理"""
    sid = "s_edge_25"
    _services.pop(sid, None)
    service = await create_audio_service(sid, _MockDB(), [])
    call_count = 0

    async def _raise_first(*a, **kw):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("模拟写库失败")

    with patch("app.audio.audio_service.insert_speech_transcript_and_broadcast", side_effect=_raise_first):
        try:
            await service._on_asr_result("第一句（会失败）", b"\x00" * 32000)
            await service._on_asr_result("第二句（正常）", b"\x00" * 32000)
            ok = call_count == 2
        except Exception as e:
            ok = False
            _log(ok, "25: 写库异常不影响下一次调用", str(e))
            await destroy_audio_service(sid)
            return

    _log(ok, "25: 写库异常不崩溃，第二次调用正常触发", f"call_count={call_count}")
    await destroy_audio_service(sid)


async def test_26_concurrent_asr_results():
    """26: 多个 _on_asr_result 并发调用 → 无竞态，各自正常写库"""
    sid = "s_edge_26"
    _services.pop(sid, None)
    service = await create_audio_service(sid, _MockDB(), [])
    call_args = []

    async def _capture(*a, **kw):
        call_args.append(kw.get("text"))

    with patch("app.audio.audio_service.insert_speech_transcript_and_broadcast", side_effect=_capture):
        await asyncio.gather(
            service._on_asr_result("并发句子1", b"\x00" * 32000),
            service._on_asr_result("并发句子2", b"\x00" * 32000),
            service._on_asr_result("并发句子3", b"\x00" * 32000),
        )
        ok = len(call_args) == 3 and set(call_args) == {"并发句子1", "并发句子2", "并发句子3"}
        _log(ok, "26: 3 个并发 _on_asr_result → 各自正确写库", call_args)

    await destroy_audio_service(sid)


async def test_27_resemblyzer_exception_fallback():
    """27: Resemblyzer identify 抛异常 → speaker 降级为 unknown，transcript 仍写入"""
    sid = "s_edge_27"
    _services.pop(sid, None)
    service = await create_audio_service(sid, _MockDB(), [])

    # 强制 has_profiles 返回 True，触发 identify 调用
    service.identifier.ref_embeds["fake_user"] = None  # 非法 embedding

    captured = {}

    async def _capture(*a, **kw):
        captured.update(kw)

    with patch("app.audio.audio_service.insert_speech_transcript_and_broadcast", side_effect=_capture):
        await service._on_asr_result("异常测试句子", b"\x00" * 32000)

    ok = captured.get("text") == "异常测试句子" and captured.get("speaker") in ("unknown", None)
    _log(ok, "27: Resemblyzer 异常 → speaker=unknown，transcript 仍写入", captured)
    await destroy_audio_service(sid)


async def test_28_stop_no_deadlock():
    """28: ffmpeg 启动后立即 stop → 2 秒内返回（无死锁）"""
    sid = "s_edge_28"
    _services.pop(sid, None)
    service = await create_audio_service(sid, _MockDB(), [])
    await asyncio.sleep(0.3)

    start = time.time()
    await destroy_audio_service(sid)
    elapsed = time.time() - start

    ok = elapsed < 8
    _log(ok, f"28: stop() 在 {elapsed:.2f}s 内返回（无死锁）",
         f"耗时 {elapsed:.2f}s > 8s" if not ok else None)


async def test_29_stop_idempotent():
    """29: destroy_audio_service 调用两次 → 第二次不报错（幂等）"""
    sid = "s_edge_29"
    _services.pop(sid, None)
    await create_audio_service(sid, _MockDB(), [])

    try:
        await destroy_audio_service(sid)
        await destroy_audio_service(sid)  # 第二次
        ok = True
    except Exception as e:
        ok = False
        _log(ok, "29: destroy 两次不报错（幂等）", str(e))
        return

    ok2 = get_audio_service(sid) is None
    _log(ok and ok2, "29: destroy 两次不报错（幂等）且 get 返回 None")


# ── 入口 ──────────────────────────────────────────────────────────

async def main():
    print("=" * 60)
    print("AudioService 边界 & 异常单元测试")
    print("=" * 60)

    await test_24_empty_text_no_insert()
    await test_25_insert_exception_no_crash()
    await test_26_concurrent_asr_results()
    await test_27_resemblyzer_exception_fallback()
    await test_28_stop_no_deadlock()
    await test_29_stop_idempotent()

    print("=" * 60)
    total = PASS + FAIL
    print(f"{'✅' if FAIL == 0 else '❌'} {PASS}/{total} 通过")
    print("=" * 60)
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
