from __future__ import annotations

from typing import Any
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..groups import MAX_GROUP_MEMBERS
from .deps import require_admin
from .schemas import BatchDeleteRequest, BatchDeleteResponse, Page, PageMeta


router = APIRouter(prefix="/api/admin/memberships", tags=["admin-memberships"])


def _to_utc_naive(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)

class AdminMembershipOut(BaseModel):
    id: str
    group_id: str
    user_id: str
    role: str
    status: str
    created_at: datetime
    group_name: str | None = None
    user_name: str | None = None


class AdminMembershipUpdate(BaseModel):
    role: str | None = None
    status: str | None = None


class AdminMembershipCreate(BaseModel):
    group_id: str
    user_id: str
    role: str = "member"
    status: str = "active"


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
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    db: AsyncSession = Depends(get_db),
) -> Page[AdminMembershipOut]:
    offset = (page - 1) * page_size

    where_clauses = ["1=1"]
    params: dict[str, Any] = {}

    if group_id:
        where_clauses.append("gm.group_id = :group_id")
        params["group_id"] = group_id
    if user_id:
        where_clauses.append("gm.user_id = :user_id")
        params["user_id"] = user_id
    if status_filter:
        where_clauses.append("gm.status = :status")
        params["status"] = status_filter
    if created_from:
        where_clauses.append("gm.created_at >= :created_from")
        params["created_from"] = _to_utc_naive(created_from)
    if created_to:
        where_clauses.append("gm.created_at <= :created_to")
        params["created_to"] = _to_utc_naive(created_to)

    where_sql = " AND ".join(where_clauses)

    count_result = await db.execute(
        text(f"SELECT COUNT(*) AS cnt FROM group_memberships gm WHERE {where_sql}"),
        params,
    )
    total = count_result.scalar_one()

    query = text(
        f"""
        SELECT
          gm.id,
          gm.group_id,
          gm.user_id,
          gm.role,
          gm.status,
          gm.created_at,
          g.name AS group_name,
          u.name AS user_name
        FROM group_memberships gm
        JOIN groups g ON g.id = gm.group_id
        JOIN users_info u ON u.id = gm.user_id
        WHERE {where_sql}
        ORDER BY gm.created_at DESC
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


@router.post(
    "/",
    response_model=AdminMembershipOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def create_membership(
    payload: AdminMembershipCreate,
    db: AsyncSession = Depends(get_db),
) -> AdminMembershipOut:
    # 基础字段校验（role/status 合法性）
    if payload.role not in {"leader", "member"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无效的成员角色",
        )
    if payload.status not in {"active", "left", "kicked"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无效的成员状态",
        )

    # 校验群组存在且处于可用状态
    group_result = await db.execute(
        text("SELECT id, is_active FROM groups WHERE id = :id"),
        {"id": payload.group_id},
    )
    group_row = group_result.mappings().first()
    if not group_row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="群组不存在",
        )
    if group_row["is_active"] is False:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="群组已关闭，不允许添加成员",
        )

    # 校验用户存在（使用 users_info 表，保持与业务侧 join 一致）
    user_result = await db.execute(
        text("SELECT id FROM users_info WHERE id = :id"),
        {"id": payload.user_id},
    )
    user_row = user_result.mappings().first()
    if not user_row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )

    # 查询是否已有成员关系
    membership_result = await db.execute(
        text(
            """
            SELECT id, role, status
            FROM group_memberships
            WHERE group_id = :group_id AND user_id = :user_id
            """
        ),
        {"group_id": payload.group_id, "user_id": payload.user_id},
    )
    existing = membership_result.mappings().first()

    # 若目标状态为 active，需要校验群成员上限
    if payload.status == "active":
        count_result = await db.execute(
            text(
                """
                SELECT COUNT(*) AS c
                FROM group_memberships
                WHERE group_id = :group_id AND status = 'active'
                """
            ),
            {"group_id": payload.group_id},
        )
        active_count = count_result.scalar_one()
        # 如果已有 active 记录，后面会单独处理；这里只限制新增/恢复为 active 的情况
        if (not existing or existing["status"] != "active") and active_count >= MAX_GROUP_MEMBERS:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="群组人数已满",
            )

    # 创建或复用成员关系
    if existing:
        # 已经是 active 且仍要设为 active，认为是重复添加
        if existing["status"] == "active" and payload.status == "active":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="该用户已在群组中",
            )

        # 如果要将成员设为 leader，需要保证唯一性
        if payload.role == "leader":
            leader_check = await db.execute(
                text(
                    """
                    SELECT id
                    FROM group_memberships
                    WHERE group_id = :group_id
                      AND role = 'leader'
                      AND status = 'active'
                      AND id != :current_id
                    """
                ),
                {"group_id": payload.group_id, "current_id": existing["id"]},
            )
            leader_existing = leader_check.mappings().first()
            if leader_existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="该群已存在群主，不能再添加 leader",
                )

        # 复用已有记录，更新 role/status
        result = await db.execute(
            text(
                """
                UPDATE group_memberships
                SET role = :role,
                    status = :status
                WHERE id = :id
                RETURNING id, group_id, user_id, role, status, created_at
                """
            ),
            {
                "id": existing["id"],
                "role": payload.role,
                "status": payload.status,
            },
        )
        row = result.mappings().first()
        await db.commit()
        return AdminMembershipOut.model_validate(dict(row))

    # 全新成员关系：若角色为 leader，需要校验群内 leader 唯一性
    if payload.role == "leader":
        leader_check = await db.execute(
            text(
                """
                SELECT id
                FROM group_memberships
                WHERE group_id = :group_id
                  AND role = 'leader'
                  AND status = 'active'
                """
            ),
            {"group_id": payload.group_id},
        )
        leader_existing = leader_check.mappings().first()
        if leader_existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="该群已存在群主，不能再添加 leader",
            )

    membership_id = f"m{uuid.uuid4().hex[:8]}"
    result = await db.execute(
        text(
            """
            INSERT INTO group_memberships (id, group_id, user_id, role, status, created_at)
            VALUES (:id, :group_id, :user_id, :role, :status, NOW())
            RETURNING id, group_id, user_id, role, status, created_at
            """
        ),
        {
            "id": membership_id,
            "group_id": payload.group_id,
            "user_id": payload.user_id,
            "role": payload.role,
            "status": payload.status,
        },
    )
    row = result.mappings().first()
    await db.commit()
    return AdminMembershipOut.model_validate(dict(row))


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


@router.post(
    "/batch-delete",
    response_model=BatchDeleteResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_admin)],
)
async def batch_delete_memberships(
    body: BatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
) -> BatchDeleteResponse:
    deleted = 0
    for mid in body.ids:
        result = await db.execute(
            text("DELETE FROM group_memberships WHERE id = :id"),
            {"id": mid},
        )
        deleted += result.rowcount
    await db.commit()
    return BatchDeleteResponse(deleted=deleted)

