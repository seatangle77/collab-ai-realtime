from __future__ import annotations

import asyncio
import json
from datetime import datetime

from backend.app import session_recordings


def test_session_recording_writes_single_audio_file(tmp_path, monkeypatch):
    async def fake_meta(session_id: str):
        return {
            "session_id": session_id,
            "started_at": datetime(2026, 5, 29, 14, 30, 12),
            "created_at": None,
            "group_name": "第三组/测试",
        }

    monkeypatch.setattr(session_recordings, "SESSION_RECORDINGS_DIR", tmp_path)
    monkeypatch.setattr(session_recordings, "_get_session_recording_meta", fake_meta)
    session_recordings._session_files.clear()
    session_recordings._session_locks.clear()

    async def run() -> None:
        await session_recordings.save_session_audio_chunk(
            "sesabc123",
            user_id="u1",
            seq=1,
            mime_type="audio/webm",
            audio_bytes=b"abc",
            duration_ms=1000,
        )
        await session_recordings.save_session_audio_chunk(
            "sesabc123",
            user_id="u1",
            seq=2,
            mime_type="audio/webm",
            audio_bytes=b"def",
            duration_ms=1500,
        )
        await session_recordings.finalize_session_recording("sesabc123")

    asyncio.run(run())

    session_file = tmp_path / "20260529-143012_第三组_测试_sesabc123.webm"
    assert session_file.read_bytes() == b"abcdef"
    sidecar = json.loads((tmp_path / "20260529-143012_第三组_测试_sesabc123.webm.json").read_text())
    assert sidecar["session_id"] == "sesabc123"
    assert sidecar["recording_file"] == session_file.name
    assert sidecar["mime_type"] == "audio/webm"
    assert sidecar["duration_ms"] == 2500
    assert sidecar["duration_sec"] == 2.5
    assert sidecar["chunk_count"] == 2
    assert sidecar["byte_count"] == 6
    assert sidecar["file_size_bytes"] == 6
    assert sidecar["first_seq"] == 1
    assert sidecar["last_seq"] == 2
    assert not (tmp_path / "20260529-143012_第三组_测试_sesabc123").exists()
