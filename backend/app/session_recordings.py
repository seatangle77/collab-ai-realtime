from __future__ import annotations

import asyncio
import os
import re
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


async def save_session_audio_chunk(
    session_id: str,
    *,
    user_id: str,
    seq: int,
    mime_type: str,
    audio_bytes: bytes,
) -> None:
    lock = _get_session_lock(session_id)
    async with lock:
        session_file = await _resolve_session_file(session_id, mime_type)
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
            return session_file
        finally:
            _session_files.pop(session_id, None)
            _session_locks.pop(session_id, None)
