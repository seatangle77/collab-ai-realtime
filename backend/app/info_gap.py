"""
信息缺口关键词按钮接口
- GET  /api/sessions/{session_id}/info-gap/buttons  查询当前用户 pending 按钮
- POST /api/sessions/{session_id}/info-gap/click    点击按钮，更新状态
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any, Mapping

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .admin.deps import require_admin
from .auth import get_current_user
from .db import get_db
from .jpush_client import send_push_to_registration_id
from .nlp import push_content as nlp_push_content
from .ws_manager import ws_manager
from .ws_protocol import build_info_gap_button

router = APIRouter(prefix="/api", tags=["info-gap"])


# ── Pydantic 模型 ─────────────────────────────────────────────────────────────

class InfoGapButtonOut(BaseModel):
    id: str
    keyword: str
    skw_score: float
    status: str
    analysis_run_id: str
    window_start: Any
    created_at: Any


class ClickRequest(BaseModel):
    button_id: str


class ClickResponse(BaseModel):
    success: bool


# ── 工具函数 ──────────────────────────────────────────────────────────────────


def _build_reasoning_run_id(session_id: str, window_start: Any) -> str:
    value = window_start.isoformat() if hasattr(window_start, "isoformat") else str(window_start)
    return f"reasoning:{session_id}:{value}"

async def _assert_session_member(
    session_id: str,
    user_id: str,
    db: AsyncSession,
) -> None:
    """校验会话存在且当前用户是活跃成员，否则抛 HTTPException。"""
    row = await db.execute(
        text(
            """
            SELECT 1 FROM chat_sessions cs
            JOIN group_memberships gm ON gm.group_id = cs.group_id
            WHERE cs.id = :session_id
              AND gm.user_id = :user_id
              AND gm.status = 'active'
            """
        ),
        {"session_id": session_id, "user_id": user_id},
    )
    if not row.first():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅会话活跃成员可访问",
        )


# ── 接口 ──────────────────────────────────────────────────────────────────────

class InfoGapNotifyIn(BaseModel):
    user_id: str
    button_id: str
    keyword: str
    skw_score: float
    window_start: str  # ISO 8601


@router.post(
    "/internal/sessions/{session_id}/info-gap/notify",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_admin)],
)
async def notify_info_gap_button(
    session_id: str,
    body: InfoGapNotifyIn,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Agent 写完 info_gap_buttons 后调此接口，把新按钮通过 WebSocket 推给目标用户。
    """
    analysis_run_id = _build_reasoning_run_id(session_id, body.window_start)

    # 读取 created_at（让前端时间轴能用）
    result = await db.execute(
        text("SELECT created_at FROM info_gap_buttons WHERE id = :id"),
        {"id": body.button_id},
    )
    row = result.mappings().first()
    created_at = row["created_at"].isoformat() if row and row["created_at"] else None

    button_payload = {
        "id": body.button_id,
        "keyword": body.keyword,
        "skw_score": body.skw_score,
        "analysis_run_id": analysis_run_id,
        "window_start": body.window_start,
        "created_at": created_at,
    }

    sent = await ws_manager.send_to_user(
        session_id,
        body.user_id,
        build_info_gap_button([button_payload]),
    )

    return {"sent": sent, "button_id": body.button_id}


@router.get(
    "/sessions/{session_id}/info-gap/buttons",
    response_model=list[InfoGapButtonOut],
)
async def get_info_gap_buttons(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Mapping[str, Any] = Depends(get_current_user),
) -> list[InfoGapButtonOut]:
    """查询当前用户在该会话中状态为 pending 的信息缺口关键词按钮。"""
    await _assert_session_member(session_id, current_user["id"], db)

    result = await db.execute(
        text(
            """
            SELECT id, keyword, skw_score, status, window_start, created_at
            FROM info_gap_buttons
            WHERE session_id = :session_id
              AND user_id    = :user_id
              AND status     = 'pending'
            ORDER BY created_at DESC
            """
        ),
        {"session_id": session_id, "user_id": current_user["id"]},
    )
    rows = result.mappings().all()
    items: list[InfoGapButtonOut] = []
    for row in rows:
        payload = dict(row)
        payload["analysis_run_id"] = _build_reasoning_run_id(session_id, payload["window_start"])
        items.append(InfoGapButtonOut.model_validate(payload))
    return items


@router.post(
    "/sessions/{session_id}/info-gap/click",
    response_model=ClickResponse,
)
async def click_info_gap_button(
    session_id: str,
    body: ClickRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Mapping[str, Any] = Depends(get_current_user),
) -> ClickResponse:
    """
    用户点击信息缺口关键词按钮。
    - 原子更新：pending -> clicked
    - 组装摘要与最近发言，生成真实信息缺口提示文案
    - 写 push_logs 并尝试 JPush 推送
    """
    await _assert_session_member(session_id, current_user["id"], db)

    # 1) 原子更新：仅 pending 才能改为 clicked
    update_result = await db.execute(
        text(
            """
            UPDATE info_gap_buttons
            SET status = 'clicked', clicked_at = NOW()
            WHERE id = :button_id
              AND session_id = :session_id
              AND user_id = :user_id
              AND status = 'pending'
            RETURNING id, keyword, skw_score
            """
        ),
        {
            "button_id": body.button_id,
            "session_id": session_id,
            "user_id": current_user["id"],
        },
    )
    btn = update_result.mappings().first()
    if not btn:
        # 细分 404 / 409，避免接口语义丢失
        exists_result = await db.execute(
            text(
                """
                SELECT status
                FROM info_gap_buttons
                WHERE id = :button_id
                  AND session_id = :session_id
                  AND user_id = :user_id
                """
            ),
            {
                "button_id": body.button_id,
                "session_id": session_id,
                "user_id": current_user["id"],
            },
        )
        exists_row = exists_result.mappings().first()
        if not exists_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="按钮不存在")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="按钮已被点击或已过期")

    await db.commit()

    # 2) 组装上下文并生成真实推送文案
    summary_result = await db.execute(
        text(
            """
            SELECT content
            FROM discussion_summaries
            WHERE session_id = :session_id
            ORDER BY version DESC, created_at DESC
            LIMIT 1
            """
        ),
        {"session_id": session_id},
    )
    summary_row = summary_result.mappings().first()
    summary_text = str(summary_row["content"]).strip() if summary_row and summary_row.get("content") else ""

    transcripts_result = await db.execute(
        text(
            """
            SELECT
              COALESCE(t.user_id, t.speaker, '未知') AS speaker_id,
              t.text
            FROM speech_transcripts t
            WHERE t.session_id = :session_id
              AND t.text IS NOT NULL
              AND t.text != ''
            ORDER BY t.start DESC
            LIMIT 30
            """
        ),
        {"session_id": session_id},
    )
    transcript_rows = list(reversed(transcripts_result.mappings().all()))
    transcript_text = "\n".join(
        f"{r.get('speaker_id', '未知')}：{str(r.get('text', '')).strip()}"
        for r in transcript_rows
        if str(r.get("text", "")).strip()
    )

    user_result = await db.execute(
        text("SELECT name, device_token FROM users_info WHERE id = :user_id"),
        {"user_id": current_user["id"]},
    )
    user_row = user_result.mappings().first() or {}
    username = str(user_row.get("name") or "")
    device_token = user_row.get("device_token")

    generated_content = nlp_push_content.generate_push_content(
        trigger_type="info_gap",
        summary=summary_text,
        transcripts=transcript_text,
        username=username,
        keyword=str(btn["keyword"]),
        skw_score=float(btn.get("skw_score") or 0.0),
    )
    final_content = generated_content or f"关键词「{btn['keyword']}」可先从讨论语境里看定义和例子。"

    # 3) 写 push_log 记录
    log_id = f"pl{uuid.uuid4().hex[:8]}"
    await db.execute(
        text(
            """
            INSERT INTO push_logs
              (id, session_id, target_user_id, push_content,
               push_channel, delivery_status, triggered_at)
            VALUES
              (:id, :session_id, :user_id, :content,
               'app', 'pending', NOW())
            """
        ),
        {
            "id": log_id,
            "session_id": session_id,
            "user_id": current_user["id"],
            "content": final_content,
        },
    )
    await db.commit()

    # 4) JPush 推送（如果用户有 device_token）
    if device_token:
        try:
            await asyncio.to_thread(
                send_push_to_registration_id,
                device_token,
                final_content,
                "信息缺口提示",
            )
            await db.execute(
                text(
                    "UPDATE push_logs SET delivery_status = 'delivered' WHERE id = :id"
                ),
                {"id": log_id},
            )
            await db.commit()
        except Exception:
            # 推送失败不影响接口返回，日志由 jpush_client 内部记录
            pass

    return ClickResponse(success=True)
