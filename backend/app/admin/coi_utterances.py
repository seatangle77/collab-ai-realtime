"""Admin API for CoI utterance segmentation and coding."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..api_model import ApiModel
from ..db import get_db
from .deps import require_admin

router = APIRouter(
    prefix="/api/admin/coi-utterances",
    tags=["admin-coi-utterances"],
    dependencies=[Depends(require_admin)],
)

COI_CATEGORIES = {"TE", "EX", "IN", "RE"}


# ── Schemas ───────────────────────────────────────────────────────────────────

class CoiUtteranceOut(ApiModel):
    id: str
    session_id: str
    group_id: str
    speaker: str | None
    speaker_name: str | None
    speaker_user_id: str | None
    content: str
    source_transcript_ids: list[str]
    order_index: int
    coi_category: str | None
    coded_by: str | None
    coded_at: datetime | None
    created_at: datetime
    start_time: float | None = None


class CoiUtterancePatch(ApiModel):
    speaker: str | None = None
    content: str | None = None
    speaker_user_id: str | None = None


class CoiCodePatch(ApiModel):
    coi_category: str | None
    coded_by: str | None = None


class MergeRequest(ApiModel):
    ids: list[str]


class SplitRequest(ApiModel):
    offset: int


class ReorderItem(ApiModel):
    id: str
    order_index: int


class ReorderRequest(ApiModel):
    items: list[ReorderItem]


class ImportResponse(ApiModel):
    imported: int
    skipped: int


# ── Helpers ───────────────────────────────────────────────────────────────────

def _new_id() -> str:
    return "cu" + uuid.uuid4().hex[:12]


def _row_to_out(row: Any) -> CoiUtteranceOut:
    return CoiUtteranceOut(
        id=row["id"],
        session_id=row["session_id"],
        group_id=row["group_id"],
        speaker=row["speaker"],
        speaker_name=row.get("speaker_name"),
        speaker_user_id=row["speaker_user_id"],
        content=row["content"],
        source_transcript_ids=row["source_transcript_ids"] or [],
        order_index=row["order_index"],
        coi_category=row["coi_category"],
        coded_by=row["coded_by"],
        coded_at=row["coded_at"],
        created_at=row["created_at"],
        start_time=float(row["start_time"]) if row.get("start_time") is not None else None,
    )


async def _get_or_404(uid: str, db: AsyncSession) -> Any:
    result = await db.execute(
        text("SELECT * FROM coi_utterances WHERE id = :id"),
        {"id": uid},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="发言单元不存在")
    return row


async def _shift_order(session_id: str, from_index: int, db: AsyncSession) -> None:
    """把 from_index 及之后的记录 order_index 各加 1，为插入新记录腾位置。"""
    await db.execute(
        text(
            """
            UPDATE coi_utterances
            SET order_index = order_index + 1
            WHERE session_id = :session_id AND order_index >= :from_index
            """
        ),
        {"session_id": session_id, "from_index": from_index},
    )


# ── GET sessions summary ──────────────────────────────────────────────────────

class SessionSummaryOut(ApiModel):
    session_id: str
    session_title: str
    group_id: str
    group_name: str
    total: int
    coded: int


@router.get("/sessions-summary", response_model=list[SessionSummaryOut])
async def list_sessions_summary(
    db: AsyncSession = Depends(get_db),
) -> list[SessionSummaryOut]:
    result = await db.execute(
        text(
            """
            SELECT cu.session_id, cs.session_title,
                   cu.group_id, g.name AS group_name,
                   COUNT(*) AS total,
                   COUNT(cu.coi_category) AS coded
            FROM coi_utterances cu
            JOIN chat_sessions cs ON cs.id = cu.session_id
            JOIN groups g ON g.id = cu.group_id
            GROUP BY cu.session_id, cs.session_title, cu.group_id, g.name
            ORDER BY g.name ASC, cs.session_title ASC
            """
        )
    )
    rows = result.mappings().all()
    return [
        SessionSummaryOut(
            session_id=r["session_id"],
            session_title=r["session_title"],
            group_id=r["group_id"],
            group_name=r["group_name"],
            total=r["total"],
            coded=r["coded"],
        )
        for r in rows
    ]


# ── GET list ──────────────────────────────────────────────────────────────────

@router.get("/", response_model=list[CoiUtteranceOut])
async def list_coi_utterances(
    session_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> list[CoiUtteranceOut]:
    result = await db.execute(
        text(
            """
            SELECT cu.*, u.name AS speaker_name
            FROM coi_utterances cu
            LEFT JOIN users_info u ON u.id = cu.speaker
            WHERE cu.session_id = :session_id
            ORDER BY cu.order_index ASC
            """
        ),
        {"session_id": session_id},
    )
    rows = result.mappings().all()
    return [_row_to_out(r) for r in rows]


# ── POST import ───────────────────────────────────────────────────────────────

@router.post("/import", response_model=ImportResponse)
async def import_from_transcripts(
    session_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> ImportResponse:
    """
    把指定会话的 speech_transcripts 按时间顺序导入 coi_utterances。
    已存在于 source_transcript_ids 中的条目自动跳过（幂等）。
    """
    # 查原始转写
    trans_result = await db.execute(
        text(
            """
            SELECT transcript_id, group_id, session_id, speaker,
                   speaker_user_id, text, start, created_at
            FROM speech_transcripts
            WHERE session_id = :session_id
              AND text IS NOT NULL AND text <> ''
            ORDER BY COALESCE(start, created_at) ASC
            """
        ),
        {"session_id": session_id},
    )
    transcripts = trans_result.mappings().all()
    if not transcripts:
        return ImportResponse(imported=0, skipped=0)

    # 已导入的 transcript_id 集合
    existing_result = await db.execute(
        text(
            "SELECT source_transcript_ids FROM coi_utterances WHERE session_id = :session_id"
        ),
        {"session_id": session_id},
    )
    existing_ids: set[str] = set()
    for row in existing_result.mappings().all():
        for tid in (row["source_transcript_ids"] or []):
            existing_ids.add(tid)

    # 当前最大 order_index
    max_result = await db.execute(
        text(
            "SELECT COALESCE(MAX(order_index), 0) FROM coi_utterances WHERE session_id = :session_id"
        ),
        {"session_id": session_id},
    )
    next_index: int = (max_result.scalar_one() or 0) + 1

    imported = 0
    skipped = 0
    group_id = transcripts[0]["group_id"]

    for tr in transcripts:
        tid = tr["transcript_id"]
        if tid in existing_ids:
            skipped += 1
            continue

        await db.execute(
            text(
                """
                INSERT INTO coi_utterances
                    (id, session_id, group_id, speaker, speaker_user_id,
                     content, source_transcript_ids, order_index, start_time, created_at)
                VALUES
                    (:id, :session_id, :group_id, :speaker, :speaker_user_id,
                     :content, :source_transcript_ids, :order_index, :start_time, NOW())
                """
            ),
            {
                "id": _new_id(),
                "session_id": session_id,
                "group_id": group_id,
                "speaker": tr["speaker"],
                "speaker_user_id": tr["speaker_user_id"],
                "content": tr["text"],
                "source_transcript_ids": [tid],
                "order_index": next_index,
                "start_time": tr["start"].timestamp() if tr["start"] else None,
            },
        )
        next_index += 1
        imported += 1

    await db.commit()
    return ImportResponse(imported=imported, skipped=skipped)


# ── PATCH update ──────────────────────────────────────────────────────────────

@router.patch("/{uid}", response_model=CoiUtteranceOut)
async def update_utterance(
    uid: str,
    payload: CoiUtterancePatch,
    db: AsyncSession = Depends(get_db),
) -> CoiUtteranceOut:
    await _get_or_404(uid, db)

    updates: dict[str, Any] = {}
    if payload.content is not None:
        updates["content"] = payload.content
    if payload.speaker is not None:
        updates["speaker"] = payload.speaker
    if payload.speaker_user_id is not None:
        updates["speaker_user_id"] = payload.speaker_user_id

    if not updates:
        raise HTTPException(status_code=400, detail="没有需要更新的字段")

    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    result = await db.execute(
        text(f"UPDATE coi_utterances SET {set_clause} WHERE id = :uid RETURNING *"),
        {**updates, "uid": uid},
    )
    await db.commit()
    return _row_to_out(result.mappings().first())


# ── DELETE session ────────────────────────────────────────────────────────────

@router.delete("/session", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session_utterances(
    session_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> None:
    """删除某个会话的全部发言单元（用于移除无效会话）。"""
    await db.execute(
        text("DELETE FROM coi_utterances WHERE session_id = :session_id"),
        {"session_id": session_id},
    )
    await db.commit()


# ── DELETE ────────────────────────────────────────────────────────────────────

@router.delete("/{uid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_utterance(
    uid: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        text("DELETE FROM coi_utterances WHERE id = :uid RETURNING id"),
        {"uid": uid},
    )
    await db.commit()
    if not result.first():
        raise HTTPException(status_code=404, detail="发言单元不存在")


# ── POST merge ────────────────────────────────────────────────────────────────

@router.post("/merge", response_model=CoiUtteranceOut)
async def merge_utterances(
    payload: MergeRequest,
    db: AsyncSession = Depends(get_db),
) -> CoiUtteranceOut:
    if len(payload.ids) < 2:
        raise HTTPException(status_code=400, detail="至少需要选择 2 条才能合并")

    result = await db.execute(
        text(
            """
            SELECT * FROM coi_utterances
            WHERE id = ANY(:ids)
            ORDER BY order_index ASC
            """
        ),
        {"ids": payload.ids},
    )
    rows = result.mappings().all()
    if len(rows) != len(payload.ids):
        raise HTTPException(status_code=404, detail="部分发言单元不存在")

    session_ids = {r["session_id"] for r in rows}
    if len(session_ids) > 1:
        raise HTTPException(status_code=400, detail="只能合并同一会话内的发言单元")

    merged_content = "\n".join(r["content"] for r in rows)
    merged_source_ids: list[str] = []
    for r in rows:
        merged_source_ids.extend(r["source_transcript_ids"] or [])

    keep_id = rows[0]["id"]
    delete_ids = [r["id"] for r in rows[1:]]

    await db.execute(
        text(
            """
            UPDATE coi_utterances
            SET content = :content,
                source_transcript_ids = :source_ids,
                coi_category = NULL,
                coded_by = NULL,
                coded_at = NULL
            WHERE id = :id
            """
        ),
        {"content": merged_content, "source_ids": merged_source_ids, "id": keep_id},
    )
    await db.execute(
        text("DELETE FROM coi_utterances WHERE id = ANY(:ids)"),
        {"ids": delete_ids},
    )

    # 重排 order_index 保证连续
    session_id = rows[0]["session_id"]
    all_result = await db.execute(
        text(
            "SELECT id FROM coi_utterances WHERE session_id = :session_id ORDER BY order_index ASC"
        ),
        {"session_id": session_id},
    )
    all_ids = [r["id"] for r in all_result.mappings().all()]
    for idx, rid in enumerate(all_ids, start=1):
        await db.execute(
            text("UPDATE coi_utterances SET order_index = :idx WHERE id = :id"),
            {"idx": idx, "id": rid},
        )

    await db.commit()

    final = await db.execute(
        text("SELECT * FROM coi_utterances WHERE id = :id"),
        {"id": keep_id},
    )
    return _row_to_out(final.mappings().first())


# ── POST split ────────────────────────────────────────────────────────────────

@router.post("/{uid}/split", response_model=list[CoiUtteranceOut])
async def split_utterance(
    uid: str,
    payload: SplitRequest,
    db: AsyncSession = Depends(get_db),
) -> list[CoiUtteranceOut]:
    row = await _get_or_404(uid, db)
    content: str = row["content"]

    if payload.offset <= 0 or payload.offset >= len(content):
        raise HTTPException(status_code=400, detail="拆分位置 offset 超出范围")

    part_a = content[: payload.offset].strip()
    part_b = content[payload.offset :].strip()
    if not part_a or not part_b:
        raise HTTPException(status_code=400, detail="拆分后内容不能为空")

    session_id = row["session_id"]
    split_index = row["order_index"]

    # 把 split_index+1 及之后的记录全部后移一位
    await _shift_order(session_id, split_index + 1, db)

    # 更新原记录为 part_a
    await db.execute(
        text(
            "UPDATE coi_utterances SET content = :content, coi_category = NULL, coded_by = NULL, coded_at = NULL WHERE id = :id"
        ),
        {"content": part_a, "id": uid},
    )

    # 插入 part_b 为新记录
    new_id = _new_id()
    await db.execute(
        text(
            """
            INSERT INTO coi_utterances
                (id, session_id, group_id, speaker, speaker_user_id,
                 content, source_transcript_ids, order_index, created_at)
            VALUES
                (:id, :session_id, :group_id, :speaker, :speaker_user_id,
                 :content, :source_ids, :order_index, NOW())
            """
        ),
        {
            "id": new_id,
            "session_id": session_id,
            "group_id": row["group_id"],
            "speaker": row["speaker"],
            "speaker_user_id": row["speaker_user_id"],
            "content": part_b,
            "source_ids": row["source_transcript_ids"] or [],
            "order_index": split_index + 1,
        },
    )

    await db.commit()

    result = await db.execute(
        text(
            "SELECT * FROM coi_utterances WHERE id = ANY(:ids) ORDER BY order_index ASC"
        ),
        {"ids": [uid, new_id]},
    )
    return [_row_to_out(r) for r in result.mappings().all()]


# ── PATCH code ────────────────────────────────────────────────────────────────

@router.patch("/{uid}/code", response_model=CoiUtteranceOut)
async def code_utterance(
    uid: str,
    payload: CoiCodePatch,
    db: AsyncSession = Depends(get_db),
) -> CoiUtteranceOut:
    if payload.coi_category is not None and payload.coi_category not in COI_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"无效的分类，允许值：{COI_CATEGORIES}")

    await _get_or_404(uid, db)

    coded_at = datetime.utcnow() if payload.coi_category is not None else None

    result = await db.execute(
        text(
            """
            UPDATE coi_utterances
            SET coi_category = :category,
                coded_by     = :coded_by,
                coded_at     = :coded_at
            WHERE id = :id
            RETURNING *
            """
        ),
        {
            "category": payload.coi_category,
            "coded_by": payload.coded_by,
            "coded_at": coded_at,
            "id": uid,
        },
    )
    await db.commit()
    return _row_to_out(result.mappings().first())


# ── POST reorder ──────────────────────────────────────────────────────────────

@router.post("/reorder", status_code=status.HTTP_204_NO_CONTENT)
async def reorder_utterances(
    payload: ReorderRequest,
    db: AsyncSession = Depends(get_db),
) -> None:
    # 先偏移到安全区（避免 UNIQUE 约束中间态冲突），再写入目标值
    OFFSET = 100_000
    for item in payload.items:
        await db.execute(
            text("UPDATE coi_utterances SET order_index = :idx WHERE id = :id"),
            {"idx": item.order_index + OFFSET, "id": item.id},
        )
    for item in payload.items:
        await db.execute(
            text("UPDATE coi_utterances SET order_index = :idx WHERE id = :id"),
            {"idx": item.order_index, "id": item.id},
        )
    await db.commit()
