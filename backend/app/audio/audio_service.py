# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import logging
import subprocess
import threading
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audio.speaker_identifier import SpeakerIdentifier
from app.audio.tencent_asr import TencentASR
from app.transcript_realtime import insert_speech_transcript_and_broadcast

logger = logging.getLogger(__name__)

# 0.5 秒的 PCM 字节数（16000Hz × 2bytes × 0.5s）
MIN_PCM_BYTES = int(16000 * 2 * 0.5)

# PCM reader 每次读取块大小（0.1 秒）
PCM_READ_CHUNK = 3200


class AudioService:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self._loop = asyncio.get_event_loop()
        self.identifier = SpeakerIdentifier(session_id)
        self.asr = TencentASR(session_id, self._on_asr_result, self._loop)
        self._ffmpeg_proc: subprocess.Popen | None = None
        self._reader_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    async def start(self, db: AsyncSession, user_ids: list[str]) -> None:
        """加载声纹 + 启动 ffmpeg 管道 + 启动腾讯 ASR"""
        # 1. 加载声纹
        await self.identifier.load_profiles(db, user_ids)

        # 2. 启动 ffmpeg 管道（WebM stdin → PCM stdout）
        try:
            self._ffmpeg_proc = subprocess.Popen(
                [
                    "ffmpeg",
                    "-loglevel", "quiet",
                    "-f", "webm",       # 输入格式：WebM
                    "-i", "pipe:0",     # 从 stdin 读
                    "-ar", "16000",     # 采样率 16kHz
                    "-ac", "1",         # 单声道
                    "-f", "s16le",      # 输出 PCM 16bit little-endian
                    "pipe:1",           # 输出到 stdout
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            logger.error("[AudioService] session=%s ffmpeg 未安装，音频处理不可用", self.session_id)
            return

        # 3. 启动 PCM reader 线程
        self._stop_event.clear()
        self._reader_thread = threading.Thread(
            target=self._pcm_reader,
            args=(self._ffmpeg_proc, self.asr, self._stop_event),
            daemon=True,
        )
        self._reader_thread.start()

        # 4. 启动腾讯 ASR
        self.asr.start()
        logger.info("[AudioService] session=%s 启动完成", self.session_id)

    async def handle_chunk(self, audio_bytes: bytes, mime_type: str = "audio/webm") -> None:
        """收到前端 audio_chunk，按格式路由处理"""
        # Native(Android) AAC：每块单独转 PCM，直接写 ASR
        if mime_type.startswith("audio/aac") or mime_type.startswith("audio/mp4"):
            try:
                pcm_bytes = await self._convert_aac_chunk_to_pcm(audio_bytes)
                if pcm_bytes:
                    self.asr.write(pcm_bytes)
            except Exception as e:
                logger.warning("[AudioService] session=%s AAC→PCM 转换失败: %s", self.session_id, e)
            return

        # Browser WebM：流式写入 ffmpeg 管道
        if self._ffmpeg_proc is None or self._ffmpeg_proc.stdin is None:
            return

        if self._ffmpeg_proc.poll() is not None:
            logger.error(
                "[AudioService] session=%s ffmpeg 进程已退出(returncode=%s)，本 chunk 丢弃",
                self.session_id, self._ffmpeg_proc.returncode,
            )
            return

        try:
            self._ffmpeg_proc.stdin.write(audio_bytes)
            self._ffmpeg_proc.stdin.flush()
        except (BrokenPipeError, OSError) as e:
            logger.warning("[AudioService] session=%s ffmpeg stdin 写入失败: %s", self.session_id, e)

    async def _convert_aac_chunk_to_pcm(self, aac_bytes: bytes) -> bytes:
        """将单个 ADTS AAC chunk 转换为 16kHz 单声道 s16le PCM"""
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-loglevel", "quiet",
            "-f", "aac",       # ADTS AAC 流式输入
            "-i", "pipe:0",
            "-ar", "16000",
            "-ac", "1",
            "-f", "s16le",
            "pipe:1",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await proc.communicate(aac_bytes)
        return stdout

    async def _on_asr_result(self, text: str, audio_bytes: bytes) -> None:
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
            )
        except Exception as e:
            logger.error("[AudioService] session=%s 写库/广播失败: %s", self.session_id, e)

    async def stop(self) -> None:
        """会话结束：关闭 ffmpeg → 等 reader 线程 → 停 ASR → 清声纹"""
        self._stop_event.set()

        # 关闭 ffmpeg stdin，触发 ffmpeg 自然退出
        if self._ffmpeg_proc is not None:
            try:
                if self._ffmpeg_proc.stdin:
                    self._ffmpeg_proc.stdin.close()
                self._ffmpeg_proc.wait(timeout=5)
            except Exception as e:
                logger.warning("[AudioService] session=%s ffmpeg 关闭异常: %s", self.session_id, e)
                self._ffmpeg_proc.kill()

        # 等 reader 线程结束
        if self._reader_thread is not None and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=5)

        # 停止腾讯 ASR
        self.asr.stop()

        # 清理声纹缓存
        self.identifier.clear()

        logger.info("[AudioService] session=%s 已停止", self.session_id)

    @staticmethod
    def _pcm_reader(
        proc: subprocess.Popen,
        asr: TencentASR,
        stop_event: threading.Event,
    ) -> None:
        """后台线程：持续从 ffmpeg stdout 读 PCM，转发给腾讯 ASR"""
        while not stop_event.is_set():
            try:
                data = proc.stdout.read(PCM_READ_CHUNK)
            except Exception:
                break
            if not data:
                break
            asr.write(data)


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
