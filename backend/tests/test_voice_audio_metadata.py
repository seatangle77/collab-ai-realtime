from __future__ import annotations

import json
import sys
import types


resemblyzer_stub = types.ModuleType("resemblyzer")
resemblyzer_stub.VoiceEncoder = object
resemblyzer_stub.preprocess_wav = lambda path: []
sys.modules.setdefault("resemblyzer", resemblyzer_stub)

from backend.app import voice_profiles


def test_voice_audio_metadata_sidecar_is_written(tmp_path, monkeypatch):
    audio_path = tmp_path / "sample.webm"
    audio_path.write_bytes(b"fake-audio")

    monkeypatch.setattr(voice_profiles, "_remux_audio_file", lambda path: True)
    monkeypatch.setattr(voice_profiles, "_probe_audio_duration_ms", lambda path: 1234)

    voice_profiles._write_voice_audio_metadata(
        audio_path,
        user_id="user-1",
        content_type="audio/webm;codecs=opus",
        public_url="/voice-audio/user-1/sample.webm",
        uploaded_by="user-1",
    )

    metadata = json.loads((tmp_path / "sample.webm.json").read_text())
    assert metadata["user_id"] == "user-1"
    assert metadata["recording_file"] == "sample.webm"
    assert metadata["mime_type"] == "audio/webm;codecs=opus"
    assert metadata["duration_ms"] == 1234
    assert metadata["duration_sec"] == 1.234
    assert metadata["file_size_bytes"] == 10
    assert metadata["uploaded_by"] == "user-1"
    assert metadata["remuxed"] is True


def test_audio_extension_from_content_type_handles_codecs():
    assert voice_profiles._audio_extension_from_content_type("audio/webm;codecs=opus") == ".webm"
    assert voice_profiles._audio_extension_from_content_type("audio/x-wav") == ".wav"
    assert voice_profiles._audio_extension_from_content_type("audio/mp4") == ".m4a"
