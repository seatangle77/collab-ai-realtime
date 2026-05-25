# -*- coding: utf-8 -*-
import asyncio
import logging
import threading
import time

from app.audio.speech_recognizer import SpeechRecognizer, SpeechRecognitionListener
from app.settings import tencent_asr_settings

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


class Credential:
    def __init__(self, secret_id: str, secret_key: str):
        self.secret_id = secret_id
        self.secret_key = secret_key


class MyASRListener(SpeechRecognitionListener):
    def __init__(self, session_id: str, on_result, on_partial_result, on_error_callback, loop):
        self.session_id = session_id
        self.on_result = on_result                  # async def on_result(text, audio_bytes, segment_key=None)
        self.on_partial_result = on_partial_result  # async def on_partial_result(segment_key, text, is_final)
        self.on_error_callback = on_error_callback  # 触发重连的同步回调
        self.loop = loop                            # asyncio event loop，用于线程回调桥接
        self.sentence_frames: list[bytes] = []
        self._sentence_segment_texts: dict[str, list[str]] = {}
        self._sentence_last_emit_ms: dict[str, float] = {}
        self._partial_emit_interval_ms = 250

    def cache_audio(self, data: bytes):
        self.sentence_frames.append(data)

    def on_sentence_begin(self, response):
        # 新句子开始，清空音频缓存，避免跨句累积
        self.sentence_frames = []

    @staticmethod
    def _sentence_key(response: dict, result: dict) -> str:
        voice_id = str(response.get("voice_id", "unknown"))
        idx = result.get("index", -1)
        return f"{voice_id}:{idx}"

    @staticmethod
    def _split_segments(word_list: list[dict], sil_gap_ms: int) -> list[str]:
        if not word_list:
            return []
        segments: list[list[dict]] = []
        current_segment: list[dict] = [word_list[0]]
        last_end = word_list[0].get("end_time", 0)
        for w in word_list[1:]:
            start = w.get("start_time", last_end)
            end = w.get("end_time", start)
            gap = start - last_end
            if gap >= sil_gap_ms and current_segment:
                segments.append(current_segment)
                current_segment = [w]
            else:
                current_segment.append(w)
            last_end = end
        if current_segment:
            segments.append(current_segment)
        return ["".join(w.get("word", "") for w in seg).strip() for seg in segments]

    def on_recognition_result_change(self, response):
        result = response.get("result") or {}
        word_list = result.get("word_list") or []
        if not word_list:
            return

        now_ms = time.time() * 1000
        sentence_key = self._sentence_key(response, result)
        last_emit = self._sentence_last_emit_ms.get(sentence_key, 0.0)
        if now_ms - last_emit < self._partial_emit_interval_ms:
            return

        seg_texts = self._split_segments(word_list, tencent_asr_settings.local_split_gap_ms)
        if not seg_texts:
            return
        prev_texts = self._sentence_segment_texts.get(sentence_key, [])
        for i, seg_text in enumerate(seg_texts):
            if not seg_text:
                continue
            if i < len(prev_texts) and prev_texts[i] == seg_text:
                continue
            segment_key = f"{sentence_key}:{i}"
            if self.on_partial_result:
                asyncio.run_coroutine_threadsafe(
                    self.on_partial_result(segment_key, seg_text, False),
                    self.loop,
                )
        self._sentence_segment_texts[sentence_key] = seg_texts
        self._sentence_last_emit_ms[sentence_key] = now_ms

    def on_sentence_end(self, response):
        """
        在腾讯返回的一句内部，再按 0.6 秒静音做二次分段。
        逻辑：
          - 从 result.word_list 中读取每个词的 start_time / end_time（毫秒）
          - 相邻两个词之间的间隔 >= 600ms 视为一个“停顿点”，在此处分割
          - 对每一小段，拼接文本并调用外部 on_result(text, audio_bytes)
        """
        result = response.get("result") or {}
        word_list = result.get("word_list") or []
        sentence_key = self._sentence_key(response, result)

        # 若没有词级时间戳，退回到原来的整句逻辑
        if not word_list:
            text = result.get("voice_text_str", "")
            audio_bytes = b"".join(self.sentence_frames)
            self.sentence_frames = []
            if text:
                asyncio.run_coroutine_threadsafe(
                    self.on_result(text, audio_bytes, segment_key=f"{sentence_key}:0"),
                    self.loop,
                )
                if self.on_partial_result:
                    segment_key = f"{sentence_key}:0"
                    asyncio.run_coroutine_threadsafe(
                        self.on_partial_result(segment_key, text, True),
                        self.loop,
                    )
            self._sentence_segment_texts.pop(sentence_key, None)
            self._sentence_last_emit_ms.pop(sentence_key, None)
            return

        seg_texts = self._split_segments(word_list, tencent_asr_settings.local_split_gap_ms)

        # 目前先简单使用整句音频作为每一小段的 audio_bytes
        # 这样可以复用现有的声纹识别与写库逻辑，代价是会多次重复利用同一段音频。
        full_audio = b"".join(self.sentence_frames)
        self.sentence_frames = []

        for i, seg_text in enumerate(seg_texts):
            if not seg_text:
                continue
            segment_key = f"{sentence_key}:{i}"
            asyncio.run_coroutine_threadsafe(
                self.on_result(seg_text, full_audio, segment_key=segment_key),
                self.loop,
            )
            if self.on_partial_result:
                asyncio.run_coroutine_threadsafe(
                    self.on_partial_result(segment_key, seg_text, True),
                    self.loop,
                )
        self._sentence_segment_texts.pop(sentence_key, None)
        self._sentence_last_emit_ms.pop(sentence_key, None)

    def on_fail(self, response):
        logger.error(
            "[TencentASR] 识别失败 session=%s: code=%s msg=%s",
            self.session_id,
            response.get("code"),
            response.get("message"),
        )
        # 在独立线程触发重连，避免阻塞 ASR 回调线程
        if self.on_error_callback:
            threading.Thread(target=self.on_error_callback, daemon=True).start()


class TencentASR:
    def __init__(self, session_id: str, on_result, on_partial_result, loop, enable_reconnect: bool = True):
        """
        session_id : 当前会话 ID
        on_result  : async def on_result(text: str, audio_bytes: bytes)
        loop       : asyncio 事件循环（传入 asyncio.get_event_loop()）
        """
        self.session_id = session_id
        self._on_result = on_result
        self._loop = loop
        self._retry_count = 0
        self._stopped = False
        self._enable_reconnect = enable_reconnect

        self.listener = MyASRListener(
            session_id,
            on_result,
            on_partial_result,
            self._on_asr_error,
            loop,
        )
        self._build_recognizer()

    def _build_recognizer(self) -> None:
        """构造 SpeechRecognizer，供初始化和重连复用"""
        cred = Credential(
            tencent_asr_settings.secret_id,
            tencent_asr_settings.secret_key,
        )
        self.recognizer = SpeechRecognizer(
            tencent_asr_settings.appid,
            cred,
            tencent_asr_settings.asr_engine,
            self.listener,
        )
        self.recognizer.set_need_vad(1)           # 腾讯侧 VAD 自动断句
        self.recognizer.set_vad_silence_time(tencent_asr_settings.vad_silence_time_ms)
        self.recognizer.set_filter_modal(1)       # 部分过滤语气词，减少“嗯/啊/呃”等低信息转写
        self.recognizer.set_word_info(1)          # 开启词级时间戳，供本地二次切分
        self.recognizer.set_voice_format(1)       # 1 = PCM

    def _on_asr_error(self) -> None:
        """ASR 连接异常时触发，最多重连 MAX_RETRIES 次，间隔递增"""
        if not self._enable_reconnect:
            logger.warning("[TencentASR] session=%s 忽略重连：当前任务禁用自动重连", self.session_id)
            return

        if self._stopped:
            logger.warning("[TencentASR] session=%s 忽略重连：已停止", self.session_id)
            return

        if self._retry_count >= MAX_RETRIES:
            logger.error(
                "[TencentASR] session=%s 重连次数已达上限(%d)，放弃重连",
                self.session_id, MAX_RETRIES,
            )
            return

        self._retry_count += 1
        wait = self._retry_count * 2  # 2s / 4s / 6s 递增
        logger.warning(
            "[TencentASR] session=%s 第 %d 次重连，等待 %ds ...",
            self.session_id, self._retry_count, wait,
        )
        time.sleep(wait)

        try:
            self._build_recognizer()
            self.recognizer.start()
            self._retry_count = 0
            logger.info("[TencentASR] session=%s 重连成功", self.session_id)
        except Exception as e:
            logger.error("[TencentASR] session=%s 重连失败: %s", self.session_id, e)

    def start(self) -> None:
        logger.info("[TencentASR] session=%s start", self.session_id)
        self.recognizer.start()

    def write(self, pcm_bytes: bytes) -> None:
        """每收到一个 audio_chunk 调一次：同时缓存音频 + 发给 ASR"""
        self.listener.cache_audio(pcm_bytes)
        wait_started = time.perf_counter()
        status = getattr(self.recognizer, "status", None)
        if status == 1:
            logger.warning(
                "[TencentASR] session=%s write_waiting_for_open pcm_bytes=%d",
                self.session_id,
                len(pcm_bytes),
            )
        self.recognizer.write(pcm_bytes)
        wait_elapsed_ms = (time.perf_counter() - wait_started) * 1000
        if wait_elapsed_ms >= 300:
            logger.warning(
                "[TencentASR] session=%s write_slow pcm_bytes=%d elapsed_ms=%.1f status=%s",
                self.session_id,
                len(pcm_bytes),
                wait_elapsed_ms,
                getattr(self.recognizer, "status", None),
            )

    def stop(self) -> None:
        self._stopped = True
        try:
            self.recognizer.stop()
        except Exception as e:
            logger.warning(
                "[TencentASR] stop 异常 session=%s: %s",
                self.session_id, e,
            )
