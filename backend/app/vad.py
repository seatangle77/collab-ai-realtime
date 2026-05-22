from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends

from .admin.deps import require_admin
from .redis_client import get_redis_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/internal", tags=["vad"])
VAD_SPEAKING_THRESHOLD_MS = 650


@router.get(
    "/sessions/{session_id}/vad-speaking",
    dependencies=[Depends(require_admin)],
)
async def get_vad_speaking(session_id: str) -> dict:
    """
    查询当前 session 是否有人正在说话。
    优先使用 last_voice_at_ms 计算静默时长；旧 is_speaking TTL key 仅作兼容兜底。
    Agent 推送前调用此接口，有人说话则跳过本次推送。
    """
    client = get_redis_client()
    if client is None:
        # Redis 未配置，不阻塞推送
        logger.debug("[VAD] session=%s Redis 未配置，返回 is_speaking=false", session_id)
        return {"is_speaking": False}

    key = f"vad:{session_id}:is_speaking"
    last_voice_key = f"vad:{session_id}:last_voice_at_ms"
    try:
        last_voice_raw = await client.get(last_voice_key)
        if last_voice_raw is not None:
            last_voice_at_ms = int(last_voice_raw)
            silence_ms = max(0, int(time.time() * 1000) - last_voice_at_ms)
            is_speaking = silence_ms < VAD_SPEAKING_THRESHOLD_MS
            logger.debug(
                "[VAD] session=%s last_voice_at_ms=%s silence_ms=%s is_speaking=%s",
                session_id,
                last_voice_at_ms,
                silence_ms,
                is_speaking,
            )
            return {
                "is_speaking": is_speaking,
                "silence_ms": silence_ms,
                "last_voice_at_ms": last_voice_at_ms,
            }

        value = await client.get(key)
        is_speaking = value is not None
        logger.debug("[VAD] session=%s key=%s is_speaking=%s legacy=true", session_id, key, is_speaking)
        return {"is_speaking": is_speaking, "silence_ms": None, "last_voice_at_ms": None}
    except ValueError:
        logger.warning("[VAD] session=%s invalid last_voice_at_ms，返回 is_speaking=false", session_id)
        return {"is_speaking": False, "silence_ms": None, "last_voice_at_ms": None}
    except Exception as e:
        # Redis 出错，不阻塞推送
        logger.warning("[VAD] session=%s redis_error=%s，返回 is_speaking=false", session_id, e)
        return {"is_speaking": False, "silence_ms": None, "last_voice_at_ms": None}
