"""Admin read-only + delete API for questionnaire_entries."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..api_model import ApiModel
from ..db import get_db
from .deps import require_admin

router = APIRouter(
    prefix="/api/admin/questionnaire-entries",
    tags=["admin-questionnaire-entries"],
    dependencies=[Depends(require_admin)],
)


class QuestionnaireEntryAdminOut(ApiModel):
    user_id: str
    user_name: str | None
    group_id: str | None
    group_name: str | None
    condition: str | None
    srcc_responses: dict | None
    srcc_result: dict | None
    pcs_responses: dict | None
    pcs_result: dict | None
    updated_at: str | None


class PaginationMeta(ApiModel):
    total: int
    page: int
    page_size: int


class QuestionnaireEntryListOut(ApiModel):
    items: list[QuestionnaireEntryAdminOut]
    meta: PaginationMeta


def _build_row(row: Any) -> QuestionnaireEntryAdminOut:
    return QuestionnaireEntryAdminOut(
        user_id=row["user_id"],
        user_name=row["user_name"],
        group_id=row["group_id"],
        group_name=row["group_name"],
        condition=row["condition"],
        srcc_responses=row["srcc_responses"],
        srcc_result=row["srcc_result"],
        pcs_responses=row["pcs_responses"],
        pcs_result=row["pcs_result"],
        updated_at=row["updated_at"].isoformat() if row["updated_at"] else None,
    )


@router.get("", response_model=QuestionnaireEntryListOut)
async def list_entries(
    group_id: str | None = Query(default=None),
    condition: str | None = Query(default=None),
    updated_from: str | None = Query(default=None),
    updated_to: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    where_clauses = []
    params: dict[str, Any] = {"limit": page_size, "offset": (page - 1) * page_size}

    if group_id:
        where_clauses.append("qe.group_id = :group_id")
        params["group_id"] = group_id
    if condition:
        where_clauses.append("qe.condition = :condition")
        params["condition"] = condition
    if updated_from:
        where_clauses.append("qe.updated_at >= :updated_from")
        params["updated_from"] = updated_from
    if updated_to:
        where_clauses.append("qe.updated_at <= :updated_to")
        params["updated_to"] = updated_to

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    count_row = await db.execute(
        text(f"""
            SELECT COUNT(*) AS total
            FROM questionnaire_entries qe
            {where_sql}
        """),
        params,
    )
    total = count_row.mappings().first()["total"]

    rows = await db.execute(
        text(f"""
            SELECT
                qe.user_id,
                ui.name        AS user_name,
                qe.group_id,
                g.name         AS group_name,
                qe.condition,
                qe.srcc_responses,
                qe.srcc_result,
                qe.pcs_responses,
                qe.pcs_result,
                qe.updated_at
            FROM questionnaire_entries qe
            LEFT JOIN users_info ui ON ui.id = qe.user_id
            LEFT JOIN groups     g  ON g.id  = qe.group_id
            {where_sql}
            ORDER BY qe.updated_at DESC
            LIMIT :limit OFFSET :offset
        """),
        params,
    )

    items = [_build_row(row) for row in rows.mappings()]
    return QuestionnaireEntryListOut(
        items=items,
        meta=PaginationMeta(total=total, page=page, page_size=page_size),
    )


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entry(user_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text("DELETE FROM questionnaire_entries WHERE user_id = :user_id RETURNING user_id"),
        {"user_id": user_id},
    )
    if not result.fetchone():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="记录不存在")
    await db.commit()
