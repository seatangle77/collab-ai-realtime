from __future__ import annotations

import sys
import types


resemblyzer_stub = types.ModuleType("resemblyzer")
resemblyzer_stub.VoiceEncoder = object
resemblyzer_stub.preprocess_wav = lambda path: []
sys.modules.setdefault("resemblyzer", resemblyzer_stub)

from backend.app import voice_profiles


def test_voice_audio_metadata_is_embedded_without_sidecar(tmp_path, monkeypatch):
    audio_path = tmp_path / "sample.webm"
    audio_path.write_bytes(b"fake-audio")

    captured: dict[str, object] = {}

    def fake_remux(path, *, metadata=None):
        captured["path"] = path
        captured["metadata"] = metadata
        return True

    monkeypatch.setattr(voice_profiles, "_remux_audio_file", fake_remux)
    monkeypatch.setattr(voice_profiles, "_probe_audio_duration_ms", lambda path: 1234)

    voice_profiles._finalize_voice_audio_file(
        audio_path,
        user_id="user-1",
        content_type="audio/webm;codecs=opus",
        public_url="/voice-audio/user-1/sample.webm",
        uploaded_by="user-1",
    )

    assert captured["path"] == audio_path
    metadata = captured["metadata"]
    assert metadata["user_id"] == "user-1"
    assert metadata["mime_type"] == "audio/webm;codecs=opus"
    assert metadata["duration_ms"] == 1234
    assert metadata["duration_sec"] == 1.234
    assert metadata["file_size_bytes"] == 10
    assert metadata["uploaded_by"] == "user-1"
    assert not (tmp_path / "sample.webm.json").exists()


def test_audio_extension_from_content_type_handles_codecs():
    assert voice_profiles._audio_extension_from_content_type("audio/webm;codecs=opus") == ".webm"
    assert voice_profiles._audio_extension_from_content_type("audio/x-wav") == ".wav"
    assert voice_profiles._audio_extension_from_content_type("audio/mp4") == ".m4a"
