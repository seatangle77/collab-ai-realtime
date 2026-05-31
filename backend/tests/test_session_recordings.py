from __future__ import annotations

import asyncio
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
    captured: dict[str, object] = {}

    def fake_remux(path, *, metadata=None):
        captured["path"] = path
        captured["metadata"] = metadata
        return True

    monkeypatch.setattr(session_recordings, "_remux_recording_file", fake_remux)
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
    assert captured["path"] == session_file
    metadata = captured["metadata"]
    assert metadata["session_id"] == "sesabc123"
    assert metadata["mime_type"] == "audio/webm"
    assert metadata["duration_ms"] == 2500
    assert metadata["duration_sec"] == 2.5
    assert metadata["chunk_count"] == 2
    assert metadata["byte_count"] == 6
    assert metadata["first_seq"] == 1
    assert metadata["last_seq"] == 2
    assert not (tmp_path / "20260529-143012_第三组_测试_sesabc123.webm.json").exists()
    assert not (tmp_path / "20260529-143012_第三组_测试_sesabc123").exists()
