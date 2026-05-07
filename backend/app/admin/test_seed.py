"""
测试数据种子接口（仅 admin 可用）
用于在集成测试中插入 agent 产生的数据（info_gap_buttons / discussion_summaries / window_metrics）
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from ..api_model import ApiModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from .deps import require_admin

router = APIRouter(
    prefix="/api/admin/test-seed",
    tags=["admin-test-seed"],
    dependencies=[Depends(require_admin)],
)


# ── info_gap_buttons ──────────────────────────────────────────────────────────

class InfoGapButtonSeed(ApiModel):
    session_id: str
    user_id: str
    keyword: str
    skw_score: float = 0.2
    status: str = "pending"


@router.post("/info-gap-button")
async def seed_info_gap_button(
    body: InfoGapButtonSeed,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    btn_id = f"igb{uuid.uuid4().hex[:8]}"
    await db.execute(
        text(
            """
            INSERT INTO info_gap_buttons
              (id, session_id, user_id, keyword, skw_score, status, window_start, created_at)
            VALUES
              (:id, :session_id, :user_id, :keyword, :skw_score, :status, NOW(), NOW())
            """
        ),
        {
            "id": btn_id,
            "session_id": body.session_id,
            "user_id": body.user_id,
            "keyword": body.keyword,
            "skw_score": body.skw_score,
            "status": body.status,
        },
    )
    await db.commit()
    return {"id": btn_id}


# ── discussion_summaries ──────────────────────────────────────────────────────

class DiscussionSummarySeed(ApiModel):
    session_id: str
    content: str
    version: int = 1


@router.post("/discussion-summary")
async def seed_discussion_summary(
    body: DiscussionSummarySeed,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    sid = f"ds{uuid.uuid4().hex[:8]}"
    await db.execute(
        text(
            """
            INSERT INTO discussion_summaries
              (id, session_id, version, content, window_start, window_end, created_at)
            VALUES
              (:id, :session_id, :version, :content,
               NOW() - INTERVAL '2 minutes', NOW(), NOW())
            """
        ),
        {
            "id": sid,
            "session_id": body.session_id,
            "version": body.version,
            "content": body.content,
        },
    )
    await db.commit()
    return {"id": sid}


# ── window_metrics ────────────────────────────────────────────────────────────

class WindowMetricsSeed(ApiModel):
    session_id: str
    user_id: str
    speaking_ratio: float = 0.4
    silence_s: int = 30
    ttr: float | None = 0.6
    arg_density: float | None = 0.1
    srep: float | None = None
    info_gain: float | None = None
    has_reasoning: bool | None = None
    has_evidence: bool | None = None
    reasoning_source: str | None = None
    evidence_source: str | None = None


@router.post("/window-metrics")
async def seed_window_metrics(
    body: WindowMetricsSeed,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    mid = f"wm{uuid.uuid4().hex[:8]}"
    await db.execute(
        text(
            """
            INSERT INTO window_metrics
              (id, session_id, user_id, window_start, window_end,
               speaking_ratio, silence_s, ttr, arg_density,
               srep, info_gain, has_reasoning, has_evidence, reasoning_source, evidence_source, created_at)
            VALUES
              (:id, :session_id, :user_id,
               NOW() - INTERVAL '2 minutes', NOW(),
               :speaking_ratio, :silence_s, :ttr, :arg_density,
               :srep, :info_gain, :has_reasoning, :has_evidence, :reasoning_source, :evidence_source, NOW())
            """
        ),
        {
            "id": mid,
            "session_id": body.session_id,
            "user_id": body.user_id,
            "speaking_ratio": body.speaking_ratio,
            "silence_s": body.silence_s,
            "ttr": body.ttr,
            "arg_density": body.arg_density,
            "srep": body.srep,
            "info_gain": body.info_gain,
            "has_reasoning": body.has_reasoning,
            "has_evidence": body.has_evidence,
            "reasoning_source": body.reasoning_source,
            "evidence_source": body.evidence_source,
        },
    )
    await db.commit()
    return {"id": mid}
