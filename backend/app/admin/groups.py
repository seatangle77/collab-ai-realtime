from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from .deps import require_admin
from .schemas import Page, PageMeta


router = APIRouter(prefix="/api/admin/groups", tags=["admin-groups"])


class AdminGroupOut(BaseModel):
    id: str
    name: str
    created_at: Any
    is_active: bool


class AdminGroupUpdate(BaseModel):
    name: str | None = None
    is_active: bool | None = None


@router.get(
    "/",
    response_model=Page[AdminGroupOut],
    dependencies=[Depends(require_admin)],
)
async def list_groups(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    name: str | None = None,
    is_active: bool | None = None,
    db: AsyncSession = Depends(get_db),
) -> Page[AdminGroupOut]:
    offset = (page - 1) * page_size

    where_clauses = ["1=1"]
    params: dict[str, Any] = {}

    if name:
        where_clauses.append("name ILIKE :name")
        params["name"] = f"%{name}%"
    if is_active is not None:
        where_clauses.append("is_active = :is_active")
        params["is_active"] = is_active

    where_sql = " AND ".join(where_clauses)

    count_result = await db.execute(
        text(f"SELECT COUNT(*) AS cnt FROM groups WHERE {where_sql}"),
        params,
    )
    total = count_result.scalar_one()

    query = text(
        f"""
        SELECT id, name, created_at, is_active
        FROM groups
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
    items = [AdminGroupOut.model_validate(dict(row)) for row in rows]

    return Page[AdminGroupOut](
        items=items,
        meta=PageMeta(total=total, page=page, page_size=page_size),
    )


@router.get(
    "/{group_id}",
    response_model=AdminGroupOut,
    dependencies=[Depends(require_admin)],
)
async def get_group_detail(
    group_id: str,
    db: AsyncSession = Depends(get_db),
) -> AdminGroupOut:
    result = await db.execute(
        text(
            """
            SELECT id, name, created_at, is_active
            FROM groups
            WHERE id = :id
            """
        ),
        {"id": group_id},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="群组不存在",
        )
    return AdminGroupOut.model_validate(dict(row))


@router.patch(
    "/{group_id}",
    response_model=AdminGroupOut,
    dependencies=[Depends(require_admin)],
)
async def update_group(
    group_id: str,
    payload: AdminGroupUpdate,
    db: AsyncSession = Depends(get_db),
) -> AdminGroupOut:
    if payload.name is None and payload.is_active is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="没有任何可更新字段",
        )

    sets: list[str] = []
    params: dict[str, Any] = {"id": group_id}

    if payload.name is not None:
        sets.append("name = :name")
        params["name"] = payload.name
    if payload.is_active is not None:
        sets.append("is_active = :is_active")
        params["is_active"] = payload.is_active

    set_sql = ", ".join(sets)

    result = await db.execute(
        text(
            f"""
            UPDATE groups
            SET {set_sql}
            WHERE id = :id
            RETURNING id, name, created_at, is_active
            """
        ),
        params,
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="群组不存在",
        )

    await db.commit()
    return AdminGroupOut.model_validate(dict(row))


@router.delete(
    "/{group_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
async def delete_group(
    group_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        text("DELETE FROM groups WHERE id = :id"),
        {"id": group_id},
    )
    if result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="群组不存在",
        )
    await db.commit()

