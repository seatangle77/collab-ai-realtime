"""
破冰声纹样本单元测试。

运行方式（在 backend/ 目录下）：
  python tests/test_icebreaker_voice_sample.py

这些测试不调用真实 ASR、ffmpeg 或 Resemblyzer；只验证破冰 helper 对
user_voice_profiles 的追加与重算写库行为。
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

env_path = BACKEND_DIR / ".env.local"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from app.icebreaker import voice_sample as mod

PASS = 0
FAIL = 0


def _log(ok: bool, msg: str, extra: Any = None) -> None:
    global PASS, FAIL
    print(f"{'✅' if ok else '❌'} {msg}")
    if not ok and extra is not None:
        print("   详情:", extra)
    if ok:
        PASS += 1
    else:
        FAIL += 1


class _Result:
    def __init__(self, row: dict[str, Any] | None = None):
        self._row = row

    def mappings(self):
        return self

    def first(self):
        return self._row

    def one(self):
        if self._row is None:
            raise AssertionError("expected one row")
        return self._row


class _MockDB:
    def __init__(self, row: dict[str, Any] | None = None):
        self.row = row
        self.updated: dict[str, Any] | None = None
        self.commits = 0

    async def execute(self, query, params=None):
        sql = str(query)
        params = params or {}
        if "SELECT id, user_id, voice_embedding, sample_audio_urls" in sql:
            return _Result(self.row)
        if "INSERT INTO user_voice_profiles" in sql:
            self.row = {
                "id": params["id"],
                "user_id": params["user_id"],
                "voice_embedding": None,
                "sample_audio_urls": [],
                "created_at": params["created_at"],
                "embedding_status": "not_generated",
                "embedding_updated_at": None,
            }
            return _Result(self.row)
        if "UPDATE user_voice_profiles" in sql:
            self.updated = dict(params)
            if self.row is not None:
                self.row["sample_audio_urls"] = params["sample_audio_urls"]
                self.row["voice_embedding"] = params["voice_embedding"]
                self.row["embedding_status"] = "ready"
            return _Result(self.row)
        raise AssertionError(f"unexpected SQL: {sql}")

    async def commit(self):
        self.commits += 1


class _Patch:
    def __init__(self):
        self.originals: dict[str, Any] = {}

    def set(self, name: str, value: Any) -> None:
        self.originals[name] = getattr(mod, name)
        setattr(mod, name, value)

    def restore(self) -> None:
        for name, value in self.originals.items():
            setattr(mod, name, value)


def _patch_fast_audio_pipeline(sample_url: str, embedding: list[float]) -> _Patch:
    patch = _Patch()
    patch.set("decode_icebreaker_audio_to_wav", lambda audio_bytes, mime_type: b"fake-wav")
    patch.set("_wav_duration_sec", lambda wav_bytes: 2.0)
    patch.set(
        "_save_wav_sample",
        lambda **kwargs: sample_url,
    )
    patch.set("_generate_embedding_from_urls", lambda urls: embedding)
    return patch


async def test_appends_sample_and_regenerates_embedding() -> None:
    sample_url = "http://127.0.0.1:8000/audio/voice-profiles/u1/icebreaker.wav"
    embedding = [0.1, 0.2, 0.3]
    patch = _patch_fast_audio_pipeline(sample_url, embedding)
    db = _MockDB(
        {
            "id": "vp-existing",
            "user_id": "u1",
            "voice_embedding": [0.0],
            "sample_audio_urls": ["http://example.com/old.wav"],
            "created_at": None,
            "embedding_status": "ready",
            "embedding_updated_at": None,
        }
    )

    try:
        result = await mod.add_icebreaker_voice_sample(
            db=db,
            user_id="u1",
            group_id="g1",
            source="intro",
            audio_bytes=b"fake-audio",
            mime_type="audio/webm",
            text_value="我是测试用户",
            question_index=1,
        )
    finally:
        patch.restore()

    ok = result.voice_sample_added is True
    ok &= db.updated is not None
    ok &= "old.wav" in db.updated["sample_audio_urls"]
    ok &= sample_url in db.updated["sample_audio_urls"]
    ok &= db.updated["voice_embedding"] == "[0.1, 0.2, 0.3]"
    ok &= db.commits == 1
    _log(ok, "破冰样本追加旧 URL 并重算 voice_embedding", {"result": result, "updated": db.updated})


async def test_creates_profile_when_missing() -> None:
    sample_url = "http://127.0.0.1:8000/audio/voice-profiles/u-new/icebreaker.wav"
    patch = _patch_fast_audio_pipeline(sample_url, [0.4, 0.5])
    db = _MockDB()

    try:
        result = await mod.add_icebreaker_voice_sample(
            db=db,
            user_id="u-new",
            group_id="g1",
            source="story",
            audio_bytes=b"fake-audio",
            mime_type="audio/webm",
            text_value="故事开始了",
            round_no=1,
            turn_index=1,
        )
    finally:
        patch.restore()

    ok = result.voice_sample_added is True
    ok &= db.row is not None and db.row["user_id"] == "u-new"
    ok &= db.updated is not None and sample_url in db.updated["sample_audio_urls"]
    ok &= db.commits == 1
    _log(ok, "无 profile 时破冰样本会创建 user_voice_profiles 并写入样本", {"row": db.row, "updated": db.updated})


async def test_empty_text_is_not_added() -> None:
    db = _MockDB(
        {
            "id": "vp-existing",
            "user_id": "u1",
            "voice_embedding": None,
            "sample_audio_urls": [],
            "created_at": None,
            "embedding_status": "not_generated",
            "embedding_updated_at": None,
        }
    )
    result = await mod.add_icebreaker_voice_sample(
        db=db,
        user_id="u1",
        group_id="g1",
        source="intro",
        audio_bytes=b"fake-audio",
        mime_type="audio/webm",
        text_value="",
    )

    ok = result.voice_sample_added is False
    ok &= db.updated is None
    ok &= db.commits == 0
    ok &= len(result.warnings) > 0
    _log(ok, "ASR 空文本不会加入声纹样本", {"result": result})


async def main() -> None:
    print("=" * 60)
    print("Icebreaker Voice Sample Tests")
    print("=" * 60)

    await test_appends_sample_and_regenerates_embedding()
    await test_creates_profile_when_missing()
    await test_empty_text_is_not_added()

    print("=" * 60)
    total = PASS + FAIL
    print(f"{'✅' if FAIL == 0 else '❌'} {PASS}/{total} 通过")
    print("=" * 60)
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
