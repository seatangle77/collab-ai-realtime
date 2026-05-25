from __future__ import annotations

import asyncio
import logging
import subprocess
import uuid

from .audio.tencent_asr import TencentASR
from .settings import tencent_asr_settings

logger = logging.getLogger(__name__)

MAX_ICEBREAKER_AUDIO_BYTES = 12 * 1024 * 1024
ALLOWED_ICEBREAKER_MIME_TYPES = {"audio/webm", "audio/aac", "audio/mp4"}
PCM_CHUNK_BYTES = 3200
ASR_RESULT_TIMEOUT_SEC = 18
ASR_FLUSH_WAIT_SEC = 1.2


class IcebreakerASRError(RuntimeError):
    pass


class IcebreakerAudioDecodeError(IcebreakerASRError):
    pass


class IcebreakerASRUnavailable(IcebreakerASRError):
    pass


def normalize_icebreaker_mime_type(mime_type: str) -> str:
    normalized = (mime_type or "").split(";", 1)[0].strip().lower()
    if normalized not in ALLOWED_ICEBREAKER_MIME_TYPES:
        raise IcebreakerAudioDecodeError("unsupported_audio")
    return normalized


def _ffmpeg_input_format(mime_type: str) -> str:
    if mime_type == "audio/webm":
        return "webm"
    if mime_type == "audio/aac":
        return "aac"
    if mime_type == "audio/mp4":
        return "mp4"
    raise IcebreakerAudioDecodeError("unsupported_audio")


def decode_icebreaker_audio_to_pcm(audio_bytes: bytes, mime_type: str) -> bytes:
    if not audio_bytes:
        raise IcebreakerAudioDecodeError("empty_audio")
    if len(audio_bytes) > MAX_ICEBREAKER_AUDIO_BYTES:
        raise IcebreakerAudioDecodeError("audio_too_large")

    input_format = _ffmpeg_input_format(mime_type)
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                input_format,
                "-i",
                "pipe:0",
                "-ar",
                "16000",
                "-ac",
                "1",
                "-f",
                "s16le",
                "pipe:1",
            ],
            input=audio_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
            check=False,
        )
    except FileNotFoundError as exc:
        raise IcebreakerAudioDecodeError("ffmpeg_missing") from exc
    except subprocess.TimeoutExpired as exc:
        raise IcebreakerAudioDecodeError("decode_timeout") from exc

    if result.returncode != 0 or not result.stdout:
        logger.warning("[IcebreakerASR] ffmpeg decode failed: %s", result.stderr.decode("utf-8", errors="ignore")[:300])
        raise IcebreakerAudioDecodeError("decode_failed")
    return result.stdout


async def transcribe_icebreaker_audio(
    *,
    audio_bytes: bytes,
    mime_type: str,
    turn_id: str | None = None,
) -> str:
    """
    破冰专用临时转写：audio -> text。
    不写 speech_transcripts，不广播，不进入正式讨论链路。
    """
    if not (
        tencent_asr_settings.appid
        and tencent_asr_settings.secret_id
        and tencent_asr_settings.secret_key
    ):
        raise IcebreakerASRUnavailable("tencent_asr_not_configured")

    normalized_mime = normalize_icebreaker_mime_type(mime_type)
    logger.info(
        "[IcebreakerASR] transcribe begin turn_id=%s mime_type=%s audio_bytes=%d",
        turn_id,
        normalized_mime,
        len(audio_bytes),
    )
    pcm_bytes = decode_icebreaker_audio_to_pcm(audio_bytes, normalized_mime)
    logger.info(
        "[IcebreakerASR] decode ok turn_id=%s pcm_bytes=%d",
        turn_id,
        len(pcm_bytes),
    )

    loop = asyncio.get_running_loop()
    result_queue: asyncio.Queue[str] = asyncio.Queue()
    session_id = f"icebreaker-{turn_id or uuid.uuid4().hex[:8]}"

    async def on_result(text: str, _audio_bytes: bytes, segment_key: str | None = None) -> None:
        clean = text.strip()
        if clean:
            await result_queue.put(clean)

    async def on_partial_result(segment_key: str, text: str, is_final: bool) -> None:
        return None

    asr = TencentASR(session_id, on_result, on_partial_result, loop, enable_reconnect=False)
    try:
        asr.start()
        # 给 websocket 一点连接时间；正式讨论链路是长连接，这里是短任务。
        await asyncio.sleep(0.25)

        for offset in range(0, len(pcm_bytes), PCM_CHUNK_BYTES):
            asr.write(pcm_bytes[offset: offset + PCM_CHUNK_BYTES])
            await asyncio.sleep(0.01)

        await asyncio.sleep(ASR_FLUSH_WAIT_SEC)

        texts: list[str] = []
        while True:
            try:
                texts.append(result_queue.get_nowait())
            except asyncio.QueueEmpty:
                break

        if not texts:
            try:
                first = await asyncio.wait_for(result_queue.get(), timeout=ASR_RESULT_TIMEOUT_SEC)
                texts.append(first)
            except asyncio.TimeoutError as exc:
                raise IcebreakerASRUnavailable("asr_timeout") from exc

        final_text = "".join(texts).strip()
        logger.info(
            "[IcebreakerASR] transcribe done turn_id=%s text_len=%d text_preview=%s",
            turn_id,
            len(final_text),
            final_text[:80],
        )
        return final_text
    finally:
        asr.stop()
