from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import _hash_password
from ..db import get_db
from .deps import require_admin
from .schemas import BatchDeleteRequest, BatchDeleteResponse, Page, PageMeta


router = APIRouter(prefix="/api/admin/users", tags=["admin-users"])


def _to_utc_naive(dt: datetime) -> datetime:
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
    password_needs_reset: bool = False


class AdminUserCreate(BaseModel):
    name: str
    email: str
    password: str
    device_token: str | None = None


class AdminUserUpdate(BaseModel):
    name: str | None = None
    device_token: str | None = None


def _build_where(
    email: str | None,
    name: str | None,
    user_id: str | None,
    device_token: str | None,
    created_from: datetime | None,
    created_to: datetime | None,
    group_name: str | None,
    group_id: str | None,
) -> tuple[str, dict[str, Any]]:
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

    return " AND ".join(where_clauses), params


async def _fetch_group_info(db: AsyncSession, user_ids: list[str]) -> dict[str, dict[str, list[str]]]:
    """批量查询给定用户 ID 列表的 active 群组信息。"""
    if not user_ids:
        return {}
    result = await db.execute(
        text(
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
        ),
        {"user_ids": user_ids},
    )
    mapping: dict[str, dict[str, list[str]]] = {}
    for row in result.mappings().all():
        mapping[row["user_id"]] = {
            "group_ids": list(row["group_ids"] or []),
            "group_names": list(row["group_names"] or []),
        }
    return mapping


def _build_admin_user_out(row: Any, group_info: dict[str, dict[str, list[str]]]) -> AdminUserOut:
    uid = row["id"]
    extra = group_info.get(uid, {"group_ids": [], "group_names": []})
    return AdminUserOut.model_validate(
        {
            "id": row["id"],
            "name": row["name"],
            "email": row["email"],
            "device_token": row["device_token"],
            "created_at": row["created_at"],
            "group_ids": extra["group_ids"],
            "group_names": extra["group_names"],
            "password_needs_reset": row.get("password_needs_reset", False),
        }
    )


# ---- 导出 CSV（必须在 /{user_id} 之前注册）----

@router.get("/export", dependencies=[Depends(require_admin)])
async def export_users_csv(
    email: str | None = None,
    name: str | None = None,
    user_id: str | None = Query(None, alias="id"),
    device_token: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    group_name: str | None = None,
    group_id: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    where_sql, params = _build_where(
        email, name, user_id, device_token, created_from, created_to, group_name, group_id
    )

    base_result = await db.execute(
        text(
            f"""
            SELECT id, name, email, device_token, created_at, password_needs_reset
            FROM users_info
            WHERE {where_sql}
            ORDER BY created_at DESC
            """
        ),
        params,
    )
    rows = base_result.mappings().all()

    all_ids = [r["id"] for r in rows]
    group_info = await _fetch_group_info(db, all_ids)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "name", "email", "device_token", "group_ids", "group_names", "password_needs_reset", "created_at"])
    for row in rows:
        extra = group_info.get(row["id"], {"group_ids": [], "group_names": []})
        writer.writerow([
            row["id"],
            row["name"],
            row["email"],
            row["device_token"] or "",
            "|".join(extra["group_ids"]),
            "|".join(extra["group_names"]),
            row.get("password_needs_reset", False),
            row["created_at"].isoformat() if row["created_at"] else "",
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=users_export.csv"},
    )


# ---- 创建用户（必须在 /{user_id} 之前注册）----

@router.post("/", response_model=AdminUserOut, dependencies=[Depends(require_admin)])
async def create_user(
    payload: AdminUserCreate,
    db: AsyncSession = Depends(get_db),
) -> AdminUserOut:
    if len(payload.password) != 4:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="密码必须为 4 位")

    existing = await db.execute(
        text("SELECT id FROM users_info WHERE email = :email"),
        {"email": payload.email},
    )
    if existing.first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="邮箱已被注册")

    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    new_user_id = f"u{uuid.uuid4().hex[:8]}"
    group_id = f"g{uuid.uuid4().hex[:8]}"
    membership_id = f"gm{uuid.uuid4().hex[:8]}"

    await db.execute(
        text(
            """
            INSERT INTO users_info (id, name, email, device_token, password_hash, created_at)
            VALUES (:id, :name, :email, :device_token, :password_hash, :created_at)
            """
        ),
        {
            "id": new_user_id,
            "name": payload.name,
            "email": payload.email,
            "device_token": payload.device_token,
            "password_hash": _hash_password(payload.password),
            "created_at": now_utc,
        },
    )

    await db.execute(
        text(
            """
            INSERT INTO groups (id, name, is_active, is_default, created_at)
            VALUES (:id, :name, TRUE, TRUE, :created_at)
            """
        ),
        {"id": group_id, "name": f"{payload.name} 的群组", "created_at": now_utc},
    )

    await db.execute(
        text(
            """
            INSERT INTO group_memberships (id, group_id, user_id, role, status, created_at)
            VALUES (:id, :group_id, :user_id, 'owner', 'active', :created_at)
            """
        ),
        {"id": membership_id, "group_id": group_id, "user_id": new_user_id, "created_at": now_utc},
    )

    await db.commit()

    group_info = await _fetch_group_info(db, [new_user_id])
    result = await db.execute(
        text(
            """
            SELECT id, name, email, device_token, created_at, password_needs_reset
            FROM users_info WHERE id = :id
            """
        ),
        {"id": new_user_id},
    )
    row = result.mappings().one()
    return _build_admin_user_out(row, group_info)


# ---- 列表 ----

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
    where_sql, params = _build_where(
        email, name, user_id, device_token, created_from, created_to, group_name, group_id
    )
    offset = (page - 1) * page_size

    count_result = await db.execute(
        text(f"SELECT COUNT(*) AS cnt FROM users_info WHERE {where_sql}"),
        params,
    )
    total = count_result.scalar_one()

    params_page = dict(params)
    params_page["limit"] = page_size
    params_page["offset"] = offset

    base_result = await db.execute(
        text(
            f"""
            SELECT id, name, email, device_token, created_at, password_needs_reset
            FROM users_info
            WHERE {where_sql}
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        params_page,
    )
    base_rows = base_result.mappings().all()

    if not base_rows:
        return Page[AdminUserOut](items=[], meta=PageMeta(total=total, page=page, page_size=page_size))

    user_ids = [row["id"] for row in base_rows]
    group_info = await _fetch_group_info(db, user_ids)

    items = [_build_admin_user_out(row, group_info) for row in base_rows]
    return Page[AdminUserOut](items=items, meta=PageMeta(total=total, page=page, page_size=page_size))


# ---- 单个用户详情 ----

@router.get("/{user_id}", response_model=AdminUserOut, dependencies=[Depends(require_admin)])
async def get_user_detail(
    user_id: str,
    db: AsyncSession = Depends(get_db),
) -> AdminUserOut:
    result = await db.execute(
        text(
            """
            SELECT id, name, email, device_token, created_at, password_needs_reset
            FROM users_info
            WHERE id = :id
            """
        ),
        {"id": user_id},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    group_info = await _fetch_group_info(db, [user_id])
    return _build_admin_user_out(row, group_info)


# ---- 更新 ----

@router.patch("/{user_id}", response_model=AdminUserOut, dependencies=[Depends(require_admin)])
async def update_user(
    user_id: str,
    payload: AdminUserUpdate,
    db: AsyncSession = Depends(get_db),
) -> AdminUserOut:
    if payload.name is None and payload.device_token is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="没有任何可更新字段")

    sets: list[str] = []
    params: dict[str, Any] = {"id": user_id}

    if payload.name is not None:
        sets.append("name = :name")
        params["name"] = payload.name
    if payload.device_token is not None:
        sets.append("device_token = :device_token")
        params["device_token"] = payload.device_token

    result = await db.execute(
        text(
            f"""
            UPDATE users_info
            SET {", ".join(sets)}
            WHERE id = :id
            RETURNING id, name, email, device_token, created_at, password_needs_reset
            """
        ),
        params,
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    await db.commit()
    group_info = await _fetch_group_info(db, [user_id])
    return _build_admin_user_out(row, group_info)


# ---- 删除 ----

@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_admin)])
async def delete_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    # 先级联删除成员关系
    await db.execute(
        text("DELETE FROM group_memberships WHERE user_id = :id"),
        {"id": user_id},
    )
    result = await db.execute(
        text("DELETE FROM users_info WHERE id = :id"),
        {"id": user_id},
    )
    if result.rowcount == 0:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    await db.commit()


# ---- 批量删除 ----

@router.post("/batch-delete", response_model=BatchDeleteResponse, dependencies=[Depends(require_admin)])
async def batch_delete_users(
    body: BatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
) -> BatchDeleteResponse:
    # 批量删除成员关系
    await db.execute(
        text("DELETE FROM group_memberships WHERE user_id = ANY(:ids)"),
        {"ids": body.ids},
    )
    # 批量删除用户
    result = await db.execute(
        text("DELETE FROM users_info WHERE id = ANY(:ids)"),
        {"ids": body.ids},
    )
    await db.commit()
    return BatchDeleteResponse(deleted=result.rowcount)


# ---- 标记强制重置密码 ----

@router.post("/{user_id}/mark-password-reset", response_model=AdminUserOut, dependencies=[Depends(require_admin)])
async def mark_password_reset(
    user_id: str,
    db: AsyncSession = Depends(get_db),
) -> AdminUserOut:
    result = await db.execute(
        text(
            """
            UPDATE users_info
            SET password_needs_reset = TRUE
            WHERE id = :id
            RETURNING id, name, email, device_token, created_at, password_needs_reset
            """
        ),
        {"id": user_id},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    await db.commit()
    group_info = await _fetch_group_info(db, [user_id])
    return _build_admin_user_out(row, group_info)


# ---- 代登录 ----

@router.post("/{user_id}/impersonate", dependencies=[Depends(require_admin)])
async def impersonate_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    result = await db.execute(
        text("SELECT id FROM users_info WHERE id = :id"),
        {"id": user_id},
    )
    if not result.mappings().first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    from ..auth import _create_access_token

    access_token = _create_access_token({"sub": user_id, "impersonated_by": "admin"})
    return {"access_token": access_token, "token_type": "bearer"}
