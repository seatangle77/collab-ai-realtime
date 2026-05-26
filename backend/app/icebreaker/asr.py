from __future__ import annotations

import asyncio
import base64
import datetime as dt
import hashlib
import hmac
import json
import logging
import os
import subprocess
import time
import urllib.error
import urllib.request
import uuid

from ..settings import tencent_asr_settings

logger = logging.getLogger(__name__)

MAX_ICEBREAKER_AUDIO_BYTES = 12 * 1024 * 1024
ALLOWED_ICEBREAKER_MIME_TYPES = {"audio/webm", "audio/aac", "audio/mp4"}
TENCENT_SENTENCE_ENDPOINT = "https://asr.tencentcloudapi.com"
TENCENT_SENTENCE_HOST = "asr.tencentcloudapi.com"
TENCENT_SENTENCE_SERVICE = "asr"
TENCENT_SENTENCE_ACTION = "SentenceRecognition"
TENCENT_SENTENCE_VERSION = "2019-06-14"
TENCENT_SENTENCE_TIMEOUT_SEC = 20
MAX_TENCENT_SENTENCE_WAV_BYTES = 3 * 1024 * 1024


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


def decode_icebreaker_audio_to_wav(audio_bytes: bytes, mime_type: str) -> bytes:
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
                "-acodec",
                "pcm_s16le",
                "-f",
                "wav",
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


def _hmac_sha256(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


def _build_tencent_authorization(*, payload: str, timestamp: int) -> str:
    canonical_uri = "/"
    canonical_query_string = ""
    canonical_headers = f"content-type:application/json; charset=utf-8\nhost:{TENCENT_SENTENCE_HOST}\n"
    signed_headers = "content-type;host"
    hashed_request_payload = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    canonical_request = "\n".join(
        [
            "POST",
            canonical_uri,
            canonical_query_string,
            canonical_headers,
            signed_headers,
            hashed_request_payload,
        ]
    )

    request_date = dt.datetime.fromtimestamp(timestamp, dt.UTC).strftime("%Y-%m-%d")
    credential_scope = f"{request_date}/{TENCENT_SENTENCE_SERVICE}/tc3_request"
    hashed_canonical_request = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
    string_to_sign = "\n".join(
        [
            "TC3-HMAC-SHA256",
            str(timestamp),
            credential_scope,
            hashed_canonical_request,
        ]
    )

    secret_date = _hmac_sha256(("TC3" + tencent_asr_settings.secret_key).encode("utf-8"), request_date)
    secret_service = _hmac_sha256(secret_date, TENCENT_SENTENCE_SERVICE)
    secret_signing = _hmac_sha256(secret_service, "tc3_request")
    signature = hmac.new(secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    return (
        "TC3-HMAC-SHA256 "
        f"Credential={tencent_asr_settings.secret_id}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, "
        f"Signature={signature}"
    )


def _call_tencent_sentence_recognition(*, wav_bytes: bytes, turn_id: str) -> str:
    engine = os.getenv("ICEBREAKER_ASR_ENGINE", "16k_zh").strip() or "16k_zh"
    region = os.getenv("ICEBREAKER_TENCENT_REGION", "ap-shanghai").strip() or "ap-shanghai"
    filter_modal = int(os.getenv("ICEBREAKER_ASR_FILTER_MODAL", "2"))
    filter_punc = int(os.getenv("ICEBREAKER_ASR_FILTER_PUNC", "0"))

    payload_dict = {
        "SubServiceType": 2,
        "ProjectId": 0,
        "EngSerViceType": engine,
        "SourceType": 1,
        "VoiceFormat": "wav",
        "Data": base64.b64encode(wav_bytes).decode("ascii"),
        "DataLen": len(wav_bytes),
        "UsrAudioKey": turn_id or f"icebreaker-{uuid.uuid4().hex[:8]}",
        "FilterModal": filter_modal,
        "FilterPunc": filter_punc,
        "ConvertNumMode": 1,
        "WordInfo": 0,
    }
    payload = json.dumps(payload_dict, ensure_ascii=False, separators=(",", ":"))
    timestamp = int(time.time())
    headers = {
        "Authorization": _build_tencent_authorization(payload=payload, timestamp=timestamp),
        "Content-Type": "application/json; charset=utf-8",
        "Host": TENCENT_SENTENCE_HOST,
        "X-TC-Action": TENCENT_SENTENCE_ACTION,
        "X-TC-Version": TENCENT_SENTENCE_VERSION,
        "X-TC-Timestamp": str(timestamp),
        "X-TC-Region": region,
    }

    logger.info(
        "[IcebreakerASR] sentence request turn_id=%s engine=%s region=%s wav_bytes=%d filter_modal=%d",
        turn_id,
        engine,
        region,
        len(wav_bytes),
        filter_modal,
    )

    request = urllib.request.Request(
        TENCENT_SENTENCE_ENDPOINT,
        data=payload.encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TENCENT_SENTENCE_TIMEOUT_SEC) as response:
            response_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="ignore")
        logger.warning(
            "[IcebreakerASR] sentence http_error turn_id=%s status=%s body=%s",
            turn_id,
            exc.code,
            response_body[:500],
        )
        raise IcebreakerASRUnavailable("sentence_recognition_http_error") from exc
    except urllib.error.URLError as exc:
        logger.warning("[IcebreakerASR] sentence network_error turn_id=%s error=%s", turn_id, exc)
        raise IcebreakerASRUnavailable("sentence_recognition_network_error") from exc

    try:
        data = json.loads(response_body)
    except json.JSONDecodeError as exc:
        logger.warning("[IcebreakerASR] sentence invalid_json turn_id=%s body=%s", turn_id, response_body[:500])
        raise IcebreakerASRUnavailable("sentence_recognition_invalid_json") from exc

    response_data = data.get("Response") or {}
    request_id = response_data.get("RequestId", "")
    if "Error" in response_data:
        error = response_data.get("Error") or {}
        logger.warning(
            "[IcebreakerASR] sentence api_error turn_id=%s request_id=%s code=%s message=%s",
            turn_id,
            request_id,
            error.get("Code"),
            error.get("Message"),
        )
        raise IcebreakerASRUnavailable(str(error.get("Code") or "sentence_recognition_api_error"))

    text = str(response_data.get("Result") or "").strip()
    logger.info(
        "[IcebreakerASR] sentence response turn_id=%s request_id=%s duration_ms=%s text_len=%d text_preview=%s",
        turn_id,
        request_id,
        response_data.get("AudioDuration"),
        len(text),
        text[:80],
    )
    return text


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
    wav_bytes = decode_icebreaker_audio_to_wav(audio_bytes, normalized_mime)
    if len(wav_bytes) > MAX_TENCENT_SENTENCE_WAV_BYTES:
        raise IcebreakerAudioDecodeError("audio_too_large_for_sentence_recognition")

    logger.info(
        "[IcebreakerASR] decode ok turn_id=%s wav_bytes=%d",
        turn_id,
        len(wav_bytes),
    )

    loop = asyncio.get_running_loop()
    session_id = f"icebreaker-{turn_id or uuid.uuid4().hex[:8]}"
    final_text = await loop.run_in_executor(
        None,
        lambda: _call_tencent_sentence_recognition(wav_bytes=wav_bytes, turn_id=session_id),
    )
    logger.info(
        "[IcebreakerASR] transcribe done turn_id=%s text_len=%d text_preview=%s",
        turn_id,
        len(final_text),
        final_text[:80],
    )
    return final_text
