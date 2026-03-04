from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from .deps import require_admin
from .schemas import Page, PageMeta


router = APIRouter(prefix="/api/admin/memberships", tags=["admin-memberships"])


class AdminMembershipOut(BaseModel):
    id: str
    group_id: str
    user_id: str
    role: str
    status: str
    created_at: Any


class AdminMembershipUpdate(BaseModel):
    role: str | None = None
    status: str | None = None


@router.get(
    "/",
    response_model=Page[AdminMembershipOut],
    dependencies=[Depends(require_admin)],
)
async def list_memberships(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    group_id: str | None = None,
    user_id: str | None = None,
    status_filter: str | None = Query(
        default=None,
        alias="status",
        description="按成员状态过滤，例如 active/left/kicked",
    ),
    db: AsyncSession = Depends(get_db),
) -> Page[AdminMembershipOut]:
    offset = (page - 1) * page_size

    where_clauses = ["1=1"]
    params: dict[str, Any] = {}

    if group_id:
        where_clauses.append("group_id = :group_id")
        params["group_id"] = group_id
    if user_id:
        where_clauses.append("user_id = :user_id")
        params["user_id"] = user_id
    if status_filter:
        where_clauses.append("status = :status")
        params["status"] = status_filter

    where_sql = " AND ".join(where_clauses)

    count_result = await db.execute(
        text(f"SELECT COUNT(*) AS cnt FROM group_memberships WHERE {where_sql}"),
        params,
    )
    total = count_result.scalar_one()

    query = text(
        f"""
        SELECT id, group_id, user_id, role, status, created_at
        FROM group_memberships
        WHERE {where_sql}
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :offset
        """
    )
    params_with_page = dict(params)
    params_with_page["limit"] = page_size
    params_with_page["offset"] = offset

    result = await db.execute(query, params_with_page)
    rows = result.mappings().all()
    items = [AdminMembershipOut.model_validate(dict(row)) for row in rows]

    return Page[AdminMembershipOut](
        items=items,
        meta=PageMeta(total=total, page=page, page_size=page_size),
    )


@router.get(
    "/{membership_id}",
    response_model=AdminMembershipOut,
    dependencies=[Depends(require_admin)],
)
async def get_membership_detail(
    membership_id: str,
    db: AsyncSession = Depends(get_db),
) -> AdminMembershipOut:
    result = await db.execute(
        text(
            """
            SELECT id, group_id, user_id, role, status, created_at
            FROM group_memberships
            WHERE id = :id
            """
        ),
        {"id": membership_id},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="成员关系不存在",
        )
    return AdminMembershipOut.model_validate(dict(row))


@router.patch(
    "/{membership_id}",
    response_model=AdminMembershipOut,
    dependencies=[Depends(require_admin)],
)
async def update_membership(
    membership_id: str,
    payload: AdminMembershipUpdate,
    db: AsyncSession = Depends(get_db),
) -> AdminMembershipOut:
    if payload.role is None and payload.status is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="没有任何可更新字段",
        )

    sets: list[str] = []
    params: dict[str, Any] = {"id": membership_id}

    if payload.role is not None:
        sets.append("role = :role")
        params["role"] = payload.role
    if payload.status is not None:
        sets.append("status = :status")
        params["status"] = payload.status

    set_sql = ", ".join(sets)

    result = await db.execute(
        text(
            f"""
            UPDATE group_memberships
            SET {set_sql}
            WHERE id = :id
            RETURNING id, group_id, user_id, role, status, created_at
            """
        ),
        params,
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="成员关系不存在",
        )

    await db.commit()
    return AdminMembershipOut.model_validate(dict(row))


@router.delete(
    "/{membership_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
async def delete_membership(
    membership_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        text("DELETE FROM group_memberships WHERE id = :id"),
        {"id": membership_id},
    )
    if result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="成员关系不存在",
        )
    await db.commit()

