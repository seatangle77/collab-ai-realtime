"""
概念词义查询
POST /api/concepts/lookup

先查 Redis 缓存，命中秒回；未命中调轻模型生成一句解释，写缓存后立即返回。
返回内容后，后台异步完成：更新按钮状态、写 push_logs、发 JPush。
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Mapping

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from openai import AsyncOpenAI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .api_model import ApiModel
from .auth import get_current_user
from .db import get_db, get_sessionmaker
from .jpush_client import send_push_to_registration_id
from .redis_client import get_redis_client
from .settings import QWEN_CHAT_EXTRA_BODY, nlp_settings

router = APIRouter(prefix="/api", tags=["concepts"])
logger = logging.getLogger(__name__)

_CACHE_TTL_S = 60 * 60 * 24 * 7  # 7天
_CACHE_PREFIX = "concept:lookup:"
_MODEL_TIMEOUT_S = 8.0

_SYSTEM_PROMPT = (
    "你是一个面向普通用户的概念解释助手。"
    "只输出一句通俗中文短解释，不加前缀、标题或说明。"
)
_USER_TEMPLATE = (
    "解释「{keyword}」是什么意思，不超过20字；避免术语套术语，必要时用一个简单例子。"
)


# ── Pydantic 模型 ─────────────────────────────────────────────────────────────

class ConceptLookupRequest(ApiModel):
    keyword: str
    button_id: str = ""
    session_id: str = ""


class ConceptLookupResponse(ApiModel):
    keyword: str
    content: str


# ── 缓存 ──────────────────────────────────────────────────────────────────────

async def _get_from_cache(keyword: str) -> str | None:
    redis = get_redis_client()
    if redis is None:
        return None
    try:
        return await redis.get(_CACHE_PREFIX + keyword)
    except Exception as e:
        logger.warning("[concepts] 缓存读取失败: %s", e)
        return None


async def _set_cache(keyword: str, content: str) -> None:
    redis = get_redis_client()
    if redis is None:
        return
    try:
        await redis.set(_CACHE_PREFIX + keyword, content, ex=_CACHE_TTL_S)
    except Exception as e:
        logger.warning("[concepts] 缓存写入失败: %s", e)


# ── 轻模型生成 ────────────────────────────────────────────────────────────────

async def _generate_explanation(keyword: str) -> str:
    if not nlp_settings.qwen_api_key:
        return ""
    client = AsyncOpenAI(
        api_key=nlp_settings.qwen_api_key,
        base_url=nlp_settings.qwen_base_url,
    )
    prompt = _USER_TEMPLATE.format(keyword=keyword)
    try:
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=nlp_settings.fast_model,
                max_tokens=80,
                extra_body=QWEN_CHAT_EXTRA_BODY,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
            ),
            timeout=_MODEL_TIMEOUT_S,
        )
        result = (response.choices[0].message.content or "").strip()
        logger.info("[concepts] 生成解释 keyword=%s content=%s", keyword, result)
        return result
    except asyncio.TimeoutError:
        logger.warning("[concepts] 轻模型调用超时 keyword=%s timeout=%ss", keyword, _MODEL_TIMEOUT_S)
        return ""
    except Exception as e:
        logger.warning("[concepts] 轻模型调用失败: %s", e)
        return ""


# ── 后台任务 ──────────────────────────────────────────────────────────────────

async def _run_background_tasks(
    button_id: str,
    session_id: str,
    user_id: str,
    keyword: str,
    content: str,
) -> None:
    """后台异步：更新按钮状态、写 push_logs、发 JPush。不阻塞主响应。"""
    display_content = f"{keyword}：{content}"

    async with get_sessionmaker()() as db:
        # 1. 更新按钮状态 pending → clicked
        if button_id:
            try:
                await db.execute(
                    text(
                        """
                        UPDATE info_gap_buttons
                        SET status = 'clicked', clicked_at = NOW()
                        WHERE id = :button_id
                          AND user_id = :user_id
                          AND status = 'pending'
                        """
                    ),
                    {"button_id": button_id, "user_id": user_id},
                )
            except Exception as e:
                logger.warning("[concepts] 更新按钮状态失败: %s", e)

        # 2. 获取 device_token
        device_token: str | None = None
        if session_id:
            try:
                user_result = await db.execute(
                    text("SELECT device_token FROM users_info WHERE id = :user_id"),
                    {"user_id": user_id},
                )
                user_row = user_result.mappings().first() or {}
                device_token = user_row.get("device_token")
            except Exception as e:
                logger.warning("[concepts] 查询 device_token 失败: %s", e)

        # 3. 写 push_logs
        log_id: str | None = None
        if session_id and content:
            try:
                log_id = f"pl{uuid.uuid4().hex[:8]}"
                await db.execute(
                    text(
                        """
                        INSERT INTO push_logs
                          (id, session_id, target_user_id, push_content,
                           push_channel, delivery_status, delivery_reason, triggered_at)
                        VALUES
                          (:id, :session_id, :user_id, :content,
                           'info_gap', 'pending', 'jpush_pending', NOW())
                        """
                    ),
                    {
                        "id": log_id,
                        "session_id": session_id,
                        "user_id": user_id,
                        "content": display_content,
                    },
                )
                logger.warning(
                    "[PUSH_LOG_CREATE] source=concepts session_id=%s button_id=%s log_id=%s"
                    " target_user_id=%s status=pending reason=jpush_pending content_len=%s",
                    session_id, button_id, log_id, user_id, len(display_content),
                )
            except Exception as e:
                logger.warning("[concepts] 写 push_logs 失败: %s", e)
                log_id = None

        await db.commit()

        # 4. 发 JPush，根据结果更新 push_logs 状态
        if not log_id:
            return

        if device_token:
            try:
                await asyncio.to_thread(
                    send_push_to_registration_id,
                    device_token,
                    display_content,
                    "",
                )
                await db.execute(
                    text(
                        """
                        UPDATE push_logs
                        SET delivery_status = 'delivered',
                            delivery_reason = 'jpush_delivered',
                            delivered_at = NOW()
                        WHERE id = :id
                        """
                    ),
                    {"id": log_id},
                )
                logger.warning(
                    "[PUSH_LOG_UPDATE] source=concepts session_id=%s log_id=%s"
                    " target_user_id=%s from_status=pending to_status=delivered reason=jpush_delivered",
                    session_id, log_id, user_id,
                )
            except Exception as e:
                logger.warning("[concepts] JPush 发送失败: %s", e)
                await db.execute(
                    text(
                        """
                        UPDATE push_logs
                        SET delivery_status = 'failed',
                            delivery_reason = 'jpush_send_error'
                        WHERE id = :id
                        """
                    ),
                    {"id": log_id},
                )
                logger.warning(
                    "[PUSH_LOG_UPDATE] source=concepts session_id=%s log_id=%s"
                    " target_user_id=%s from_status=pending to_status=failed reason=jpush_send_error",
                    session_id, log_id, user_id,
                )
        else:
            await db.execute(
                text(
                    """
                    UPDATE push_logs
                    SET delivery_status = 'skipped',
                        delivery_reason = 'jpush_no_device_token'
                    WHERE id = :id
                    """
                ),
                {"id": log_id},
            )
            logger.warning(
                "[PUSH_LOG_UPDATE] source=concepts session_id=%s log_id=%s"
                " target_user_id=%s from_status=pending to_status=skipped reason=jpush_no_device_token",
                session_id, log_id, user_id,
            )

        await db.commit()


# ── 接口 ──────────────────────────────────────────────────────────────────────

@router.post("/concepts/lookup", response_model=ConceptLookupResponse)
async def lookup_concept(
    body: ConceptLookupRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: Mapping[str, Any] = Depends(get_current_user),
) -> ConceptLookupResponse:
    """
    查询概念词义。先走缓存，未命中调轻模型生成一句解释。
    立即返回结果，状态更新 / push_logs / JPush 在后台异步完成。
    """
    keyword = body.keyword.strip()
    if not keyword:
        return ConceptLookupResponse(keyword=keyword, content="")

    # 校验 session_id 归属（当前用户必须是该会话的活跃成员）
    if body.session_id:
        session_row = await db.execute(
            text(
                """
                SELECT 1 FROM chat_sessions cs
                JOIN group_memberships gm ON gm.group_id = cs.group_id
                WHERE cs.id = :session_id
                  AND gm.user_id = :user_id
                  AND gm.status = 'active'
                """
            ),
            {"session_id": body.session_id, "user_id": current_user["id"]},
        )
        if not session_row.first():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="仅会话活跃成员可访问",
            )

    # 校验 button_id 归属（按钮必须属于该 session 且属于当前用户）
    if body.button_id and body.session_id:
        btn_row = await db.execute(
            text(
                """
                SELECT 1 FROM info_gap_buttons
                WHERE id = :button_id
                  AND session_id = :session_id
                  AND user_id = :user_id
                """
            ),
            {
                "button_id": body.button_id,
                "session_id": body.session_id,
                "user_id": current_user["id"],
            },
        )
        if not btn_row.first():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="按钮不存在",
            )

    # 1. 查缓存
    content = await _get_from_cache(keyword)
    if content:
        logger.info("[concepts] 缓存命中 keyword=%s", keyword)
    else:
        # 2. 调轻模型（有 timeout；失败时返回空内容）
        content = await _generate_explanation(keyword)
        if content:
            await _set_cache(keyword, content)

    # 3. 后台任务（不阻塞返回）
    if content and (body.button_id or body.session_id):
        background_tasks.add_task(
            _run_background_tasks,
            button_id=body.button_id,
            session_id=body.session_id,
            user_id=current_user["id"],
            keyword=keyword,
            content=content,
        )

    return ConceptLookupResponse(keyword=keyword, content=content or "")
