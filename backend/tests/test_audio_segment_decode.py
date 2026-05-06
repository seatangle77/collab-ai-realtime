"""
离线音频 segment 解码验证。

运行：
  python -m backend.tests.test_audio_segment_decode

依赖：
  ffmpeg
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from typing import Callable

from backend.app.audio_segments import OfflineAudioDecodeError, decode_offline_audio_to_pcm


def _log(ok: bool, msg: str, extra: object = None) -> bool:
    print(f"{'✅' if ok else '❌'} {msg}")
    if not ok and extra is not None:
        print("   详情:", extra)
    return ok


def _require_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def _make_webm_segment(duration: float = 1.0) -> bytes:
    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=1000:duration={duration}",
            "-c:a",
            "libopus",
            "-f",
            "webm",
            "pipe:1",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return result.stdout


def _make_aac_segment(duration: float = 1.0) -> bytes:
    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=1000:duration={duration}",
            "-c:a",
            "aac",
            "-f",
            "adts",
            "pipe:1",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return result.stdout


def _expect_decode_ok(name: str, audio_bytes: bytes, mime_type: str) -> bool:
    try:
        pcm = decode_offline_audio_to_pcm(audio_bytes, mime_type)
        return _log(len(pcm) > 0, f"{name} 可解码为 PCM", {"pcm_bytes": len(pcm)})
    except Exception as exc:
        return _log(False, f"{name} 解码失败", str(exc))


def _expect_decode_failed(name: str, audio_bytes: bytes, mime_type: str) -> bool:
    try:
        decode_offline_audio_to_pcm(audio_bytes, mime_type)
    except OfflineAudioDecodeError:
        return _log(True, f"{name} 不可作为独立补传单位")
    except Exception as exc:
        return _log(False, f"{name} 返回了非预期异常", str(exc))
    return _log(False, f"{name} 被误判为可独立解码")


def test_webm_complete_segment_decodes() -> bool:
    return _expect_decode_ok("WebM 完整 segment", _make_webm_segment(), "audio/webm")


def test_webm_middle_bytes_are_rejected() -> bool:
    webm = _make_webm_segment(duration=2.0)
    middle = webm[len(webm) // 3 : len(webm) * 2 // 3]
    return _expect_decode_failed("WebM 中间裸字节", middle, "audio/webm")


def test_aac_complete_segment_decodes() -> bool:
    return _expect_decode_ok("AAC 完整 segment", _make_aac_segment(), "audio/aac")


def run_all() -> bool:
    if not _require_ffmpeg():
        print("⚠️ ffmpeg 不存在，跳过离线音频解码测试")
        return True

    tests: list[Callable[[], bool]] = [
        test_webm_complete_segment_decodes,
        test_webm_middle_bytes_are_rejected,
        test_aac_complete_segment_decodes,
    ]
    results = [test() for test in tests]
    ok = all(results)
    print("\n=== 离线音频解码测试完成：%s ===" % ("通过" if ok else "失败"))
    return ok


if __name__ == "__main__":
    sys.exit(0 if run_all() else 1)
