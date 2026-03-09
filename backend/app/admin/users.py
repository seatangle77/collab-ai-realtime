from __future__ import annotations

from typing import Any
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from .deps import require_admin
from .schemas import BatchDeleteRequest, BatchDeleteResponse, Page, PageMeta


router = APIRouter(prefix="/api/admin/users", tags=["admin-users"])


def _to_utc_naive(dt: datetime) -> datetime:
    """
    将带时区的 datetime 统一转换为 UTC naive，
    避免 asyncpg 在处理 offset-naive / offset-aware 混用时抛错。
    """
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


class AdminUserOut(BaseModel):
    id: str
    name: str
    email: str
    device_token: str | None = None
    created_at: datetime
    group_ids: list[str] = []
    group_names: list[str] = []


class AdminUserUpdate(BaseModel):
    name: str | None = None
    device_token: str | None = None


@router.get("/", response_model=Page[AdminUserOut], dependencies=[Depends(require_admin)])
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    email: str | None = None,
    name: str | None = None,
    user_id: str | None = Query(None, alias="id"),
    device_token: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    group_name: str | None = None,
    group_id: str | None = None,
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
    if user_id:
        where_clauses.append("id = :id")
        params["id"] = user_id
    if device_token:
        where_clauses.append("device_token ILIKE :device_token")
        params["device_token"] = f"%{device_token}%"
    if created_from:
        where_clauses.append("created_at >= :created_from")
        params["created_from"] = _to_utc_naive(created_from)
    if created_to:
        where_clauses.append("created_at <= :created_to")
        params["created_to"] = _to_utc_naive(created_to)
    if group_name:
        where_clauses.append(
            """
            EXISTS (
              SELECT 1
              FROM group_memberships gm
              JOIN groups g ON g.id = gm.group_id
              WHERE gm.user_id = users_info.id
                AND gm.status = 'active'
                AND g.name ILIKE :group_name
            )
            """
        )
        params["group_name"] = f"%{group_name}%"
    if group_id:
        where_clauses.append(
            """
            EXISTS (
              SELECT 1
              FROM group_memberships gm
              WHERE gm.user_id = users_info.id
                AND gm.status = 'active'
                AND gm.group_id = :group_id
            )
            """
        )
        params["group_id"] = group_id

    where_sql = " AND ".join(where_clauses)

    # 统计总数：只在 users_info 上计数，必要时通过 EXISTS 引用成员/群组表
    count_result = await db.execute(
        text(f"SELECT COUNT(*) AS cnt FROM users_info WHERE {where_sql}"),
        params,
    )
    total = count_result.scalar_one()

    # 第一步：只从 users_info 拉取当前页基础信息，保持与旧版接口的性能特征接近
    base_query = text(
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

    base_result = await db.execute(base_query, params_with_page)
    base_rows = base_result.mappings().all()

    # 没有任何用户时，直接返回
    if not base_rows:
        return Page[AdminUserOut](
            items=[],
            meta=PageMeta(total=total, page=page, page_size=page_size),
        )

    # 提取当前页用户 ID，用于后续批量查询成员关系
    user_ids = [row["id"] for row in base_rows]

    # 第二步：仅针对当前页用户，批量查出其 active 成员关系和对应群组
    memberships_query = text(
        """
        SELECT
          gm.user_id,
          array_agg(DISTINCT g.id) AS group_ids,
          array_agg(DISTINCT g.name) AS group_names
        FROM group_memberships gm
        JOIN groups g ON g.id = gm.group_id
        WHERE gm.user_id = ANY(:user_ids)
          AND gm.status = 'active'
        GROUP BY gm.user_id
        """
    )
    memberships_result = await db.execute(
        memberships_query,
        {"user_ids": user_ids},
    )
    memberships_rows = memberships_result.mappings().all()

    # 聚合为 user_id -> {group_ids, group_names} 的映射，方便合并
    memberships_map: dict[str, dict[str, list[str]]] = {}
    for row in memberships_rows:
        uid = row["user_id"]
        memberships_map[uid] = {
            "group_ids": list(row["group_ids"] or []),
            "group_names": list(row["group_names"] or []),
        }

    # 组装最终返回的 AdminUserOut 列表
    items: list[AdminUserOut] = []
    for row in base_rows:
        uid = row["id"]
        extra = memberships_map.get(uid, {"group_ids": [], "group_names": []})
        payload: dict[str, Any] = {
            "id": row["id"],
            "name": row["name"],
            "email": row["email"],
            "device_token": row["device_token"],
            "created_at": row["created_at"],
            "group_ids": extra["group_ids"],
            "group_names": extra["group_names"],
        }
        items.append(AdminUserOut.model_validate(payload))

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


@router.post(
    "/batch-delete",
    response_model=BatchDeleteResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_admin)],
)
async def batch_delete_users(
    body: BatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
) -> BatchDeleteResponse:
    deleted = 0
    for uid in body.ids:
        result = await db.execute(
            text("DELETE FROM users_info WHERE id = :id"),
            {"id": uid},
        )
        deleted += result.rowcount
    await db.commit()
    return BatchDeleteResponse(deleted=deleted)

