from __future__ import annotations

from typing import Any, Mapping

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import get_current_user
from .db import get_db

router = APIRouter(prefix="/api/groups", tags=["groups"])

MAX_GROUP_MEMBERS = 3


class GroupCreate(BaseModel):
    name: str


class GroupSummary(BaseModel):
    id: str
    name: str
    created_at: Any
    is_active: bool
    member_count: int
    my_role: str


class GroupMember(BaseModel):
    user_id: str
    role: str
    status: str
    user_name: str | None = None
    device_token: str | None = None


class GroupDetail(BaseModel):
    group: dict[str, Any]
    member_count: int
    members: list[GroupMember]
    my_role: str | None = None


async def _get_group_or_404(group_id: str, db: AsyncSession) -> Mapping[str, Any]:
    result = await db.execute(
        text("SELECT * FROM groups WHERE id = :group_id AND is_active = TRUE"),
        {"group_id": group_id},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="群组不存在或已被关闭")
    return row


async def _get_group_detail(group_id: str, user_id: str, db: AsyncSession) -> GroupDetail:
    group_row = await _get_group_or_404(group_id, db)

    members_result = await db.execute(
        text(
            """
            SELECT
                gm.user_id,
                gm.role,
                gm.status,
                ui.name AS user_name,
                ui.device_token
            FROM group_memberships AS gm
            LEFT JOIN users_info AS ui ON ui.id = gm.user_id
            WHERE gm.group_id = :group_id AND gm.status = 'active'
            ORDER BY gm.created_at ASC
            """
        ),
        {"group_id": group_id},
    )
    members_rows = [GroupMember.model_validate(dict(row)) for row in members_result.mappings().all()]
    member_count = len(members_rows)
    my_role = next((m.role for m in members_rows if m.user_id == user_id), None)

    return GroupDetail(
        group=dict(group_row),
        member_count=member_count,
        members=members_rows,
        my_role=my_role,
    )


@router.post("", response_model=GroupDetail, status_code=status.HTTP_201_CREATED)
async def create_group(
    payload: GroupCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Mapping[str, Any] = Depends(get_current_user),
) -> GroupDetail:
    # 创建群组
    result = await db.execute(
        text(
            """
            INSERT INTO groups (name, created_at, is_active)
            VALUES (:name, NOW(), TRUE)
            RETURNING id
            """
        ),
        {"name": payload.name},
    )
    group_id = result.scalar_one()

    # 当前用户作为 leader 加入群组
    await db.execute(
        text(
            """
            INSERT INTO group_memberships (group_id, user_id, role, status, created_at)
            VALUES (:group_id, :user_id, 'leader', 'active', NOW())
            """
        ),
        {"group_id": group_id, "user_id": current_user["id"]},
    )
    await db.commit()

    return await _get_group_detail(group_id, current_user["id"], db)


@router.get("/my", response_model=list[GroupSummary])
async def list_my_groups(
    db: AsyncSession = Depends(get_db),
    current_user: Mapping[str, Any] = Depends(get_current_user),
) -> list[GroupSummary]:
    result = await db.execute(
        text(
            """
            SELECT
                g.id,
                g.name,
                g.created_at,
                g.is_active,
                gm.role AS my_role,
                COUNT(gm_all.user_id) AS member_count
            FROM group_memberships AS gm
            JOIN groups AS g
                ON g.id = gm.group_id
            LEFT JOIN group_memberships AS gm_all
                ON gm_all.group_id = g.id AND gm_all.status = 'active'
            WHERE gm.user_id = :user_id
              AND gm.status = 'active'
              AND g.is_active = TRUE
            GROUP BY g.id, g.name, g.created_at, g.is_active, gm.role
            ORDER BY g.created_at DESC
            """
        ),
        {"user_id": current_user["id"]},
    )
    rows = result.mappings().all()
    return [
        GroupSummary(
            id=row["id"],
            name=row["name"],
            created_at=row["created_at"],
            is_active=row["is_active"],
            member_count=row["member_count"],
            my_role=row["my_role"],
        )
        for row in rows
    ]


@router.get("/{group_id}", response_model=GroupDetail)
async def get_group(
    group_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Mapping[str, Any] = Depends(get_current_user),
) -> GroupDetail:
    return await _get_group_detail(group_id, current_user["id"], db)


@router.post("/{group_id}/join", response_model=GroupDetail)
async def join_group(
    group_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Mapping[str, Any] = Depends(get_current_user),
) -> GroupDetail:
    await _get_group_or_404(group_id, db)

    # 当前活跃成员数
    count_result = await db.execute(
        text(
            """
            SELECT COUNT(*) AS c
            FROM group_memberships
            WHERE group_id = :group_id AND status = 'active'
            """
        ),
        {"group_id": group_id},
    )
    member_count = count_result.scalar_one()
    if member_count >= MAX_GROUP_MEMBERS:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="群组人数已满")

    # 是否已有 membership
    membership_result = await db.execute(
        text(
            """
            SELECT id, status
            FROM group_memberships
            WHERE group_id = :group_id AND user_id = :user_id
            """
        ),
        {"group_id": group_id, "user_id": current_user["id"]},
    )
    membership = membership_result.mappings().first()

    if membership:
        if membership["status"] == "active":
            # 已经在群里，直接返回详情
            return await _get_group_detail(group_id, current_user["id"], db)

        # 从 left / inactive 变为 active
        await db.execute(
            text(
                """
                UPDATE group_memberships
                SET status = 'active'
                WHERE id = :id
                """
            ),
            {"id": membership["id"]},
        )
    else:
        # 新成员加入，角色默认为 member
        await db.execute(
            text(
                """
                INSERT INTO group_memberships (group_id, user_id, role, status, created_at)
                VALUES (:group_id, :user_id, 'member', 'active', NOW())
                """
            ),
            {"group_id": group_id, "user_id": current_user["id"]},
        )

    await db.commit()
    return await _get_group_detail(group_id, current_user["id"], db)


@router.post("/{group_id}/leave")
async def leave_group(
    group_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Mapping[str, Any] = Depends(get_current_user),
) -> dict[str, bool]:
    await _get_group_or_404(group_id, db)

    await db.execute(
        text(
            """
            UPDATE group_memberships
            SET status = 'left'
            WHERE group_id = :group_id AND user_id = :user_id AND status = 'active'
            """
        ),
        {"group_id": group_id, "user_id": current_user["id"]},
    )
    await db.commit()
    return {"success": True}

