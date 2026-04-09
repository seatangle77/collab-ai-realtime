# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import logging
import subprocess
import threading
import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audio.speaker_identifier import SpeakerIdentifier
from app.audio.tencent_asr import TencentASR
from app.transcript_realtime import insert_speech_transcript_and_broadcast
from app.redis_client import get_redis_client
from app.ws_manager import ws_manager
from app.ws_protocol import build_transcript_segment

try:
    import webrtcvad
except ImportError:  # pragma: no cover
    webrtcvad = None

logger = logging.getLogger(__name__)

# 0.5 秒的 PCM 字节数（16000Hz × 2bytes × 0.5s）
MIN_PCM_BYTES = int(16000 * 2 * 0.5)

# PCM reader 每次读取块大小（0.1 秒）
PCM_READ_CHUNK = 3200
PCM_READER_HEARTBEAT_SEC = 5
VAD_FRAME_BYTES = 320        # 16kHz * 16bit * 10ms = 320 bytes
VAD_REDIS_TTL_SEC = 2        # is_speaking key 过期时间，超过则认为无人说话
VAD_REDIS_WRITE_INTERVAL = 0.5  # 最多每 0.5s 写一次 Redis，避免过于频繁


class AudioService:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self._loop = asyncio.get_event_loop()
        self.identifier = SpeakerIdentifier(session_id)
        self.asr = TencentASR(session_id, self._on_asr_result, self._on_asr_partial_result, self._loop)
        self._ffmpeg_proc: subprocess.Popen | None = None
        self._reader_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        # AAC 专用持久 ffmpeg 管道
        self._aac_ffmpeg_proc: subprocess.Popen | None = None
        self._aac_reader_thread: threading.Thread | None = None
        self._aac_stop_event = threading.Event()
        self._vad = webrtcvad.Vad(2) if webrtcvad is not None else None
        self._vad_last_redis_write: float = 0.0
        self._vad_lock = threading.Lock()
        if self._vad is None:
            logger.warning("[AudioService] session=%s webrtcvad 不可用，VAD is_speaking 检测已禁用", self.session_id)

    async def start(self, db: AsyncSession, user_ids: list[str]) -> None:
        """加载声纹 + 启动 ffmpeg 管道 + 启动腾讯 ASR"""
        # 1. 加载声纹
        await self.identifier.load_profiles(db, user_ids)

        # 2. 启动 WebM ffmpeg 管道（低延迟模式）
        try:
            self._ffmpeg_proc = subprocess.Popen(
                [
                    "ffmpeg",
                    "-loglevel", "quiet",
                    "-fflags", "nobuffer",      # 禁止输出缓冲，立刻输出 PCM
                    "-flags", "low_delay",      # 低延迟模式
                    "-probesize", "32",         # 减少探测阶段读取量
                    "-analyzeduration", "0",    # 跳过流分析等待
                    "-f", "webm",               # 输入格式：WebM
                    "-i", "pipe:0",             # 从 stdin 读
                    "-ar", "16000",             # 采样率 16kHz
                    "-ac", "1",                 # 单声道
                    "-f", "s16le",              # 输出 PCM 16bit little-endian
                    "pipe:1",                   # 输出到 stdout
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            logger.error("[AudioService] session=%s ffmpeg 未安装，音频处理不可用", self.session_id)
            return

        # 3. 启动 WebM PCM reader 线程
        self._stop_event.clear()
        self._reader_thread = threading.Thread(
            target=self._pcm_reader,
            args=(self._ffmpeg_proc, self.asr, self._stop_event),
            daemon=True,
        )
        self._reader_thread.start()

        # 3b. 启动 AAC 持久 ffmpeg 管道（低延迟模式）
        try:
            self._aac_ffmpeg_proc = subprocess.Popen(
                [
                    "ffmpeg",
                    "-loglevel", "quiet",
                    "-fflags", "nobuffer",
                    "-flags", "low_delay",
                    "-probesize", "32",
                    "-analyzeduration", "0",
                    "-f", "aac",                # ADTS AAC 流式输入
                    "-i", "pipe:0",
                    "-ar", "16000",
                    "-ac", "1",
                    "-f", "s16le",
                    "pipe:1",
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            self._aac_stop_event.clear()
            self._aac_reader_thread = threading.Thread(
                target=self._pcm_reader,
                args=(self._aac_ffmpeg_proc, self.asr, self._aac_stop_event),
                daemon=True,
            )
            self._aac_reader_thread.start()
        except FileNotFoundError:
            logger.error("[AudioService] session=%s ffmpeg 未安装，AAC 管道不可用", self.session_id)
            self._aac_ffmpeg_proc = None

        # 4. 启动腾讯 ASR
        self.asr.start()
        logger.info("[AudioService] session=%s 启动完成", self.session_id)

    async def handle_chunk(
        self,
        audio_bytes: bytes,
        mime_type: str = "audio/webm",
        seq: int | None = None,
    ) -> None:
        """收到前端 audio_chunk，按格式路由处理"""
        # Native(Android) AAC：写入持久 ffmpeg 管道（reader 线程转发给 ASR）
        if mime_type.startswith("audio/aac") or mime_type.startswith("audio/mp4"):
            if self._aac_ffmpeg_proc is None or self._aac_ffmpeg_proc.stdin is None:
                logger.warning(
                    "[AudioService] session=%s seq=%s AAC ffmpeg 不可用，chunk 丢弃",
                    self.session_id, seq,
                )
                return
            if self._aac_ffmpeg_proc.poll() is not None:
                logger.error(
                    "[AudioService] session=%s AAC ffmpeg 进程已退出(returncode=%s)，本 chunk 丢弃",
                    self.session_id, self._aac_ffmpeg_proc.returncode,
                )
                return
            try:
                write_started = time.perf_counter()
                self._aac_ffmpeg_proc.stdin.write(audio_bytes)
                self._aac_ffmpeg_proc.stdin.flush()
                write_elapsed_ms = (time.perf_counter() - write_started) * 1000
                if write_elapsed_ms >= 200:
                    logger.warning(
                        "[AudioService] session=%s seq=%s AAC ffmpeg_write_slow bytes=%d elapsed_ms=%.1f",
                        self.session_id, seq, len(audio_bytes), write_elapsed_ms,
                    )
            except (BrokenPipeError, OSError) as e:
                logger.warning("[AudioService] session=%s AAC ffmpeg stdin 写入失败: %s", self.session_id, e)
            return

        # Browser WebM：流式写入 ffmpeg 管道
        if self._ffmpeg_proc is None or self._ffmpeg_proc.stdin is None:
            logger.warning(
                "[AudioService] session=%s seq=%s WebM ffmpeg 不可用，chunk 丢弃",
                self.session_id, seq,
            )
            return

        if self._ffmpeg_proc.poll() is not None:
            logger.error(
                "[AudioService] session=%s ffmpeg 进程已退出(returncode=%s)，本 chunk 丢弃",
                self.session_id, self._ffmpeg_proc.returncode,
            )
            return

        try:
            write_started = time.perf_counter()
            self._ffmpeg_proc.stdin.write(audio_bytes)
            self._ffmpeg_proc.stdin.flush()
            write_elapsed_ms = (time.perf_counter() - write_started) * 1000
            if write_elapsed_ms >= 200:
                logger.warning(
                    "[AudioService] session=%s seq=%s WebM ffmpeg_write_slow bytes=%d elapsed_ms=%.1f",
                    self.session_id, seq, len(audio_bytes), write_elapsed_ms,
                )
        except (BrokenPipeError, OSError) as e:
            logger.warning("[AudioService] session=%s ffmpeg stdin 写入失败: %s", self.session_id, e)

    async def _on_asr_result(
        self,
        text: str,
        audio_bytes: bytes,
        segment_key: str | None = None,
    ) -> None:
        """
        腾讯 ASR on_sentence_end 回调（已由 run_coroutine_threadsafe 桥接到 asyncio）。
        流程：音频长度检查 → Resemblyzer 识别说话人 → 写库 + 广播
        """
        if not text or not text.strip():
            return

        # 音频太短，跳过声纹识别
        if len(audio_bytes) < MIN_PCM_BYTES:
            logger.debug(
                "[AudioService] session=%s 音频过短 (%d bytes)，speaker 标记 unknown",
                self.session_id, len(audio_bytes),
            )
            speaker, confidence = "unknown", 0.0
        elif not self.identifier.has_profiles():
            logger.debug("[AudioService] session=%s 未加载声纹，speaker 标记 unknown", self.session_id)
            speaker, confidence = "unknown", 0.0
        else:
            # Resemblyzer CPU 阻塞，放线程池
            loop = asyncio.get_event_loop()
            speaker, confidence = await loop.run_in_executor(
                None, self.identifier.identify, audio_bytes
            )

        logger.info(
            "[AudioService] session=%s speaker=%s confidence=%.3f text=%r",
            self.session_id, speaker, confidence, text[:50],
        )

        # 写库 + 广播前端
        try:
            await insert_speech_transcript_and_broadcast(
                self.session_id,
                text=text,
                speaker=speaker,
                confidence=confidence,
                segment_key=segment_key,
            )
        except Exception as e:
            logger.error("[AudioService] session=%s 写库/广播失败: %s", self.session_id, e)

    async def _on_asr_partial_result(self, segment_key: str, text: str, is_final: bool) -> None:
        try:
            await ws_manager.broadcast_to_session(
                self.session_id,
                build_transcript_segment(
                    {
                        "session_id": self.session_id,
                        "segment_key": segment_key,
                        "text": text,
                        "speaker": "unknown",
                        "is_final": is_final,
                    }
                ),
            )
        except Exception as e:
            logger.debug("[AudioService] session=%s 实时片段广播失败: %s", self.session_id, e)

    async def _vad_mark_speaking(self) -> None:
        """写 Redis is_speaking 信号，TTL=2s，过期即视为无人说话。"""
        client = get_redis_client()
        if client is None:
            return
        key = f"vad:{self.session_id}:is_speaking"
        try:
            await client.set(key, "1", ex=VAD_REDIS_TTL_SEC)
        except Exception as e:
            logger.warning("[AudioService] session=%s vad_redis_write_failed: %s", self.session_id, e)

    def _process_vad_chunk(self, pcm_chunk: bytes, vad_buf: bytearray) -> bytearray:
        """按 10ms 帧执行 VAD；检测到说话则写 Redis is_speaking 信号。"""
        if self._vad is None:
            return vad_buf

        vad_buf.extend(pcm_chunk)
        saw_speech = False

        while len(vad_buf) >= VAD_FRAME_BYTES:
            frame = bytes(vad_buf[:VAD_FRAME_BYTES])
            del vad_buf[:VAD_FRAME_BYTES]
            try:
                if self._vad.is_speech(frame, 16000):
                    saw_speech = True
            except Exception:
                logger.exception("[AudioService] session=%s VAD 处理失败，当前帧跳过", self.session_id)
                continue

        if not saw_speech:
            return vad_buf

        now = time.time()
        should_write = False
        with self._vad_lock:
            if now - self._vad_last_redis_write >= VAD_REDIS_WRITE_INTERVAL:
                self._vad_last_redis_write = now
                should_write = True

        if should_write:
            asyncio.run_coroutine_threadsafe(self._vad_mark_speaking(), self._loop)

        return vad_buf

    async def stop(self) -> None:
        """会话结束：关闭 ffmpeg → 等 reader 线程 → 停 ASR → 清声纹"""
        self._stop_event.set()
        self._aac_stop_event.set()

        # 关闭 WebM ffmpeg
        if self._ffmpeg_proc is not None:
            try:
                if self._ffmpeg_proc.stdin:
                    self._ffmpeg_proc.stdin.close()
                self._ffmpeg_proc.wait(timeout=5)
            except Exception as e:
                logger.warning("[AudioService] session=%s WebM ffmpeg 关闭异常: %s", self.session_id, e)
                self._ffmpeg_proc.kill()

        # 关闭 AAC ffmpeg
        if self._aac_ffmpeg_proc is not None:
            try:
                if self._aac_ffmpeg_proc.stdin:
                    self._aac_ffmpeg_proc.stdin.close()
                self._aac_ffmpeg_proc.wait(timeout=5)
            except Exception as e:
                logger.warning("[AudioService] session=%s AAC ffmpeg 关闭异常: %s", self.session_id, e)
                self._aac_ffmpeg_proc.kill()

        # 等 reader 线程结束
        if self._reader_thread is not None and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=5)
        if self._aac_reader_thread is not None and self._aac_reader_thread.is_alive():
            self._aac_reader_thread.join(timeout=5)

        # 停止腾讯 ASR
        self.asr.stop()

        # 清理声纹缓存
        self.identifier.clear()

        logger.info("[AudioService] session=%s 已停止", self.session_id)

    def _pcm_reader(
        self,
        proc: subprocess.Popen,
        asr: TencentASR,
        stop_event: threading.Event,
    ) -> None:
        """后台线程：持续从 ffmpeg stdout 读 PCM，转发给腾讯 ASR"""
        session_id = getattr(asr, "session_id", "unknown")
        read_count = 0
        total_bytes = 0
        last_heartbeat_at = time.monotonic()
        vad_buf = bytearray()
        logger.info("[AudioService] session=%s pcm_reader_started", session_id)
        while not stop_event.is_set():
            try:
                data = proc.stdout.read(PCM_READ_CHUNK)
            except Exception:
                logger.exception("[AudioService] session=%s pcm_reader_read_failed", session_id)
                break
            if not data:
                logger.warning("[AudioService] session=%s pcm_reader_eof", session_id)
                break
            read_count += 1
            total_bytes += len(data)
            now = time.monotonic()
            if now - last_heartbeat_at >= PCM_READER_HEARTBEAT_SEC:
                logger.info(
                    "[AudioService] session=%s pcm_reader_heartbeat reads=%d pcm_bytes=%d",
                    session_id,
                    read_count,
                    total_bytes,
                )
                last_heartbeat_at = now
            vad_buf = self._process_vad_chunk(data, vad_buf)
            asr.write(data)
        logger.warning(
            "[AudioService] session=%s pcm_reader_stopped reads=%d pcm_bytes=%d stop_set=%s",
            session_id,
            read_count,
            total_bytes,
            stop_event.is_set(),
        )


# ── Session 注册表 ──────────────────────────────────────────────

_services: dict[str, AudioService] = {}


def get_audio_service(session_id: str) -> AudioService | None:
    return _services.get(session_id)


async def create_audio_service(
    session_id: str,
    db: AsyncSession,
    user_ids: list[str],
) -> AudioService:
    """创建并启动 AudioService，若已存在则先销毁旧实例"""
    if session_id in _services:
        await destroy_audio_service(session_id)

    service = AudioService(session_id)
    _services[session_id] = service
    await service.start(db, user_ids)
    return service


async def destroy_audio_service(session_id: str) -> None:
    """停止并移除 AudioService"""
    service = _services.pop(session_id, None)
    if service is not None:
        await service.stop()
