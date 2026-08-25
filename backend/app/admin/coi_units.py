"""Admin API for CoI unit preparation and multi-coder coding."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..api_model import ApiModel
from ..db import get_db
from .deps import require_admin

router = APIRouter(
    prefix="/api/admin/coi-units",
    tags=["admin-coi-units"],
    dependencies=[Depends(require_admin)],
)

COI_CATEGORIES = {"TE", "EX", "IN", "RE", "OTHER"}
CODER_ROLES = {"coder_a", "coder_b", "final"}

CoiCategory = Literal["TE", "EX", "IN", "RE", "OTHER"]
CoderRole = Literal["coder_a", "coder_b", "final"]


# ── Schemas ───────────────────────────────────────────────────────────────────

class CoiUnitIn(ApiModel):
    order_index: int
    content: str
    speaker: str | None = None
    speaker_user_id: str | None = None
    source_transcript_ids: list[str] = Field(default_factory=list)
    start_time: float | None = None


class CoiUnitOut(ApiModel):
    id: str
    session_id: str
    group_id: str
    speaker: str | None
    speaker_user_id: str | None
    content: str
    source_transcript_ids: list[str]
    order_index: int
    start_time: float | None
    created_at: datetime
    updated_at: datetime


class SaveUnitsRequest(ApiModel):
    units: list[CoiUnitIn]


class SaveUnitsResponse(ApiModel):
    saved: int
    deleted_previous: int
    deleted_codes: int


class ImportUnitsResponse(ApiModel):
    imported: int
    deleted_previous: int
    deleted_codes: int


class SplitUnitRequest(ApiModel):
    first_content: str
    second_content: str


class UnitMutationResponse(ApiModel):
    units: list[CoiUnitOut]
    invalidated_codes: int


class CoiCodeIn(ApiModel):
    unit_id: str
    coi_categories: list[CoiCategory]
    coded_by: str | None = None


class SaveCodesRequest(ApiModel):
    codes: list[CoiCodeIn]


class SaveCodesResponse(ApiModel):
    saved: int
    coder_role: CoderRole


class CoiCodeOut(ApiModel):
    unit_id: str
    coder_role: CoderRole
    coi_categories: list[CoiCategory]
    coded_by: str | None
    coded_at: datetime
    updated_at: datetime


class UnitWithCodeOut(ApiModel):
    unit: CoiUnitOut
    code: CoiCodeOut | None


class AgreementUnitOut(ApiModel):
    unit: CoiUnitOut
    coder_a: CoiCodeOut | None
    coder_b: CoiCodeOut | None
    final: CoiCodeOut | None
    agreed: bool


class SessionSummaryOut(ApiModel):
    session_id: str
    session_title: str
    group_id: str
    group_name: str
    units_total: int
    coder_a_coded: int
    coder_b_coded: int
    final_coded: int


# ── Helpers ───────────────────────────────────────────────────────────────────

def _new_unit_id() -> str:
    return "cuu" + uuid.uuid4().hex[:12]


def _new_code_id() -> str:
    return "cuc" + uuid.uuid4().hex[:12]


def _validate_coder_role(coder_role: str) -> CoderRole:
    if coder_role not in CODER_ROLES:
        raise HTTPException(status_code=400, detail="无效的编码角色")
    return coder_role  # type: ignore[return-value]


def _require_structure_editor(coder_role: str) -> None:
    if coder_role != "coder_a":
        raise HTTPException(status_code=403, detail="只有研究员 A 可以拆分或合并观点单元")


def _validate_coi_category(coi_category: str) -> CoiCategory:
    if coi_category not in COI_CATEGORIES:
        raise HTTPException(status_code=400, detail="无效的 CoI 分类")
    return coi_category  # type: ignore[return-value]


def _normalize_coi_categories(coi_categories: list[str]) -> list[CoiCategory]:
    if not coi_categories:
        raise HTTPException(status_code=400, detail="每条观点至少需要一个 CoI 分类")
    if len(coi_categories) > len(COI_CATEGORIES):
        raise HTTPException(status_code=400, detail="CoI 分类数量不能超过 4 个")
    selected = {_validate_coi_category(category) for category in coi_categories}
    if "OTHER" in selected and len(selected) > 1:
        raise HTTPException(status_code=400, detail="OTHER 不能与 TE、EX、IN、RE 同时选择")
    return [category for category in ("TE", "EX", "IN", "RE", "OTHER") if category in selected]  # type: ignore[misc]


async def _get_session_group_id(db: AsyncSession, session_id: str) -> str:
    result = await db.execute(
        text("SELECT group_id FROM chat_sessions WHERE id = :sid"),
        {"sid": session_id},
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="会话不存在")
    return str(row[0])


def _unit_row_to_out(row: Any) -> CoiUnitOut:
    return CoiUnitOut(
        id=row["id"],
        session_id=row["session_id"],
        group_id=row["group_id"],
        speaker=row["speaker"],
        speaker_user_id=row["speaker_user_id"],
        content=row["content"],
        source_transcript_ids=row["source_transcript_ids"] or [],
        order_index=row["order_index"],
        start_time=float(row["start_time"]) if row.get("start_time") is not None else None,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _code_row_to_out(row: Any) -> CoiCodeOut:
    return CoiCodeOut(
        unit_id=row["unit_id"],
        coder_role=_validate_coder_role(row["coder_role"]),
        coi_categories=_normalize_coi_categories(list(row["coi_categories"] or [])),
        coded_by=row["coded_by"],
        coded_at=row["coded_at"],
        updated_at=row["updated_at"],
    )


def _joined_code_to_out(row: Any, prefix: str = "code") -> CoiCodeOut | None:
    unit_id = row.get(f"{prefix}_unit_id")
    if unit_id is None:
        return None
    return CoiCodeOut(
        unit_id=unit_id,
        coder_role=_validate_coder_role(row[f"{prefix}_coder_role"]),
        coi_categories=_normalize_coi_categories(list(row[f"{prefix}_coi_categories"] or [])),
        coded_by=row[f"{prefix}_coded_by"],
        coded_at=row[f"{prefix}_coded_at"],
        updated_at=row[f"{prefix}_updated_at"],
    )


def _validate_units_payload(units: list[CoiUnitIn]) -> None:
    seen: set[int] = set()
    for unit in units:
        if unit.order_index <= 0:
            raise HTTPException(status_code=400, detail="观点单元序号必须大于 0")
        if unit.order_index in seen:
            raise HTTPException(status_code=400, detail="观点单元序号不能重复")
        seen.add(unit.order_index)
        if not unit.content.strip():
            raise HTTPException(status_code=400, detail="观点单元内容不能为空")


def _validate_codes_payload(codes: list[CoiCodeIn]) -> None:
    seen: set[str] = set()
    for code in codes:
        if code.unit_id in seen:
            raise HTTPException(status_code=400, detail="同一观点单元不能重复提交编码")
        seen.add(code.unit_id)
        code.coi_categories = _normalize_coi_categories(code.coi_categories)


async def _count_codes(db: AsyncSession, session_id: str) -> int:
    result = await db.execute(
        text("SELECT COUNT(*) FROM coi_unit_codes WHERE session_id = :sid"),
        {"sid": session_id},
    )
    return int(result.scalar_one())


async def _count_units(db: AsyncSession, session_id: str) -> int:
    result = await db.execute(
        text("SELECT COUNT(*) FROM coi_units WHERE session_id = :sid"),
        {"sid": session_id},
    )
    return int(result.scalar_one())


async def _ensure_units_belong_to_session(
    db: AsyncSession,
    session_id: str,
    unit_ids: list[str],
) -> None:
    if not unit_ids:
        return
    result = await db.execute(
        text("""
            SELECT COUNT(*)
            FROM coi_units
            WHERE session_id = :sid AND id = ANY(:unit_ids)
        """),
        {"sid": session_id, "unit_ids": unit_ids},
    )
    if int(result.scalar_one()) != len(set(unit_ids)):
        raise HTTPException(status_code=400, detail="编码中包含不属于该会话的观点单元")


async def _lock_session_units(db: AsyncSession, session_id: str) -> list[Any]:
    result = await db.execute(
        text("""
            SELECT *
            FROM coi_units
            WHERE session_id = :sid
            ORDER BY order_index ASC
            FOR UPDATE
        """),
        {"sid": session_id},
    )
    return list(result.mappings().all())


async def _delete_unit_codes(db: AsyncSession, unit_ids: list[str]) -> int:
    result = await db.execute(
        text("""
            DELETE FROM coi_unit_codes
            WHERE unit_id = ANY(:unit_ids)
            RETURNING id
        """),
        {"unit_ids": unit_ids},
    )
    return len(result.all())


async def _shift_orders_up_after(
    db: AsyncSession,
    session_id: str,
    order_index: int,
    max_order: int,
) -> None:
    """Make one empty order slot after order_index without transient collisions."""
    if order_index >= max_order:
        return
    offset = max_order + 1
    await db.execute(
        text("""
            UPDATE coi_units
            SET order_index = order_index + :offset
            WHERE session_id = :sid AND order_index > :order_index
        """),
        {"sid": session_id, "order_index": order_index, "offset": offset},
    )
    await db.execute(
        text("""
            UPDATE coi_units
            SET order_index = order_index - :offset + 1
            WHERE session_id = :sid AND order_index > :offset
        """),
        {"sid": session_id, "offset": offset},
    )


async def _shift_orders_down_after(
    db: AsyncSession,
    session_id: str,
    order_index: int,
    max_order: int,
) -> None:
    """Close one order slot after deleting adjacent units without collisions."""
    if order_index >= max_order:
        return
    offset = max_order + 1
    await db.execute(
        text("""
            UPDATE coi_units
            SET order_index = order_index + :offset
            WHERE session_id = :sid AND order_index > :order_index
        """),
        {"sid": session_id, "order_index": order_index, "offset": offset},
    )
    await db.execute(
        text("""
            UPDATE coi_units
            SET order_index = order_index - :offset - 1
            WHERE session_id = :sid AND order_index > :offset
        """),
        {"sid": session_id, "offset": offset},
    )


# ── Step 4: unit preparation endpoints ────────────────────────────────────────

@router.get("/sessions-summary", response_model=list[SessionSummaryOut])
async def list_sessions_summary(
    db: AsyncSession = Depends(get_db),
) -> list[SessionSummaryOut]:
    result = await db.execute(
        text("""
            WITH unit_counts AS (
                SELECT session_id, group_id, COUNT(*) AS units_total
                FROM coi_units
                GROUP BY session_id, group_id
            ),
            code_counts AS (
                SELECT session_id,
                       COUNT(*) FILTER (WHERE coder_role = 'coder_a') AS coder_a_coded,
                       COUNT(*) FILTER (WHERE coder_role = 'coder_b') AS coder_b_coded,
                       COUNT(*) FILTER (WHERE coder_role = 'final') AS final_coded
                FROM coi_unit_codes
                GROUP BY session_id
            )
            SELECT uc.session_id, cs.session_title,
                   uc.group_id, g.name AS group_name,
                   uc.units_total,
                   COALESCE(cc.coder_a_coded, 0) AS coder_a_coded,
                   COALESCE(cc.coder_b_coded, 0) AS coder_b_coded,
                   COALESCE(cc.final_coded, 0) AS final_coded
            FROM unit_counts uc
            JOIN chat_sessions cs ON cs.id = uc.session_id
            JOIN groups g ON g.id = uc.group_id
            LEFT JOIN code_counts cc ON cc.session_id = uc.session_id
            ORDER BY g.name ASC, cs.session_title ASC
        """)
    )
    return [
        SessionSummaryOut(
            session_id=row["session_id"],
            session_title=row["session_title"],
            group_id=row["group_id"],
            group_name=row["group_name"],
            units_total=row["units_total"],
            coder_a_coded=row["coder_a_coded"],
            coder_b_coded=row["coder_b_coded"],
            final_coded=row["final_coded"],
        )
        for row in result.mappings().all()
    ]


@router.get("/sessions/{session_id}", response_model=list[CoiUnitOut])
async def list_session_units(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[CoiUnitOut]:
    await _get_session_group_id(db, session_id)
    result = await db.execute(
        text("""
            SELECT *
            FROM coi_units
            WHERE session_id = :sid
            ORDER BY order_index ASC
        """),
        {"sid": session_id},
    )
    return [_unit_row_to_out(row) for row in result.mappings().all()]


@router.post(
    "/sessions/{session_id}/units/{unit_id}/split",
    response_model=UnitMutationResponse,
)
async def split_session_unit(
    session_id: str,
    unit_id: str,
    payload: SplitUnitRequest,
    coder_role: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> UnitMutationResponse:
    """Split one shared unit; invalidate only codes attached to that unit."""
    _require_structure_editor(coder_role)
    await _get_session_group_id(db, session_id)
    first_content = payload.first_content.strip()
    second_content = payload.second_content.strip()
    if not first_content or not second_content:
        raise HTTPException(status_code=400, detail="拆分后的两段内容都不能为空")

    rows = await _lock_session_units(db, session_id)
    target = next((row for row in rows if row["id"] == unit_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="观点单元不存在或已被调整，请重新加载")

    max_order = max((int(row["order_index"]) for row in rows), default=0)
    order_index = int(target["order_index"])
    new_ids = [_new_unit_id(), _new_unit_id()]
    invalidated_codes = await _delete_unit_codes(db, [unit_id])
    await db.execute(
        text("DELETE FROM coi_units WHERE id = :unit_id"),
        {"unit_id": unit_id},
    )
    await _shift_orders_up_after(db, session_id, order_index, max_order)

    shared = {
        "session_id": session_id,
        "group_id": target["group_id"],
        "speaker": target["speaker"],
        "speaker_user_id": target["speaker_user_id"],
        "source_transcript_ids": target["source_transcript_ids"] or [],
        "start_time": target["start_time"],
    }
    await db.execute(
        text("""
            INSERT INTO coi_units
                (id, session_id, group_id, speaker, speaker_user_id,
                 content, source_transcript_ids, order_index, start_time)
            VALUES
                (:id, :session_id, :group_id, :speaker, :speaker_user_id,
                 :content, :source_transcript_ids, :order_index, :start_time)
        """),
        [
            {**shared, "id": new_ids[0], "content": first_content, "order_index": order_index},
            {**shared, "id": new_ids[1], "content": second_content, "order_index": order_index + 1},
        ],
    )
    result = await db.execute(
        text("SELECT * FROM coi_units WHERE id = ANY(:unit_ids) ORDER BY order_index ASC"),
        {"unit_ids": new_ids},
    )
    units = [_unit_row_to_out(row) for row in result.mappings().all()]
    await db.commit()
    return UnitMutationResponse(units=units, invalidated_codes=invalidated_codes)


@router.post(
    "/sessions/{session_id}/units/{unit_id}/merge-next",
    response_model=UnitMutationResponse,
)
async def merge_session_unit_with_next(
    session_id: str,
    unit_id: str,
    coder_role: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> UnitMutationResponse:
    """Merge one shared unit with its next neighbor; invalidate only their codes."""
    _require_structure_editor(coder_role)
    await _get_session_group_id(db, session_id)
    rows = await _lock_session_units(db, session_id)
    target_index = next((i for i, row in enumerate(rows) if row["id"] == unit_id), -1)
    if target_index < 0:
        raise HTTPException(status_code=404, detail="观点单元不存在或已被调整，请重新加载")
    if target_index >= len(rows) - 1:
        raise HTTPException(status_code=400, detail="最后一条观点无法与下一条合并")

    current = rows[target_index]
    following = rows[target_index + 1]
    current_order = int(current["order_index"])
    following_order = int(following["order_index"])
    if following_order != current_order + 1:
        raise HTTPException(status_code=409, detail="观点序号已变化，请重新加载后再试")

    merged_id = _new_unit_id()
    invalidated_codes = await _delete_unit_codes(db, [current["id"], following["id"]])
    await db.execute(
        text("DELETE FROM coi_units WHERE id = ANY(:unit_ids)"),
        {"unit_ids": [current["id"], following["id"]]},
    )
    max_order = max((int(row["order_index"]) for row in rows), default=0)
    await _shift_orders_down_after(db, session_id, following_order, max_order)

    source_ids = list(dict.fromkeys([
        *(current["source_transcript_ids"] or []),
        *(following["source_transcript_ids"] or []),
    ]))
    await db.execute(
        text("""
            INSERT INTO coi_units
                (id, session_id, group_id, speaker, speaker_user_id,
                 content, source_transcript_ids, order_index, start_time)
            VALUES
                (:id, :session_id, :group_id, :speaker, :speaker_user_id,
                 :content, :source_transcript_ids, :order_index, :start_time)
        """),
        {
            "id": merged_id,
            "session_id": session_id,
            "group_id": current["group_id"],
            "speaker": current["speaker"],
            "speaker_user_id": current["speaker_user_id"],
            "content": f'{str(current["content"]).strip()} {str(following["content"]).strip()}',
            "source_transcript_ids": source_ids,
            "order_index": current_order,
            "start_time": current["start_time"],
        },
    )
    result = await db.execute(
        text("SELECT * FROM coi_units WHERE id = :unit_id"),
        {"unit_id": merged_id},
    )
    row = result.mappings().first()
    if row is None:
        raise HTTPException(status_code=500, detail="合并观点保存失败")
    unit = _unit_row_to_out(row)
    await db.commit()
    return UnitMutationResponse(units=[unit], invalidated_codes=invalidated_codes)


@router.post("/sessions/{session_id}/import-from-preprocess", response_model=ImportUnitsResponse)
async def import_units_from_preprocess(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> ImportUnitsResponse:
    group_id = await _get_session_group_id(db, session_id)

    source_result = await db.execute(
        text("""
            SELECT speaker, speaker_user_id, content, source_transcript_ids,
                   order_index, start_time
            FROM coi_utterances
            WHERE session_id = :sid
            ORDER BY order_index ASC
        """),
        {"sid": session_id},
    )
    source_rows = source_result.mappings().all()
    if not source_rows:
        return ImportUnitsResponse(imported=0, deleted_previous=0, deleted_codes=0)

    deleted_codes = await _count_codes(db, session_id)
    deleted_previous = await _count_units(db, session_id)

    await db.execute(
        text("DELETE FROM coi_unit_codes WHERE session_id = :sid"),
        {"sid": session_id},
    )
    await db.execute(
        text("DELETE FROM coi_units WHERE session_id = :sid"),
        {"sid": session_id},
    )

    rows = [
        {
            "id": _new_unit_id(),
            "session_id": session_id,
            "group_id": group_id,
            "speaker": row["speaker"],
            "speaker_user_id": row["speaker_user_id"],
            "content": row["content"],
            "source_transcript_ids": row["source_transcript_ids"] or [],
            "order_index": row["order_index"],
            "start_time": row["start_time"],
        }
        for row in source_rows
    ]
    await db.execute(
        text("""
            INSERT INTO coi_units
                (id, session_id, group_id, speaker, speaker_user_id,
                 content, source_transcript_ids, order_index, start_time)
            VALUES
                (:id, :session_id, :group_id, :speaker, :speaker_user_id,
                 :content, :source_transcript_ids, :order_index, :start_time)
        """),
        rows,
    )
    await db.commit()
    return ImportUnitsResponse(
        imported=len(rows),
        deleted_previous=deleted_previous,
        deleted_codes=deleted_codes,
    )


@router.put("/sessions/{session_id}", response_model=SaveUnitsResponse)
async def save_session_units(
    session_id: str,
    payload: SaveUnitsRequest,
    db: AsyncSession = Depends(get_db),
) -> SaveUnitsResponse:
    """Replace all prepared units for one session and clear its new-table codes."""
    group_id = await _get_session_group_id(db, session_id)
    _validate_units_payload(payload.units)

    deleted_codes = await _count_codes(db, session_id)
    deleted_previous = await _count_units(db, session_id)

    await db.execute(
        text("DELETE FROM coi_unit_codes WHERE session_id = :sid"),
        {"sid": session_id},
    )
    await db.execute(
        text("DELETE FROM coi_units WHERE session_id = :sid"),
        {"sid": session_id},
    )

    if payload.units:
        rows = [
            {
                "id": _new_unit_id(),
                "session_id": session_id,
                "group_id": group_id,
                "speaker": unit.speaker,
                "speaker_user_id": unit.speaker_user_id,
                "content": unit.content.strip(),
                "source_transcript_ids": unit.source_transcript_ids,
                "order_index": unit.order_index,
                "start_time": unit.start_time,
            }
            for unit in payload.units
        ]
        await db.execute(
            text("""
                INSERT INTO coi_units
                    (id, session_id, group_id, speaker, speaker_user_id,
                     content, source_transcript_ids, order_index, start_time)
                VALUES
                    (:id, :session_id, :group_id, :speaker, :speaker_user_id,
                     :content, :source_transcript_ids, :order_index, :start_time)
            """),
            rows,
        )

    await db.commit()
    return SaveUnitsResponse(
        saved=len(payload.units),
        deleted_previous=deleted_previous,
        deleted_codes=deleted_codes,
    )


# ── Step 5: independent coding endpoints ──────────────────────────────────────

@router.get("/sessions/{session_id}/codes", response_model=list[UnitWithCodeOut])
async def get_session_codes(
    session_id: str,
    coder_role: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> list[UnitWithCodeOut]:
    role = _validate_coder_role(coder_role)
    await _get_session_group_id(db, session_id)
    result = await db.execute(
        text("""
            SELECT u.*,
                   c.unit_id AS code_unit_id,
                   c.coder_role AS code_coder_role,
                   c.coi_categories AS code_coi_categories,
                   c.coded_by AS code_coded_by,
                   c.coded_at AS code_coded_at,
                   c.updated_at AS code_updated_at
            FROM coi_units u
            LEFT JOIN coi_unit_codes c
              ON c.unit_id = u.id AND c.coder_role = :role
            WHERE u.session_id = :sid
            ORDER BY u.order_index ASC
        """),
        {"sid": session_id, "role": role},
    )
    return [
        UnitWithCodeOut(unit=_unit_row_to_out(row), code=_joined_code_to_out(row))
        for row in result.mappings().all()
    ]


@router.put("/sessions/{session_id}/codes", response_model=SaveCodesResponse)
async def save_session_codes(
    session_id: str,
    payload: SaveCodesRequest,
    coder_role: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> SaveCodesResponse:
    """Replace all codes for one session and one coder role."""
    role = _validate_coder_role(coder_role)
    await _get_session_group_id(db, session_id)
    _validate_codes_payload(payload.codes)
    await _ensure_units_belong_to_session(
        db,
        session_id,
        [code.unit_id for code in payload.codes],
    )

    await db.execute(
        text("""
            DELETE FROM coi_unit_codes
            WHERE session_id = :sid AND coder_role = :role
        """),
        {"sid": session_id, "role": role},
    )

    if payload.codes:
        unit_result = await db.execute(
            text("""
                SELECT id, group_id
                FROM coi_units
                WHERE session_id = :sid AND id = ANY(:unit_ids)
            """),
            {"sid": session_id, "unit_ids": [code.unit_id for code in payload.codes]},
        )
        unit_group_by_id = {
            row["id"]: row["group_id"]
            for row in unit_result.mappings().all()
        }
        rows = [
            {
                "id": _new_code_id(),
                "unit_id": code.unit_id,
                "session_id": session_id,
                "group_id": unit_group_by_id[code.unit_id],
                "coder_role": role,
                "coi_categories": code.coi_categories,
                "coded_by": code.coded_by,
            }
            for code in payload.codes
        ]
        await db.execute(
            text("""
                INSERT INTO coi_unit_codes
                    (id, unit_id, session_id, group_id, coder_role,
                     coi_categories, coded_by, coded_at, updated_at)
                VALUES
                    (:id, :unit_id, :session_id, :group_id, :coder_role,
                     :coi_categories, :coded_by, NOW(), NOW())
            """),
            rows,
        )

    await db.commit()
    return SaveCodesResponse(saved=len(payload.codes), coder_role=role)


# ── Step 6: final agreement endpoints ─────────────────────────────────────────

@router.get("/sessions/{session_id}/agreement", response_model=list[AgreementUnitOut])
async def get_session_agreement(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[AgreementUnitOut]:
    await _get_session_group_id(db, session_id)
    result = await db.execute(
        text("""
            SELECT u.*,
                   ca.unit_id AS coder_a_unit_id,
                   ca.coder_role AS coder_a_coder_role,
                   ca.coi_categories AS coder_a_coi_categories,
                   ca.coded_by AS coder_a_coded_by,
                   ca.coded_at AS coder_a_coded_at,
                   ca.updated_at AS coder_a_updated_at,
                   cb.unit_id AS coder_b_unit_id,
                   cb.coder_role AS coder_b_coder_role,
                   cb.coi_categories AS coder_b_coi_categories,
                   cb.coded_by AS coder_b_coded_by,
                   cb.coded_at AS coder_b_coded_at,
                   cb.updated_at AS coder_b_updated_at,
                   cf.unit_id AS final_unit_id,
                   cf.coder_role AS final_coder_role,
                   cf.coi_categories AS final_coi_categories,
                   cf.coded_by AS final_coded_by,
                   cf.coded_at AS final_coded_at,
                   cf.updated_at AS final_updated_at
            FROM coi_units u
            LEFT JOIN coi_unit_codes ca
              ON ca.unit_id = u.id AND ca.coder_role = 'coder_a'
            LEFT JOIN coi_unit_codes cb
              ON cb.unit_id = u.id AND cb.coder_role = 'coder_b'
            LEFT JOIN coi_unit_codes cf
              ON cf.unit_id = u.id AND cf.coder_role = 'final'
            WHERE u.session_id = :sid
            ORDER BY u.order_index ASC
        """),
        {"sid": session_id},
    )
    items: list[AgreementUnitOut] = []
    for row in result.mappings().all():
        coder_a = _joined_code_to_out(row, "coder_a")
        coder_b = _joined_code_to_out(row, "coder_b")
        final = _joined_code_to_out(row, "final")
        items.append(
            AgreementUnitOut(
                unit=_unit_row_to_out(row),
                coder_a=coder_a,
                coder_b=coder_b,
                final=final,
                agreed=(
                    coder_a is not None
                    and coder_b is not None
                    and set(coder_a.coi_categories) == set(coder_b.coi_categories)
                ),
            )
        )
    return items


@router.put("/sessions/{session_id}/final-codes", response_model=SaveCodesResponse)
async def save_session_final_codes(
    session_id: str,
    payload: SaveCodesRequest,
    db: AsyncSession = Depends(get_db),
) -> SaveCodesResponse:
    return await save_session_codes(
        session_id=session_id,
        payload=payload,
        coder_role="final",
        db=db,
    )
