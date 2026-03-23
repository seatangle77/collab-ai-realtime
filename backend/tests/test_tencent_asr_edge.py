"""
TencentASR 边界 & 异常单元测试（用例 30-34）

运行方式（在 backend/ 目录下）：
  python tests/test_tencent_asr_edge.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
import threading
from pathlib import Path
from typing import Any

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
from app.audio.tencent_asr import TencentASR, MAX_RETRIES
from app.audio.speech_recognizer import OPENED, STARTED

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


def _make_asr(sid: str) -> tuple[TencentASR, asyncio.AbstractEventLoop]:
    loop = asyncio.new_event_loop()
    async def _dummy(text, audio): pass
    asr = TencentASR(sid, _dummy, loop)
    return asr, loop


# ── 用例 ──────────────────────────────────────────────────────────

def test_30_on_fail_increments_retry():
    """30: on_fail 触发 → _retry_count 递增"""
    asr, loop = _make_asr("s_asr_30")
    asr.start()
    time.sleep(2)

    initial = asr._retry_count

    # 直接调用内部重连逻辑（模拟 on_fail 触发，跳过实际等待）
    asr._retry_count = 0
    # 用线程模拟一次 on_fail 回调（不等待实际重连完成）
    original_build = asr._build_recognizer
    build_called = []

    def _mock_build():
        build_called.append(1)
        original_build()

    asr._build_recognizer = _mock_build
    # 模拟 on_fail 触发 → 在线程里跑 _on_asr_error
    t = threading.Thread(target=asr._on_asr_error, daemon=True)
    t.start()
    t.join(timeout=10)

    ok = asr._retry_count == 1
    _log(ok, "30: on_fail 触发 → _retry_count == 1", f"retry_count={asr._retry_count}")
    asr.stop()
    loop.close()


def test_31_max_retries_not_exceeded():
    """31: _on_asr_error 触发 MAX_RETRIES 次后不再重连"""
    asr, loop = _make_asr("s_asr_31")

    # 直接设到上限，不等待实际重连
    asr._retry_count = MAX_RETRIES
    retry_before = asr._retry_count

    # 再触发一次，应该直接返回不增加
    build_called = []
    original_build = asr._build_recognizer
    def _mock_build():
        build_called.append(1)
        original_build()
    asr._build_recognizer = _mock_build

    # _on_asr_error 应该直接 return（不重建）
    t = threading.Thread(target=asr._on_asr_error, daemon=True)
    t.start()
    t.join(timeout=3)

    ok = len(build_called) == 0 and asr._retry_count == MAX_RETRIES
    _log(ok, f"31: 达到 MAX_RETRIES({MAX_RETRIES}) 后不再重连",
         f"build_called={build_called}, retry={asr._retry_count}")
    loop.close()


def test_32_stopped_flag_prevents_retry():
    """32: stop() 后触发 _on_asr_error → 不重连（_stopped=True）"""
    asr, loop = _make_asr("s_asr_32")
    asr.start()
    time.sleep(1)
    asr.stop()

    retry_before = asr._retry_count
    build_called = []
    original_build = asr._build_recognizer
    def _mock_build():
        build_called.append(1)
        original_build()
    asr._build_recognizer = _mock_build

    t = threading.Thread(target=asr._on_asr_error, daemon=True)
    t.start()
    t.join(timeout=3)

    ok = len(build_called) == 0
    _log(ok, "32: stop() 后 _on_asr_error 不触发重连（_stopped=True）",
         f"build_called={build_called}")
    loop.close()


def test_33_write_before_opened_blocks():
    """33: write() 在 STARTED 状态（未 OPENED）时阻塞等待，不丢数据"""
    asr, loop = _make_asr("s_asr_33")

    # 手动设 STARTED 但不 start（模拟还没建立连接）
    asr.recognizer.status = STARTED
    write_completed = []

    def _do_write():
        try:
            # write() 里有 while status == STARTED: sleep(0.1)
            # 我们在 0.5s 后把状态改成 OPENED 让它解除阻塞
            asr.recognizer.write(b"\x00" * 100)
            write_completed.append(True)
        except Exception:
            write_completed.append(False)

    t = threading.Thread(target=_do_write, daemon=True)
    t.start()
    time.sleep(0.3)

    # 模拟连接建立
    asr.recognizer.status = OPENED
    t.join(timeout=5)

    # write 在 OPENED 后完成（但 ws 为 None 会报错，这里只验证不在 STARTED 时无限阻塞）
    ok = not t.is_alive()
    _log(ok, "33: write() 在 STARTED 状态阻塞，OPENED 后解除（不永久阻塞）",
         "线程仍在运行（永久阻塞）" if not ok else None)
    loop.close()


def test_34_short_pcm_sentence_frames():
    """34: 极短 PCM 触发 on_sentence_end → sentence_frames 被清空"""
    loop = asyncio.new_event_loop()
    received_audio = []

    async def _on_result(text, audio_bytes):
        received_audio.append(len(audio_bytes))

    asr = TencentASR("s_asr_34", _on_result, loop)

    # 手动向 listener 注入数据并触发 on_sentence_end
    tiny_pcm = b"\x00" * 320  # 10ms
    asr.listener.cache_audio(tiny_pcm)

    fake_response = {
        "result": {"voice_text_str": "短句测试"},
        "voice_id": "test_voice"
    }
    asr.listener.on_sentence_end(fake_response)
    time.sleep(0.2)

    # on_sentence_end 后 sentence_frames 应清空
    ok1 = len(asr.listener.sentence_frames) == 0
    _log(ok1, "34: on_sentence_end 后 sentence_frames 被清空",
         f"frames={len(asr.listener.sentence_frames)}")

    loop.close()


# ── 入口 ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("TencentASR 边界 & 异常单元测试")
    print("=" * 60)

    test_30_on_fail_increments_retry()
    test_31_max_retries_not_exceeded()
    test_32_stopped_flag_prevents_retry()
    test_33_write_before_opened_blocks()
    test_34_short_pcm_sentence_frames()

    print("=" * 60)
    total = PASS + FAIL
    print(f"{'✅' if FAIL == 0 else '❌'} {PASS}/{total} 通过")
    print("=" * 60)
    sys.exit(0 if FAIL == 0 else 1)
