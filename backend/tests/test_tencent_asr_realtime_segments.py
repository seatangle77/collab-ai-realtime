from __future__ import annotations

import asyncio
import threading
import time
from typing import Any

from app.audio.tencent_asr import MyASRListener


def _log(ok: bool, message: str, extra: Any | None = None) -> bool:
    print(f"{'✅' if ok else '❌'} {message}")
    if not ok and extra is not None:
        print("   详情:", extra)
    return ok


class LoopRunner:
    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self.loop.call_soon_threadsafe(self.loop.stop)
        self._thread.join(timeout=2)
        self.loop.close()


def run_all() -> bool:
    print("=== 开始 TencentASR 实时分段测试 ===")
    runner = LoopRunner()
    runner.start()

    partial_events: list[tuple[str, str, bool]] = []
    final_results: list[tuple[str, int]] = []

    async def on_partial(segment_key: str, text: str, is_final: bool) -> None:
        partial_events.append((segment_key, text, is_final))

    async def on_result(text: str, audio_bytes: bytes) -> None:
        final_results.append((text, len(audio_bytes)))

    listener = MyASRListener(
        session_id="s-demo",
        on_result=on_result,
        on_partial_result=on_partial,
        on_error_callback=lambda: None,
        loop=runner.loop,
    )

    # 先模拟句子开始
    listener.on_sentence_begin({"voice_id": "voice-1", "result": {"index": 1, "slice_type": 0}})
    listener.cache_audio(b"a" * 3200)
    listener.cache_audio(b"b" * 3200)

    # 中间结果：应切成两段（中间有 800ms 停顿）
    response_change = {
        "voice_id": "voice-1",
        "result": {
            "index": 1,
            "slice_type": 1,
            "word_list": [
                {"word": "我们", "start_time": 0, "end_time": 200},
                {"word": "先看", "start_time": 210, "end_time": 360},
                {"word": "方案", "start_time": 380, "end_time": 520},
                {"word": "然后", "start_time": 1400, "end_time": 1600},
                {"word": "执行", "start_time": 1620, "end_time": 1780},
            ],
        },
    }
    listener.on_recognition_result_change(response_change)
    time.sleep(0.2)

    ok = True
    partial_non_final = [e for e in partial_events if e[2] is False]
    ok &= _log(len(partial_non_final) >= 2, "中间结果可实时推送分段", partial_events)

    # 句子结束：应产出正式结果 + 发送 is_final=True 片段通知
    response_end = {
        "voice_id": "voice-1",
        "result": {
            "index": 1,
            "slice_type": 2,
            "word_list": response_change["result"]["word_list"],
        },
    }
    listener.on_sentence_end(response_end)
    time.sleep(0.2)

    final_partials = [e for e in partial_events if e[2] is True]
    ok &= _log(len(final_partials) >= 2, "句子结束后会发送分段 final 通知", final_partials)
    ok &= _log(len(final_results) >= 2, "句子结束后会产出正式分段结果", final_results)

    runner.stop()
    print(f"\n=== 结果: {'全部通过 ✅' if ok else '有失败 ❌'} ===")
    return ok


if __name__ == "__main__":
    import sys

    sys.exit(0 if run_all() else 1)
