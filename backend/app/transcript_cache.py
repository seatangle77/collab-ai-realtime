from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from .redis_client import get_redis_client

logger = logging.getLogger(__name__)

TRANSCRIPT_CACHE_RETENTION_SECONDS = 240
TRANSCRIPT_CACHE_KEY_PREFIX = "transcript:session"
TRANSCRIPT_CACHE_TTL_SECONDS = 1800


def _to_timestamp_ms(value: datetime | str | None) -> int:
    if value is None:
        return 0
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        value = datetime.fromisoformat(normalized)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return int(value.timestamp() * 1000)


def _cache_key(session_id: str) -> str:
    return f"{TRANSCRIPT_CACHE_KEY_PREFIX}:{session_id}"


def _serialize_transcript(transcript: dict[str, Any]) -> str:
    return json.dumps(transcript, ensure_ascii=False, separators=(",", ":"))


async def append_transcript_to_cache(session_id: str, transcript: dict[str, Any]) -> None:
    client = get_redis_client()
    if client is None:
        logger.info("skip transcript cache append because redis is not configured", extra={"session_id": session_id})
        return

    key = _cache_key(session_id)
    score = _to_timestamp_ms(transcript.get("end") or transcript.get("created_at") or transcript.get("start"))
    if score <= 0:
        logger.warning("skip transcript cache append because timestamp is missing", extra={"session_id": session_id})
        return

    cutoff_score = score - (TRANSCRIPT_CACHE_RETENTION_SECONDS * 1000)

    try:
        async with client.pipeline(transaction=False) as pipe:
            await pipe.zadd(key, {_serialize_transcript(transcript): score})
            await pipe.zremrangebyscore(key, 0, cutoff_score)
            await pipe.expire(key, TRANSCRIPT_CACHE_TTL_SECONDS)
            await pipe.execute()
        logger.info("transcript cached in redis", extra={"session_id": session_id, "key": key, "score": score})
    except Exception:
        logger.exception("append transcript to redis cache failed", extra={"session_id": session_id})


async def get_cached_transcripts_in_window(
    session_id: str,
    window_start: datetime,
    window_end: datetime,
) -> list[dict[str, Any]]:
    client = get_redis_client()
    if client is None:
        logger.info("skip transcript cache read because redis is not configured", extra={"session_id": session_id})
        return []

    min_score = _to_timestamp_ms(window_start)
    max_score = _to_timestamp_ms(window_end)
    key = _cache_key(session_id)

    try:
        rows = await client.zrangebyscore(key, min_score, max_score)
        logger.info(
            "read transcript cache window",
            extra={"session_id": session_id, "key": key, "count": len(rows), "min_score": min_score, "max_score": max_score},
        )
    except Exception:
        logger.exception("read transcript cache failed", extra={"session_id": session_id})
        return []

    items: list[dict[str, Any]] = []
    for row in rows:
        try:
            items.append(json.loads(row))
        except json.JSONDecodeError:
            logger.warning("skip invalid cached transcript json", extra={"session_id": session_id})
    return items
