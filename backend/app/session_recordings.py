from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from sqlalchemy import text

from .db import get_sessionmaker
from .settings import BACKEND_DIR

SESSION_RECORDINGS_DIR = Path(
    os.getenv("SESSION_RECORDINGS_DIR", str(BACKEND_DIR.parent / "local-session-full-recordings"))
).expanduser()

_session_locks: dict[str, asyncio.Lock] = {}
_session_files: dict[str, Path] = {}
_session_stats: dict[str, dict[str, Any]] = {}

_logger = logging.getLogger(__name__)


def _safe_path_part(value: str, *, fallback: str) -> str:
    text_value = (value or "").strip()
    if not text_value:
        text_value = fallback
    text_value = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", text_value)
    text_value = re.sub(r"\s+", "_", text_value)
    text_value = text_value.strip("._ ")
    return text_value[:80] or fallback


def _recording_extension(mime_type: str) -> str:
    normalized = mime_type.split(";", 1)[0].strip().lower()
    if normalized == "audio/aac":
        return "aac"
    if normalized == "audio/mp4":
        return "m4a"
    if normalized == "audio/ogg":
        return "ogg"
    return "webm"


def _get_session_lock(session_id: str) -> asyncio.Lock:
    lock = _session_locks.get(session_id)
    if lock is None:
        lock = asyncio.Lock()
        _session_locks[session_id] = lock
    return lock


async def _get_session_recording_meta(session_id: str) -> Mapping[str, Any]:
    session_factory = get_sessionmaker()
    async with session_factory() as db:
        result = await db.execute(
            text(
                """
                SELECT
                    cs.id AS session_id,
                    cs.started_at,
                    cs.created_at,
                    g.name AS group_name
                FROM chat_sessions AS cs
                LEFT JOIN groups AS g ON g.id = cs.group_id
                WHERE cs.id = :session_id
                """
            ),
            {"session_id": session_id},
        )
        row = result.mappings().first()
    if row:
        return row
    return {
        "session_id": session_id,
        "started_at": None,
        "created_at": None,
        "group_name": "unknown_group",
    }


def _format_recording_timestamp(value: Any) -> str:
    dt: datetime
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.strftime("%Y%m%d-%H%M%S")


async def _resolve_session_file(session_id: str, mime_type: str) -> Path:
    cached = _session_files.get(session_id)
    if cached is not None:
        return cached

    safe_session_id = _safe_path_part(session_id, fallback="session")
    existing = sorted(SESSION_RECORDINGS_DIR.glob(f"*_{safe_session_id}.*"))
    if existing:
        _session_files[session_id] = existing[0]
        return existing[0]

    meta = await _get_session_recording_meta(session_id)
    timestamp = _format_recording_timestamp(meta.get("started_at") or meta.get("created_at"))
    group_name = _safe_path_part(str(meta.get("group_name") or ""), fallback="unknown_group")
    extension = _recording_extension(mime_type)
    session_file = SESSION_RECORDINGS_DIR / f"{timestamp}_{group_name}_{safe_session_id}.{extension}"
    _session_files[session_id] = session_file
    return session_file


def _write_audio_chunk(
    session_file: Path,
    *,
    audio_bytes: bytes,
) -> None:
    session_file.parent.mkdir(parents=True, exist_ok=True)
    with session_file.open("ab") as audio_file:
        audio_file.write(audio_bytes)


def _normalize_duration_ms(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value > 0:
        return int(round(value))
    return None


def _update_session_stats(
    session_id: str,
    *,
    seq: int,
    mime_type: str,
    audio_bytes: bytes,
    duration_ms: int | None,
) -> None:
    stats = _session_stats.setdefault(
        session_id,
        {
            "chunk_count": 0,
            "byte_count": 0,
            "duration_ms": 0,
            "first_seq": None,
            "last_seq": None,
            "mime_type": mime_type,
        },
    )
    stats["chunk_count"] += 1
    stats["byte_count"] += len(audio_bytes)
    stats["last_seq"] = seq
    stats["mime_type"] = mime_type
    if stats["first_seq"] is None:
        stats["first_seq"] = seq
    if duration_ms is not None:
        stats["duration_ms"] += duration_ms


def _write_recording_sidecar(session_file: Path, *, session_id: str, stats: Mapping[str, Any] | None) -> None:
    if not stats:
        return

    duration_ms = int(stats.get("duration_ms") or 0)
    payload = {
        "session_id": session_id,
        "recording_file": session_file.name,
        "mime_type": stats.get("mime_type"),
        "duration_ms": duration_ms,
        "duration_sec": round(duration_ms / 1000, 3) if duration_ms > 0 else None,
        "chunk_count": stats.get("chunk_count", 0),
        "byte_count": stats.get("byte_count", session_file.stat().st_size if session_file.exists() else 0),
        "file_size_bytes": session_file.stat().st_size if session_file.exists() else 0,
        "first_seq": stats.get("first_seq"),
        "last_seq": stats.get("last_seq"),
        "finalized_at": datetime.now(timezone.utc).isoformat(),
    }
    sidecar_file = session_file.with_suffix(f"{session_file.suffix}.json")
    sidecar_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _remux_recording_file(session_file: Path) -> bool:
    if session_file.suffix.lower() not in {".webm", ".m4a", ".mp4", ".ogg"}:
        return False
    if shutil.which("ffmpeg") is None:
        return False

    temp_file = session_file.with_name(f"{session_file.stem}.remuxing{session_file.suffix}")
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(session_file),
                "-map",
                "0",
                "-c",
                "copy",
                str(temp_file),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
        if result.returncode != 0 or not temp_file.exists() or temp_file.stat().st_size == 0:
            stderr = result.stderr.decode("utf-8", errors="ignore")[:500]
            _logger.warning("会话录音重封装失败 file=%s stderr=%s", session_file, stderr)
            return False
        temp_file.replace(session_file)
        return True
    except Exception as exc:
        _logger.warning("会话录音重封装异常 file=%s error=%s", session_file, exc)
        return False
    finally:
        if temp_file.exists():
            temp_file.unlink(missing_ok=True)


async def save_session_audio_chunk(
    session_id: str,
    *,
    user_id: str,
    seq: int,
    mime_type: str,
    audio_bytes: bytes,
    duration_ms: int | float | None = None,
) -> None:
    lock = _get_session_lock(session_id)
    async with lock:
        session_file = await _resolve_session_file(session_id, mime_type)
        normalized_duration_ms = _normalize_duration_ms(duration_ms)
        _update_session_stats(
            session_id,
            seq=seq,
            mime_type=mime_type,
            audio_bytes=audio_bytes,
            duration_ms=normalized_duration_ms,
        )
        await asyncio.to_thread(
            _write_audio_chunk,
            session_file,
            audio_bytes=audio_bytes,
        )


async def finalize_session_recording(session_id: str) -> Path | None:
    lock = _get_session_lock(session_id)
    async with lock:
        try:
            session_file = _session_files.get(session_id)
            if session_file is None:
                matches = sorted(SESSION_RECORDINGS_DIR.glob(f"*_{_safe_path_part(session_id, fallback='session')}.*"))
                session_file = matches[0] if matches else None
            if session_file is None or not session_file.exists():
                return None
            stats = _session_stats.get(session_id)
            await asyncio.to_thread(_remux_recording_file, session_file)
            await asyncio.to_thread(
                _write_recording_sidecar,
                session_file,
                session_id=session_id,
                stats=stats,
            )
            return session_file
        finally:
            _session_files.pop(session_id, None)
            _session_locks.pop(session_id, None)
            _session_stats.pop(session_id, None)
