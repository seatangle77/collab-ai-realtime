from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any, Mapping

from fastapi import APIRouter, Depends, HTTPException, Query, status
from .api_model import ApiModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .admin.deps import require_admin
from .auth import get_current_user
from .db import get_db
from .jpush_client import send_push_to_registration_id
from .time_utils import utc_iso
from .ws_manager import ws_manager
from .ws_protocol import build_group_notification, build_push_notification

router = APIRouter(prefix="/api", tags=["push-logs"])
logger = logging.getLogger(__name__)
WS_TRACE = "[WS_TRACE]"

VALID_PUSH_CHANNELS = {"web", "app", "glasses", "info_gap"}
VALID_DELIVERY_STATUSES = {"pending", "delivered", "failed", "skipped", "deferred"}
JPUSH_NOTIFICATION_TITLE = "AI 讨论建议"


async def _jpush_safe(device_token: str, content: str, title: str) -> None:
    """JPush 推送，失败静默处理，不抛出异常。"""
    try:
        await asyncio.to_thread(
            send_push_to_registration_id,
            device_token,
            content,
            title,
        )
    except Exception:
        pass


class PushNotifyIn(ApiModel):
    target_user_id: str
    content: str
    state_id: str | None = None
    trigger_type: str = ""
    queue_id: str | None = None


class GroupNotifyIn(ApiModel):
    content: str


def _build_reasoning_run_id(session_id: str, window_start: Any) -> str | None:
    if window_start is None:
        return None
    value = window_start.isoformat() if hasattr(window_start, "isoformat") else str(window_start)
    return f"reasoning:{session_id}:{value}"


@router.post(
    "/internal/sessions/{session_id}/push-notify",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def push_notify(
    session_id: str,
    body: PushNotifyIn,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Agent 写推送日志并通过 WebSocket 定向发给目标用户。
    1. 写入 push_logs（delivery_status 根据 WS 是否在线决定）
    2. 尝试 WebSocket 定向推送
    3. 更新 delivery_status
    """
    logger.warning(
        "%s [push_notify] >>> 收到推送请求 session_id=%s target_user_id=%s queue_id=%s",
        WS_TRACE,
        session_id, body.target_user_id, body.queue_id,
    )
    analysis_window_start = None
    analysis_run_id = None
    if body.state_id:
        state_result = await db.execute(
            text("SELECT window_start FROM discussion_states WHERE id = :id"),
            {"id": body.state_id},
        )
        state_row = state_result.mappings().first()
        if state_row:
            analysis_window_start = state_row["window_start"]
            analysis_run_id = _build_reasoning_run_id(session_id, analysis_window_start)

    content_embedding = None
    if body.queue_id:
        queue_result = await db.execute(
            text(
                """
                SELECT status, content_embedding
                FROM push_queue
                WHERE id = :queue_id
                  AND session_id = :session_id
                """
            ),
            {"queue_id": body.queue_id, "session_id": session_id},
        )
        queue_row = queue_result.mappings().first()
        if queue_row and queue_row["status"] in {"delivered", "skipped", "failed"}:
            logger.warning(
                "%s [push_notify] 队列已是终态 queue_id=%s status=%s，跳过",
                WS_TRACE,
                body.queue_id, queue_row["status"],
            )
            return {
                "id": None,
                "delivery_status": queue_row["status"],
                "delivery_reason": "queue_already_final",
                "ws_sent": False,
            }
        if queue_row:
            content_embedding = queue_row["content_embedding"]

    log_id = "pl" + uuid.uuid4().hex[:8]

    # 1. 写库（先 pending）
    insert_result = await db.execute(
        text(
            """
            INSERT INTO push_logs (
                id, session_id, state_id, queue_id, target_user_id, push_content,
                content_embedding, push_channel, delivery_status, delivery_reason, triggered_at
            )
            VALUES (
                :id, :session_id, :state_id, :queue_id, :target_user_id, :content,
                :content_embedding, 'web', 'pending', 'ws_pending', NOW()
            )
            RETURNING triggered_at
            """
        ),
        {
            "id": log_id,
            "session_id": session_id,
            "state_id": body.state_id,
            "queue_id": body.queue_id,
            "target_user_id": body.target_user_id,
            "content": body.content,
            "content_embedding": content_embedding,
        },
    )
    inserted_row = insert_result.mappings().one()
    await db.commit()
    logger.warning(
        "%s [PUSH_LOG_CREATE] source=push_notify session_id=%s queue_id=%s log_id=%s target_user_id=%s status=pending reason=ws_pending trigger_type=%s content_len=%s",
        WS_TRACE,
        session_id,
        body.queue_id,
        log_id,
        body.target_user_id,
        body.trigger_type,
        len(body.content),
    )

    # 2. 定向 WebSocket 推送
    online_user_ids = ws_manager.get_online_user_ids(session_id)
    session_conn_count = ws_manager.get_session_connection_count(session_id)
    user_conn_count = ws_manager.get_user_connection_count(session_id)
    logger.warning(
        "%s [push_notify_check] session_id=%s target_user_id=%s session_conn_count=%s user_conn_count=%s online_user_ids=%s",
        WS_TRACE,
        session_id,
        body.target_user_id,
        session_conn_count,
        user_conn_count,
        online_user_ids,
    )
    target_online = body.target_user_id in online_user_ids
    sent = await ws_manager.send_to_user(
        session_id,
        body.target_user_id,
        build_push_notification(
            body.content,
            body.target_user_id,
            utc_iso(inserted_row["triggered_at"]),
            analysis_run_id=analysis_run_id,
            analysis_window_start=utc_iso(analysis_window_start),
        ),
    )

    # 3. 更新投递状态
    new_status = "delivered" if sent else "failed"
    delivery_reason = "ws_delivered" if sent else (
        "ws_send_error" if target_online else "ws_user_not_connected"
    )
    if delivery_reason == "ws_user_not_connected":
        logger.warning(
            "%s [push_notify_ws_user_not_connected] session_id=%s target_user_id=%s log_id=%s session_conn_count=%s user_conn_count=%s online_user_ids=%s queue_id=%s trigger_type=%s",
            WS_TRACE,
            session_id,
            body.target_user_id,
            log_id,
            session_conn_count,
            user_conn_count,
            online_user_ids,
            body.queue_id,
            body.trigger_type,
        )
    logger.warning(
        "%s [push_notify_result] session_id=%s target_user_id=%s log_id=%s target_online=%s ws_sent=%s delivery_reason=%s session_conn_count=%s user_conn_count=%s online_user_ids=%s",
        WS_TRACE,
        session_id,
        body.target_user_id,
        log_id,
        target_online,
        sent,
        delivery_reason,
        session_conn_count,
        user_conn_count,
        online_user_ids,
    )
    await db.execute(
        text(
            "UPDATE push_logs SET delivery_status = :s, delivery_reason = :r, delivered_at = NOW() WHERE id = :id"
            if sent else
            "UPDATE push_logs SET delivery_status = :s, delivery_reason = :r WHERE id = :id"
        ),
        {"s": new_status, "r": delivery_reason, "id": log_id},
    )
    await db.commit()
    logger.warning(
        "%s [PUSH_LOG_UPDATE] source=push_notify session_id=%s queue_id=%s log_id=%s target_user_id=%s from_status=pending to_status=%s reason=%s target_online=%s ws_sent=%s session_conn_count=%s user_conn_count=%s online_user_ids=%s",
        WS_TRACE,
        session_id,
        body.queue_id,
        log_id,
        body.target_user_id,
        new_status,
        delivery_reason,
        target_online,
        sent,
        session_conn_count,
        user_conn_count,
        online_user_ids,
    )

    # 4. JPush：目标用户有 device_token 时额外推送，离线也通知
    token_result = await db.execute(
        text("SELECT device_token FROM users_info WHERE id = :uid"),
        {"uid": body.target_user_id},
    )
    token_row = token_result.mappings().first()
    device_token = token_row["device_token"] if token_row else None
    if device_token:
        await _jpush_safe(device_token, body.content, JPUSH_NOTIFICATION_TITLE)

    return {
        "id": log_id,
        "delivery_status": new_status,
        "delivery_reason": delivery_reason,
        "ws_sent": sent,
    }


@router.post(
    "/internal/sessions/{session_id}/group-notify",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def group_notify(
    session_id: str,
    body: GroupNotifyIn,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Agent 触发群组通知：
    1. 找到会话内在线用户
    2. 对每个在线用户单独发送，根据实际发送结果写各自的 push_log 状态
    """
    # 连接管理里可能存在脏 user_id（None/空串），先过滤，避免触发表约束。
    online_user_ids = [
        uid for uid in ws_manager.get_online_user_ids(session_id)
        if isinstance(uid, str) and uid.strip()
    ]
    if not online_user_ids:
        return {
            "id": None,
            "delivery_status": "failed",
            "online_connections": 0,
        }

    message = build_group_notification(body.content, None)
    delivered_count = 0
    failed_count = 0
    first_log_id: str | None = None

    for uid in online_user_ids:
        sent = await ws_manager.send_to_user(session_id, uid, message)
        log_id = "pl" + uuid.uuid4().hex[:8]
        if first_log_id is None:
            first_log_id = log_id

        if sent:
            await db.execute(
                text(
                    """
                    INSERT INTO push_logs (
                        id, session_id, state_id, target_user_id, push_content,
                        push_channel, delivery_status, delivery_reason, triggered_at, delivered_at
                    )
                    VALUES (
                        :id, :session_id, NULL, :target_user_id, :content,
                        'web', 'delivered', 'group_ws_delivered', NOW(), NOW()
                    )
                    """
                ),
                {"id": log_id, "session_id": session_id, "target_user_id": uid, "content": body.content},
            )
            delivered_count += 1
        else:
            await db.execute(
                text(
                    """
                    INSERT INTO push_logs (
                        id, session_id, state_id, target_user_id, push_content,
                        push_channel, delivery_status, delivery_reason, triggered_at
                    )
                    VALUES (
                        :id, :session_id, NULL, :target_user_id, :content,
                        'web', 'failed', 'group_ws_send_error', NOW()
                    )
                    """
                ),
                {"id": log_id, "session_id": session_id, "target_user_id": uid, "content": body.content},
            )
            failed_count += 1

    await db.commit()

    # JPush：群组全部 active 成员并发推送，离线也通知
    member_token_result = await db.execute(
        text(
            """
            SELECT u.device_token
            FROM group_memberships gm
            JOIN users_info u ON u.id = gm.user_id
            JOIN chat_sessions cs ON cs.group_id = gm.group_id
            WHERE cs.id = :session_id
              AND gm.status = 'active'
              AND u.device_token IS NOT NULL
            """
        ),
        {"session_id": session_id},
    )
    device_tokens = [row["device_token"] for row in member_token_result.mappings().all()]
    if device_tokens:
        await asyncio.gather(
            *[_jpush_safe(token, body.content, JPUSH_NOTIFICATION_TITLE) for token in device_tokens]
        )

    return {
        "id": first_log_id,
        "delivered_count": delivered_count,
        "failed_count": failed_count,
        "online_connections": len(online_user_ids),
    }


class PushLogOut(ApiModel):
    id: str
    session_id: str
    target_user_id: str | None = None
    state_id: str | None = None
    queue_id: str | None = None
    analysis_run_id: str | None = None
    analysis_window_start: datetime | None = None
    push_content: str | None = None
    push_channel: str
    jpush_message_id: str | None = None
    delivery_status: str
    delivery_reason: str | None = None
    triggered_at: datetime
    delivered_at: datetime | None = None


@router.get(
    "/sessions/{session_id}/push-logs",
    response_model=list[PushLogOut],
)
async def get_session_push_logs(
    session_id: str,
    push_channel: str | None = Query(None),
    delivery_status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: Mapping[str, Any] = Depends(get_current_user),
) -> list[PushLogOut]:
    """
    获取当前用户在指定会话中收到的推送日志。
    仅返回 target_user_id = 当前用户的记录。
    """
    # 枚举校验
    if push_channel is not None and push_channel not in VALID_PUSH_CHANNELS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的 push_channel，合法值：{', '.join(sorted(VALID_PUSH_CHANNELS))}",
        )
    if delivery_status is not None and delivery_status not in VALID_DELIVERY_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的 delivery_status，合法值：{', '.join(sorted(VALID_DELIVERY_STATUSES))}",
        )

    # 1. 校验会话存在
    session_result = await db.execute(
        text("SELECT group_id FROM chat_sessions WHERE id = :id"),
        {"id": session_id},
    )
    session_row = session_result.mappings().first()
    if not session_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")

    group_id = session_row["group_id"]

    # 2. 校验当前用户是该群组 active 成员
    membership_result = await db.execute(
        text(
            """
            SELECT 1 FROM group_memberships
            WHERE group_id = :group_id AND user_id = :user_id AND status = 'active'
            """
        ),
        {"group_id": group_id, "user_id": current_user["id"]},
    )
    if not membership_result.first():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅群组成员可以查看推送日志")

    # Web 推送有两条到达路径：实时 WebSocket 和前端轮询。
    # push_notify 中的 failed 只表示实时 WS 未命中在线连接；如果用户已经通过
    # 本接口拉到了自己的日志，就说明 Web 端已补偿送达，避免后台长期显示“失败”。
    if delivery_status is None:
        await db.execute(
            text(
                """
                UPDATE push_logs
                SET delivery_status = 'delivered',
                    delivery_reason = 'polling_delivered',
                    delivered_at = COALESCE(delivered_at, NOW())
                WHERE session_id = :session_id
                  AND target_user_id = :user_id
                  AND push_channel = 'web'
                  AND delivery_status = 'failed'
                """
            ),
            {
                "session_id": session_id,
                "user_id": current_user["id"],
            },
        )
        await db.commit()

    # 3. 查询当前用户的推送记录。用户端只展示真正已送达/已补达的推送；
    # skipped/deferred/failed 留给后台管理排查，不打扰用户端时间线。
    where: list[str] = [
        "pl.session_id = :session_id",
        "pl.target_user_id = :user_id",
    ]
    params: dict[str, Any] = {
        "session_id": session_id,
        "user_id": current_user["id"],
    }

    if push_channel is not None:
        where.append("pl.push_channel = :push_channel")
        params["push_channel"] = push_channel
    if delivery_status is not None:
        where.append("pl.delivery_status = :delivery_status")
        params["delivery_status"] = delivery_status
    else:
        where.append("pl.delivery_status = 'delivered'")

    where_sql = " AND ".join(where)

    result = await db.execute(
        text(
            f"""
            SELECT
                pl.id, pl.session_id, pl.state_id, pl.queue_id,
                pl.target_user_id,
                ds.window_start AS analysis_window_start,
                pl.push_content, pl.push_channel,
                pl.jpush_message_id, pl.delivery_status, pl.delivery_reason,
                pl.triggered_at, pl.delivered_at
            FROM push_logs pl
            LEFT JOIN discussion_states ds ON ds.id = pl.state_id
            WHERE {where_sql}
            ORDER BY pl.triggered_at DESC
            """
        ),
        params,
    )
    rows = result.mappings().all()
    items: list[PushLogOut] = []
    for row in rows:
        payload = dict(row)
        payload["analysis_run_id"] = _build_reasoning_run_id(payload["session_id"], payload["analysis_window_start"])
        items.append(PushLogOut.model_validate(payload))
    return items
