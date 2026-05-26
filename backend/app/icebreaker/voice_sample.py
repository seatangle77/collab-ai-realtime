from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import tempfile
import uuid
import wave
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from resemblyzer import VoiceEncoder, preprocess_wav
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..config_voice import VOICE_AUDIO_BASE_DIR, VOICE_AUDIO_PUBLIC_BASE_URL
from .asr import (
    IcebreakerAudioDecodeError,
    decode_icebreaker_audio_to_wav,
    normalize_icebreaker_mime_type,
)

logger = logging.getLogger(__name__)

MIN_SAMPLE_DURATION_SEC = 1.0


@dataclass
class IcebreakerVoiceSampleResult:
    voice_sample_added: bool
    sample_url: str | None = None
    warnings: list[str] = field(default_factory=list)


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_json_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return [str(item) for item in parsed if str(item).strip()]
    return []


def _url_to_local_path(url: str) -> Path:
    relative = url.removeprefix(VOICE_AUDIO_PUBLIC_BASE_URL)
    return VOICE_AUDIO_BASE_DIR / relative.lstrip("/")


def _safe_part(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in value.strip())
    return cleaned[:80] or "unknown"


def _sample_filename(
    *,
    group_id: str,
    source: str,
    question_index: int | None,
    round_no: int | None,
    turn_index: int | None,
) -> str:
    parts = [
        "icebreaker",
        _safe_part(group_id),
        _safe_part(source),
    ]
    if question_index is not None:
        parts.append(f"q{question_index}")
    if round_no is not None:
        parts.append(f"r{round_no}")
    if turn_index is not None:
        parts.append(f"t{turn_index}")
    parts.append(uuid.uuid4().hex[:10])
    return "-".join(parts) + ".wav"


def _wav_duration_sec(wav_bytes: bytes) -> float:
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(wav_bytes)
        tmp_path = Path(tmp.name)
    try:
        with wave.open(str(tmp_path), "rb") as wav_file:
            frames = wav_file.getnframes()
            rate = wav_file.getframerate()
            return frames / float(rate or 1)
    finally:
        tmp_path.unlink(missing_ok=True)


def _save_wav_sample(
    *,
    user_id: str,
    wav_bytes: bytes,
    group_id: str,
    source: str,
    question_index: int | None,
    round_no: int | None,
    turn_index: int | None,
) -> str:
    dest_dir = VOICE_AUDIO_BASE_DIR / user_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = _sample_filename(
        group_id=group_id,
        source=source,
        question_index=question_index,
        round_no=round_no,
        turn_index=turn_index,
    )
    dest_path = dest_dir / filename
    dest_path.write_bytes(wav_bytes)
    return f"{VOICE_AUDIO_PUBLIC_BASE_URL}/{user_id}/{filename}"


def _convert_to_wav(src: Path) -> Path | None:
    if src.suffix.lower() == ".wav":
        return src

    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    tmp_path = Path(tmp.name)
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(src),
                "-ar",
                "16000",
                "-ac",
                "1",
                "-f",
                "wav",
                str(tmp_path),
            ],
            capture_output=True,
            timeout=60,
            check=False,
        )
        if result.returncode != 0:
            logger.warning(
                "[IcebreakerVoiceSample] ffmpeg convert failed path=%s stderr=%s",
                src,
                result.stderr.decode(errors="replace")[:300],
            )
            tmp_path.unlink(missing_ok=True)
            return None
        return tmp_path
    except Exception as exc:
        logger.warning("[IcebreakerVoiceSample] ffmpeg convert exception path=%s error=%s", src, exc)
        tmp_path.unlink(missing_ok=True)
        return None


def _generate_embedding_from_urls(sample_urls: list[str]) -> list[float]:
    encoder = VoiceEncoder()
    wavs = []
    tmp_files: list[Path] = []

    for url in sample_urls:
        path = _url_to_local_path(url)
        if not path.exists():
            logger.warning("[IcebreakerVoiceSample] sample file missing url=%s path=%s", url, path)
            continue
        try:
            wav_path = _convert_to_wav(path)
            if wav_path is None:
                continue
            if wav_path != path:
                tmp_files.append(wav_path)
            wavs.append(preprocess_wav(wav_path))
        except Exception as exc:
            logger.warning("[IcebreakerVoiceSample] sample preprocess failed url=%s error=%s", url, exc)
        finally:
            for tmp in tmp_files:
                tmp.unlink(missing_ok=True)
            tmp_files.clear()

    if not wavs:
        raise ValueError("no_valid_voice_samples")

    return encoder.embed_speaker(wavs).tolist()


async def _get_or_create_profile_row(db: AsyncSession, user_id: str) -> Mapping[str, Any]:
    result = await db.execute(
        text(
            """
            SELECT id, user_id, voice_embedding, sample_audio_urls, created_at,
                   embedding_status, embedding_updated_at
            FROM user_voice_profiles
            WHERE user_id = :user_id
            LIMIT 1
            """
        ),
        {"user_id": user_id},
    )
    row = result.mappings().first()
    if row:
        return row

    profile_id = f"vp{uuid.uuid4().hex[:12]}"
    insert_result = await db.execute(
        text(
            """
            INSERT INTO user_voice_profiles (id, user_id, sample_audio_urls, created_at)
            VALUES (:id, :user_id, CAST(:sample_audio_urls AS jsonb), :created_at)
            RETURNING id, user_id, voice_embedding, sample_audio_urls, created_at,
                      embedding_status, embedding_updated_at
            """
        ),
        {
            "id": profile_id,
            "user_id": user_id,
            "sample_audio_urls": json.dumps([]),
            "created_at": _utc_now_naive(),
        },
    )
    return insert_result.mappings().one()


async def add_icebreaker_voice_sample(
    *,
    db: AsyncSession,
    user_id: str,
    group_id: str,
    source: str,
    audio_bytes: bytes,
    mime_type: str,
    text_value: str,
    question_index: int | None = None,
    round_no: int | None = None,
    turn_index: int | None = None,
) -> IcebreakerVoiceSampleResult:
    warnings: list[str] = []
    if not text_value.strip():
        return IcebreakerVoiceSampleResult(False, warnings=["录音没有识别到文字，未加入声纹样本"])

    try:
        normalized_mime = normalize_icebreaker_mime_type(mime_type)
        wav_bytes = decode_icebreaker_audio_to_wav(audio_bytes, normalized_mime)
        duration_sec = _wav_duration_sec(wav_bytes)
    except IcebreakerAudioDecodeError:
        logger.exception("[IcebreakerVoiceSample] decode failed user_id=%s group_id=%s", user_id, group_id)
        return IcebreakerVoiceSampleResult(False, warnings=["录音解码失败，未加入声纹样本"])

    if duration_sec < MIN_SAMPLE_DURATION_SEC:
        return IcebreakerVoiceSampleResult(False, warnings=["录音太短，未加入声纹样本"])

    sample_url = _save_wav_sample(
        user_id=user_id,
        wav_bytes=wav_bytes,
        group_id=group_id,
        source=source,
        question_index=question_index,
        round_no=round_no,
        turn_index=turn_index,
    )

    row = await _get_or_create_profile_row(db, user_id)
    sample_urls = _parse_json_list(row.get("sample_audio_urls"))
    next_urls = [*sample_urls, sample_url]

    loop = asyncio.get_running_loop()
    try:
        embedding = await loop.run_in_executor(None, lambda: _generate_embedding_from_urls(next_urls))
    except Exception as exc:
        logger.warning(
            "[IcebreakerVoiceSample] embedding generation failed user_id=%s group_id=%s error=%s",
            user_id,
            group_id,
            exc,
        )
        return IcebreakerVoiceSampleResult(False, sample_url=sample_url, warnings=["声纹生成失败，未加入样本列表"])

    await db.execute(
        text(
            """
            UPDATE user_voice_profiles
            SET sample_audio_urls = CAST(:sample_audio_urls AS jsonb),
                voice_embedding = CAST(:voice_embedding AS jsonb),
                embedding_status = 'ready',
                embedding_updated_at = NOW()
            WHERE id = :id
            """
        ),
        {
            "id": row["id"],
            "sample_audio_urls": json.dumps(next_urls),
            "voice_embedding": json.dumps(embedding),
        },
    )
    await db.commit()
    return IcebreakerVoiceSampleResult(True, sample_url=sample_url, warnings=warnings)
