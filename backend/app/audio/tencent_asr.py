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
    def __init__(self, session_id: str, on_result, on_error_callback, loop):
        self.session_id = session_id
        self.on_result = on_result                  # async def on_result(text, audio_bytes)
        self.on_error_callback = on_error_callback  # 触发重连的同步回调
        self.loop = loop                            # asyncio event loop，用于线程回调桥接
        self.sentence_frames: list[bytes] = []

    def cache_audio(self, data: bytes):
        self.sentence_frames.append(data)

    def on_sentence_begin(self, response):
        # 新句子开始，清空音频缓存，避免跨句累积
        self.sentence_frames = []

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

        # 若没有词级时间戳，退回到原来的整句逻辑
        if not word_list:
            text = result.get("voice_text_str", "")
            audio_bytes = b"".join(self.sentence_frames)
            self.sentence_frames = []
            if text:
                asyncio.run_coroutine_threadsafe(
                    self.on_result(text, audio_bytes),
                    self.loop,
                )
            return

        # 按 0.6 秒静音切分
        SIL_GAP_MS = 600
        segments: list[list[dict]] = []
        current_segment: list[dict] = [word_list[0]]
        last_end = word_list[0].get("end_time", 0)

        for w in word_list[1:]:
            start = w.get("start_time", last_end)
            end = w.get("end_time", start)
            gap = start - last_end

            if gap >= SIL_GAP_MS and current_segment:
                segments.append(current_segment)
                current_segment = [w]
            else:
                current_segment.append(w)

            last_end = end

        if current_segment:
            segments.append(current_segment)

        # 目前先简单使用整句音频作为每一小段的 audio_bytes
        # 这样可以复用现有的声纹识别与写库逻辑，代价是会多次重复利用同一段音频。
        full_audio = b"".join(self.sentence_frames)
        self.sentence_frames = []

        for seg_words in segments:
            seg_text = "".join(w.get("word", "") for w in seg_words).strip()
            if not seg_text:
                continue
            asyncio.run_coroutine_threadsafe(
                self.on_result(seg_text, full_audio),
                self.loop,
            )

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
    def __init__(self, session_id: str, on_result, loop):
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

        self.listener = MyASRListener(
            session_id,
            on_result,
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
        self.recognizer.set_need_vad(1)      # 腾讯侧 VAD 自动断句
        self.recognizer.set_voice_format(1)  # 1 = PCM

    def _on_asr_error(self) -> None:
        """ASR 连接异常时触发，最多重连 MAX_RETRIES 次，间隔递增"""
        if self._stopped:
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
            logger.info("[TencentASR] session=%s 重连成功", self.session_id)
        except Exception as e:
            logger.error("[TencentASR] session=%s 重连失败: %s", self.session_id, e)

    def start(self) -> None:
        self.recognizer.start()

    def write(self, pcm_bytes: bytes) -> None:
        """每收到一个 audio_chunk 调一次：同时缓存音频 + 发给 ASR"""
        self.listener.cache_audio(pcm_bytes)
        self.recognizer.write(pcm_bytes)

    def stop(self) -> None:
        self._stopped = True
        try:
            self.recognizer.stop()
        except Exception as e:
            logger.warning(
                "[TencentASR] stop 异常 session=%s: %s",
                self.session_id, e,
            )
