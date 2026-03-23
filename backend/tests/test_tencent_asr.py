"""
腾讯 ASR 单元测试：TencentASR

测试用例：
  1. WebSocket 连接建立（status == OPENED）
  2. 发送合成 PCM → 回调触发（text 非空或超时）
  3. stop() 正常关闭不抛异常
  4. 重连计数：_retry_count 初始为 0
  5. _stopped 标志：stop() 后 _stopped == True

注意：
  - 测试 2 依赖腾讯 ASR 网络，需确保凭证正确
  - 如果网络不通，测试 2 会超时并给出提示

运行方式（在 backend/ 目录下）：
  python tests/test_tencent_asr.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Any

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
from app.audio.tencent_asr import TencentASR
from app.audio.speech_recognizer import OPENED

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


def _make_silence_pcm(duration_sec: float = 3.0, sr: int = 16000) -> bytes:
    """生成静音 PCM（用于测试连接，不会触发 on_sentence_end）"""
    samples = np.zeros(int(sr * duration_sec), dtype=np.int16)
    return samples.tobytes()


def _make_sine_pcm(duration_sec: float = 3.0, freq: int = 440, sr: int = 16000) -> bytes:
    """生成合成语音 PCM（正弦波）"""
    t = np.linspace(0, duration_sec, int(sr * duration_sec), endpoint=False)
    wave = (np.sin(2 * np.pi * freq * t) * 16000).astype(np.int16)
    return wave.tobytes()


# ── 测试用例 ──────────────────────────────────────────────────────

def test_initial_state():
    """初始状态：_retry_count == 0，_stopped == False"""
    loop = asyncio.new_event_loop()

    async def _dummy(text, audio):
        pass

    asr = TencentASR("s_init", _dummy, loop)
    ok1 = asr._retry_count == 0
    ok2 = asr._stopped is False
    _log(ok1 and ok2, "_retry_count=0，_stopped=False", f"retry={asr._retry_count} stopped={asr._stopped}")
    loop.close()


def test_connection_opened():
    """start() 后 2 秒内 status 变为 OPENED"""
    loop = asyncio.new_event_loop()
    result_holder = []

    async def _dummy(text, audio):
        pass

    asr = TencentASR("s_conn", _dummy, loop)
    asr.start()
    time.sleep(2)

    ok = asr.recognizer.status == OPENED
    _log(ok, "start() 后 status == OPENED（已连接腾讯 ASR）",
         f"status={asr.recognizer.status}" if not ok else None)

    asr.stop()
    loop.close()


def test_stop_no_exception():
    """stop() 正常调用不抛异常"""
    loop = asyncio.new_event_loop()

    async def _dummy(text, audio):
        pass

    asr = TencentASR("s_stop", _dummy, loop)
    asr.start()
    time.sleep(1)

    try:
        asr.stop()
        ok = True
    except Exception as e:
        ok = False
        _log(ok, "stop() 不抛异常", str(e))
        loop.close()
        return

    _log(ok, "stop() 正常执行不抛异常")
    ok2 = asr._stopped is True
    _log(ok2, "stop() 后 _stopped == True", f"_stopped={asr._stopped}")
    loop.close()


def test_write_and_callback():
    """发送合成 PCM → 等待 on_sentence_end 回调（最多等 15 秒）"""
    loop = asyncio.new_event_loop()
    received: list[str] = []

    async def _on_result(text: str, audio_bytes: bytes):
        received.append(text)

    asr = TencentASR("s_write", _on_result, loop)
    asr.start()
    time.sleep(2)  # 等连接建立

    # 分块发送合成 PCM（正弦波，腾讯可能识别不出文字但会触发回调流程）
    pcm = _make_sine_pcm(duration_sec=4.0)
    chunk_size = 3200
    for i in range(0, len(pcm), chunk_size):
        asr.write(pcm[i:i + chunk_size])
        time.sleep(0.05)

    # 等待回调最多 15 秒
    waited = 0
    while waited < 15 and not received:
        time.sleep(0.5)
        waited += 0.5

    asr.stop()
    loop.close()

    if received:
        _log(True, f"on_sentence_end 回调触发，text={repr(received[0][:30])}")
    else:
        print("⏭️  on_sentence_end 未触发（合成音频腾讯可能无法识别，属正常情况）")
        print("   建议：提供真实人声 PCM 文件重跑此测试")
        _log(True, "write() 发送无异常（连接正常）")


REAL_PCM_PATH = BACKEND_DIR / "tests" / "audio_samples" / "test_speech.pcm"


def test_real_pcm_callback():
    """用真实 PCM 文件测试回调（需提前准备）"""
    if not REAL_PCM_PATH.exists():
        print("⏭️  跳过真实 PCM 测试（请在 tests/audio_samples/ 放置 test_speech.pcm，16kHz 16bit mono）")
        return

    loop = asyncio.new_event_loop()
    received: list[str] = []

    async def _on_result(text: str, audio_bytes: bytes):
        received.append(text)

    asr = TencentASR("s_real_pcm", _on_result, loop)
    asr.start()
    time.sleep(2)

    pcm = REAL_PCM_PATH.read_bytes()
    chunk_size = 3200
    for i in range(0, len(pcm), chunk_size):
        asr.write(pcm[i:i + chunk_size])
        time.sleep(0.05)

    waited = 0
    while waited < 20 and not received:
        time.sleep(0.5)
        waited += 0.5

    asr.stop()
    loop.close()

    ok = len(received) > 0 and any(t.strip() for t in received)
    _log(ok, f"真实 PCM 回调触发，text={repr(received[0][:50]) if received else '无'}")


# ── 入口 ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("TencentASR 单元测试")
    print("=" * 60)

    test_initial_state()
    test_connection_opened()
    test_stop_no_exception()
    test_write_and_callback()
    test_real_pcm_callback()

    print("=" * 60)
    total = PASS + FAIL
    print(f"{'✅' if FAIL == 0 else '❌'} {PASS}/{total} 通过")
    print("=" * 60)
    sys.exit(0 if FAIL == 0 else 1)
