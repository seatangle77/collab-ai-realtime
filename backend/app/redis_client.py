from __future__ import annotations

import os
from functools import lru_cache

from redis.asyncio import Redis


def _get_redis_url() -> str:
    return os.getenv("REDIS_URL", "").strip()


@lru_cache
def get_redis_client() -> Redis | None:
    redis_url = _get_redis_url()
    if not redis_url:
        return None
    return Redis.from_url(redis_url, decode_responses=True)
