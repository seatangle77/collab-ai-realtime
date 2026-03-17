from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])

security = HTTPBearer(auto_error=True)

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-me")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 小时

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    device_token: str | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: str
    name: str
    email: str
    device_token: str | None = None
    created_at: datetime
    password_needs_reset: bool = False


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


def _hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def _create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> Mapping[str, Any]:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise JWTError("Missing subject")
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证令牌",
        )

    result = await db.execute(
        text(
            """
            SELECT id, name, email, device_token, created_at, password_needs_reset
            FROM users_info
            WHERE id = :user_id
            """
        ),
        {"user_id": user_id},
    )
    user = result.mappings().first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已被删除")
    return user


@router.post("/register", response_model=UserOut)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)) -> UserOut:
    # 邮箱格式校验
    if not _EMAIL_RE.match(payload.email):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="邮箱格式不正确")

    # 密码长度校验：恰好 4 位
    if len(payload.password) != 4:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="密码必须为 4 位")

    # 邮箱唯一性
    existing = await db.execute(
        text("SELECT id FROM users_info WHERE email = :email"),
        {"email": payload.email},
    )
    if existing.first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="邮箱已被注册")

    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    user_id = f"u{uuid.uuid4().hex[:8]}"
    group_id = f"g{uuid.uuid4().hex[:8]}"
    membership_id = f"gm{uuid.uuid4().hex[:8]}"

    # 写入用户
    result = await db.execute(
        text(
            """
            INSERT INTO users_info (id, name, email, device_token, password_hash, created_at)
            VALUES (:id, :name, :email, :device_token, :password_hash, :created_at)
            RETURNING id, name, email, device_token, created_at, password_needs_reset
            """
        ),
        {
            "id": user_id,
            "name": payload.name,
            "email": payload.email,
            "device_token": payload.device_token,
            "password_hash": _hash_password(payload.password),
            "created_at": now_utc,
        },
    )
    row = result.mappings().one()

    # 创建默认群组
    await db.execute(
        text(
            """
            INSERT INTO groups (id, name, is_active, is_default, created_at)
            VALUES (:id, :name, TRUE, TRUE, :created_at)
            """
        ),
        {
            "id": group_id,
            "name": f"{payload.name} 的群组",
            "created_at": now_utc,
        },
    )

    # 创建 owner 成员关系
    await db.execute(
        text(
            """
            INSERT INTO group_memberships (id, group_id, user_id, role, status, created_at)
            VALUES (:id, :group_id, :user_id, 'owner', 'active', :created_at)
            """
        ),
        {
            "id": membership_id,
            "group_id": group_id,
            "user_id": user_id,
            "created_at": now_utc,
        },
    )

    await db.commit()
    return UserOut.model_validate(dict(row))


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    result = await db.execute(
        text(
            """
            SELECT id, name, email, device_token, created_at, password_hash, password_needs_reset
            FROM users_info
            WHERE email = :email
            """
        ),
        {"email": payload.email},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="邮箱或密码错误")

    if not _verify_password(payload.password, row["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="邮箱或密码错误")

    user_data = {
        "id": row["id"],
        "name": row["name"],
        "email": row["email"],
        "device_token": row["device_token"],
        "created_at": row["created_at"],
        "password_needs_reset": row.get("password_needs_reset", False),
    }
    access_token = _create_access_token({"sub": row["id"]})
    return TokenResponse(access_token=access_token, user=UserOut.model_validate(user_data))


@router.get("/me", response_model=UserOut)
async def me(current_user: Mapping[str, Any] = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(dict(current_user))


@router.post("/change-password", response_model=UserOut)
async def change_password(
    payload: ChangePasswordRequest,
    current_user: Mapping[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    user_id = current_user["id"]

    result = await db.execute(
        text("SELECT password_hash FROM users_info WHERE id = :id"),
        {"id": user_id},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    if not _verify_password(payload.old_password, row["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="旧密码不正确")

    if len(payload.new_password) != 4:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="密码必须为 4 位")

    await db.execute(
        text(
            """
            UPDATE users_info
            SET password_hash = :password_hash,
                password_needs_reset = FALSE
            WHERE id = :id
            """
        ),
        {
            "id": user_id,
            "password_hash": _hash_password(payload.new_password),
        },
    )
    await db.commit()

    result2 = await db.execute(
        text(
            """
            SELECT id, name, email, device_token, created_at, password_needs_reset
            FROM users_info
            WHERE id = :id
            """
        ),
        {"id": user_id},
    )
    row2 = result2.mappings().one()
    return UserOut.model_validate(dict(row2))
