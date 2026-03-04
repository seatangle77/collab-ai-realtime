from __future__ import annotations

from typing import Any
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from .deps import require_admin
from .schemas import Page, PageMeta


router = APIRouter(prefix="/api/admin/users", tags=["admin-users"])


class AdminUserOut(BaseModel):
    id: str
    name: str
    email: str
    device_token: str | None = None
    created_at: datetime


class AdminUserUpdate(BaseModel):
    name: str | None = None
    device_token: str | None = None


@router.get("/", response_model=Page[AdminUserOut], dependencies=[Depends(require_admin)])
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    email: str | None = None,
    name: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> Page[AdminUserOut]:
    offset = (page - 1) * page_size

    where_clauses = ["1=1"]
    params: dict[str, Any] = {}

    if email:
        where_clauses.append("email ILIKE :email")
        params["email"] = f"%{email}%"
    if name:
        where_clauses.append("name ILIKE :name")
        params["name"] = f"%{name}%"

    where_sql = " AND ".join(where_clauses)

    # 统计总数
    count_result = await db.execute(
        text(f"SELECT COUNT(*) AS cnt FROM users_info WHERE {where_sql}"),
        params,
    )
    total = count_result.scalar_one()

    # 查询分页数据
    query = text(
        f"""
        SELECT id, name, email, device_token, created_at
        FROM users_info
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
    items = [AdminUserOut.model_validate(dict(row)) for row in rows]

    return Page[AdminUserOut](
        items=items,
        meta=PageMeta(total=total, page=page, page_size=page_size),
    )


@router.get(
    "/{user_id}",
    response_model=AdminUserOut,
    dependencies=[Depends(require_admin)],
)
async def get_user_detail(
    user_id: str,
    db: AsyncSession = Depends(get_db),
) -> AdminUserOut:
    result = await db.execute(
        text(
            """
            SELECT id, name, email, device_token, created_at
            FROM users_info
            WHERE id = :id
            """
        ),
        {"id": user_id},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )
    return AdminUserOut.model_validate(dict(row))


@router.patch(
    "/{user_id}",
    response_model=AdminUserOut,
    dependencies=[Depends(require_admin)],
)
async def update_user(
    user_id: str,
    payload: AdminUserUpdate,
    db: AsyncSession = Depends(get_db),
) -> AdminUserOut:
    if payload.name is None and payload.device_token is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="没有任何可更新字段",
        )

    sets: list[str] = []
    params: dict[str, Any] = {"id": user_id}

    if payload.name is not None:
        sets.append("name = :name")
        params["name"] = payload.name
    if payload.device_token is not None:
        sets.append("device_token = :device_token")
        params["device_token"] = payload.device_token

    set_sql = ", ".join(sets)

    result = await db.execute(
        text(
            f"""
            UPDATE users_info
            SET {set_sql}
            WHERE id = :id
            RETURNING id, name, email, device_token, created_at
            """
        ),
        params,
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )

    await db.commit()
    return AdminUserOut.model_validate(dict(row))


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
async def delete_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        text("DELETE FROM users_info WHERE id = :id"),
        {"id": user_id},
    )
    if result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )
    await db.commit()

