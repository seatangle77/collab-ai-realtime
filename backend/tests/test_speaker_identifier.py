"""
说话人识别单元测试：SpeakerIdentifier

测试用例：
  1. 无声纹时 identify → ("unknown", 0.0)
  2. 音频过短时 identify → ("unknown", 0.0)
  3. load_profiles 加载正常 embedding → has_profiles() == True
  4. load_profiles 跳过非 ready 状态
  5. identify 用合成音频返回结果（置信度数值合理）
  6. clear() 清理后 has_profiles() == False

运行前提：已安装 resemblyzer numpy
运行方式（在 backend/ 目录下）：
  python tests/test_speaker_identifier.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

# ── 路径 & 环境变量 ──────────────────────────────────────────────
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

# 加载 .env.local
env_path = BACKEND_DIR / ".env.local"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

import numpy as np
from resemblyzer import VoiceEncoder, preprocess_wav

from app.audio.speaker_identifier import SpeakerIdentifier, SIMILARITY_THRESHOLD

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


def _make_sine_pcm(duration_sec: float = 1.0, freq: int = 440, sr: int = 16000) -> bytes:
    """生成合成正弦波 PCM bytes，用于基础逻辑测试"""
    t = np.linspace(0, duration_sec, int(sr * duration_sec), endpoint=False)
    wave = (np.sin(2 * np.pi * freq * t) * 32767).astype(np.int16)
    return wave.tobytes()


def _make_ref_embedding() -> list[float]:
    """生成一个随机 256 维向量模拟声纹 embedding"""
    v = np.random.randn(256).astype(np.float32)
    v /= np.linalg.norm(v)
    return v.tolist()


# ── mock DB ──────────────────────────────────────────────────────

class _MockRow:
    def __init__(self, data: dict):
        self._data = data

    def __getitem__(self, key):
        return self._data[key]


class _MockDB:
    """最小化 mock AsyncSession，只实现 execute"""

    def __init__(self, rows: list[dict]):
        self._rows = rows

    async def execute(self, query, params=None):
        return self

    def mappings(self):
        return self

    def all(self):
        return [_MockRow(r) for r in self._rows]


# ── 测试用例 ──────────────────────────────────────────────────────

async def test_identify_no_profiles():
    """无声纹时 identify 返回 unknown"""
    si = SpeakerIdentifier("s_test_1")
    result = si.identify(_make_sine_pcm())
    ok = result == ("unknown", 0.0)
    _log(ok, "无声纹时 identify → ('unknown', 0.0)", result)


async def test_identify_short_audio():
    """音频过短（<0.5秒）时 identify 返回 unknown"""
    si = SpeakerIdentifier("s_test_2")
    # 手动注入一个声纹，确保不是因为无声纹返回 unknown
    si.ref_embeds["user_dummy"] = np.array(_make_ref_embedding(), dtype=np.float32)
    short_pcm = _make_sine_pcm(duration_sec=0.05)  # 只有 0.05 秒
    result = si.identify(short_pcm)
    ok = result[0] == "unknown"
    _log(ok, "音频过短时 identify → unknown", result)


async def test_load_profiles_ready():
    """load_profiles 加载 ready 状态的 embedding → has_profiles() == True"""
    si = SpeakerIdentifier("s_test_3")
    embedding = _make_ref_embedding()
    mock_db = _MockDB([
        {"user_id": "u001", "voice_embedding": embedding}
    ])
    await si.load_profiles(mock_db, ["u001"])
    ok = si.has_profiles() and "u001" in si.ref_embeds
    _log(ok, "load_profiles 加载正常 embedding → has_profiles() == True")


async def test_load_profiles_skips_non_ready():
    """load_profiles 只加载 embedding_status='ready' 的行（mock DB 不返回非 ready 行）"""
    si = SpeakerIdentifier("s_test_4")
    # mock DB 返回空（模拟 embedding_status != 'ready' 被过滤）
    mock_db = _MockDB([])
    await si.load_profiles(mock_db, ["u002"])
    ok = not si.has_profiles()
    _log(ok, "load_profiles 无 ready 行 → has_profiles() == False")


async def test_identify_with_synthetic_audio():
    """identify 用合成音频：置信度在 [0, 1] 范围内，返回 user_id 或 unknown"""
    si = SpeakerIdentifier("s_test_5")
    embedding = _make_ref_embedding()
    si.ref_embeds["u_synth"] = np.array(embedding, dtype=np.float32)

    pcm = _make_sine_pcm(duration_sec=2.0)
    user_id, confidence = si.identify(pcm)

    ok = isinstance(confidence, float) and 0.0 <= confidence <= 1.0
    _log(ok, f"identify 合成音频 → user={user_id}, confidence={confidence:.3f}（值域合法）", None if ok else confidence)


async def test_clear():
    """clear() 后 has_profiles() == False"""
    si = SpeakerIdentifier("s_test_6")
    si.ref_embeds["u001"] = np.array(_make_ref_embedding(), dtype=np.float32)
    si.clear()
    ok = not si.has_profiles()
    _log(ok, "clear() 后 has_profiles() == False")


# ── 真实音频测试（可选，需提供 WAV 文件）────────────────────────────

REAL_AUDIO_DIR = BACKEND_DIR / "tests" / "audio_samples"


async def test_identify_real_audio():
    """用真实音频文件验证声纹识别准确度（需提前准备样本）"""
    person_a = REAL_AUDIO_DIR / "person_a_ref.wav"
    person_b = REAL_AUDIO_DIR / "person_b_test.wav"

    if not person_a.exists() or not person_b.exists():
        print("⏭️  跳过真实音频测试（请在 tests/audio_samples/ 放置 person_a_ref.wav 和 person_b_test.wav）")
        return

    encoder = VoiceEncoder()
    ref_wav = preprocess_wav(person_a)
    ref_embed = encoder.embed_utterance(ref_wav)

    si = SpeakerIdentifier("s_test_real")
    si.ref_embeds["person_a"] = ref_embed

    test_wav = preprocess_wav(person_b)
    test_pcm = (test_wav * 32767).astype(np.int16).tobytes()
    user_id, confidence = si.identify(test_pcm)

    print(f"   真实音频结果：user_id={user_id}, confidence={confidence:.3f}")
    _log(True, "真实音频测试完成（请人工判断结果是否符合预期）")


# ── 入口 ──────────────────────────────────────────────────────────

async def main():
    print("=" * 60)
    print("SpeakerIdentifier 单元测试")
    print("=" * 60)

    await test_identify_no_profiles()
    await test_identify_short_audio()
    await test_load_profiles_ready()
    await test_load_profiles_skips_non_ready()
    await test_identify_with_synthetic_audio()
    await test_clear()
    await test_identify_real_audio()

    print("=" * 60)
    total = PASS + FAIL
    print(f"{'✅' if FAIL == 0 else '❌'} {PASS}/{total} 通过")
    print("=" * 60)
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
