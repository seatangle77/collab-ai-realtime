from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app import transcript_cache

PASS = 0
FAIL = 0


def _log(ok: bool, msg: str, extra: object = None) -> None:
    global PASS, FAIL
    print(f"{'✅' if ok else '❌'} {msg}")
    if not ok and extra is not None:
        print("   详情:", extra)
    if ok:
        PASS += 1
    else:
        FAIL += 1


class FakePipeline:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def zadd(self, *args, **kwargs):
        self.calls.append(("zadd", args, kwargs))

    async def zremrangebyscore(self, *args, **kwargs):
        self.calls.append(("zremrangebyscore", args, kwargs))

    async def expire(self, *args, **kwargs):
        self.calls.append(("expire", args, kwargs))

    async def execute(self):
        self.calls.append(("execute", tuple(), {}))


class FakeRedis:
    def __init__(self, rows=None, raise_on_read: bool = False) -> None:
        self.rows = rows or []
        self.raise_on_read = raise_on_read
        self.pipeline_obj = FakePipeline()
        self.zrange_calls: list[tuple[str, int, int]] = []

    def pipeline(self, transaction: bool = False):
        return self.pipeline_obj

    async def zrangebyscore(self, key: str, min_score: int, max_score: int):
        self.zrange_calls.append((key, min_score, max_score))
        if self.raise_on_read:
            raise RuntimeError("redis read failed")
        return self.rows


async def test_append_transcript_to_cache_is_noop_without_redis():
    transcript = {
        "transcript_id": "t1",
        "text": "hello",
        "start": datetime.now(timezone.utc).isoformat(),
        "end": datetime.now(timezone.utc).isoformat(),
    }
    with patch.object(transcript_cache, "get_redis_client", lambda: None):
        await transcript_cache.append_transcript_to_cache("s1", transcript)


async def test_append_transcript_to_cache_writes_sorted_set_and_trims():
    fake = FakeRedis()
    end = datetime(2026, 4, 8, 12, 0, 0, tzinfo=timezone.utc)
    transcript = {
        "transcript_id": "t1",
        "user_id": "u1",
        "text": "hello",
        "start": (end - timedelta(seconds=2)).isoformat(),
        "end": end.isoformat(),
        "duration": 2,
    }

    with patch.object(transcript_cache, "get_redis_client", lambda: fake):
        await transcript_cache.append_transcript_to_cache("s1", transcript)

    calls = fake.pipeline_obj.calls
    assert [name for name, _, _ in calls] == ["zadd", "zremrangebyscore", "expire", "execute"]
    assert calls[0][1][0] == "transcript:session:s1"
    score = int(end.timestamp() * 1000)
    assert list(calls[0][1][1].values()) == [score]
    assert calls[1][1] == ("transcript:session:s1", 0, score - (900 * 1000))
    assert calls[2][1] == ("transcript:session:s1", 3600)


async def test_append_transcript_to_cache_skips_when_timestamp_missing():
    fake = FakeRedis()
    with patch.object(transcript_cache, "get_redis_client", lambda: fake):
        await transcript_cache.append_transcript_to_cache("s1", {"transcript_id": "t1", "text": "hello"})
    assert fake.pipeline_obj.calls == []


async def test_get_cached_transcripts_in_window_returns_empty_without_redis():
    with patch.object(transcript_cache, "get_redis_client", lambda: None):
        rows = await transcript_cache.get_cached_transcripts_in_window(
            "s1",
            datetime.now(timezone.utc) - timedelta(seconds=120),
            datetime.now(timezone.utc),
        )
    assert rows == []


async def test_get_cached_transcripts_in_window_reads_valid_rows_and_skips_invalid_json():
    fake = FakeRedis(
        rows=[
            '{"transcript_id":"t1","user_id":"u1","text":"hello","start":"2026-04-08T12:00:00+00:00","end":"2026-04-08T12:00:02+00:00","duration":2}',
            'not-json',
            '{"transcript_id":"t2","user_id":"u2","text":"world","start":"2026-04-08T12:00:03+00:00","end":"2026-04-08T12:00:05+00:00","duration":2}',
        ]
    )
    window_start = datetime(2026, 4, 8, 11, 58, 0, tzinfo=timezone.utc)
    window_end = datetime(2026, 4, 8, 12, 2, 0, tzinfo=timezone.utc)

    with patch.object(transcript_cache, "get_redis_client", lambda: fake):
        rows = await transcript_cache.get_cached_transcripts_in_window("s1", window_start, window_end)

    assert [row["transcript_id"] for row in rows] == ["t1", "t2"]
    assert fake.zrange_calls == [("transcript:session:s1", int(window_start.timestamp() * 1000), int(window_end.timestamp() * 1000))]


async def test_get_cached_transcripts_in_window_returns_empty_on_read_error():
    fake = FakeRedis(raise_on_read=True)
    with patch.object(transcript_cache, "get_redis_client", lambda: fake):
        rows = await transcript_cache.get_cached_transcripts_in_window(
            "s1",
            datetime.now(timezone.utc) - timedelta(seconds=120),
            datetime.now(timezone.utc),
        )
    assert rows == []


async def main() -> None:
    tests = [
        test_append_transcript_to_cache_is_noop_without_redis,
        test_append_transcript_to_cache_writes_sorted_set_and_trims,
        test_append_transcript_to_cache_skips_when_timestamp_missing,
        test_get_cached_transcripts_in_window_returns_empty_without_redis,
        test_get_cached_transcripts_in_window_reads_valid_rows_and_skips_invalid_json,
        test_get_cached_transcripts_in_window_returns_empty_on_read_error,
    ]
    print("== Transcript cache tests ==")
    for test_fn in tests:
        try:
            await test_fn()
            _log(True, test_fn.__name__)
        except AssertionError as exc:
            _log(False, test_fn.__name__, f"assertion failed: {exc}")
        except Exception as exc:
            _log(False, test_fn.__name__, f"unexpected error: {exc}")

    print(f"\nSummary: PASS={PASS}, FAIL={FAIL}, TOTAL={PASS + FAIL}")
    if FAIL:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
