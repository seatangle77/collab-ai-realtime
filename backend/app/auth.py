from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=True)

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-me")  # 建议线上用环境变量覆盖
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 小时


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


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


def _hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def _verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


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
            SELECT id, name, email, device_token, created_at
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
    # 检查 email 是否已存在
    existing = await db.execute(
        text("SELECT id FROM users_info WHERE email = :email"),
        {"email": payload.email},
    )
    if existing.first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="邮箱已被注册")

    # 插入新用户
    result = await db.execute(
        text(
            """
            INSERT INTO users_info (name, email, device_token, password_hash, created_at)
            VALUES (:name, :email, :device_token, :password_hash, NOW())
            RETURNING id, name, email, device_token, created_at
            """
        ),
        {
            "name": payload.name,
            "email": payload.email,
            "device_token": payload.device_token,
            "password_hash": _hash_password(payload.password),
        },
    )
    await db.commit()
    row = result.mappings().one()
    return UserOut.model_validate(dict(row))


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    result = await db.execute(
        text(
            """
            SELECT id, name, email, device_token, created_at, password_hash
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
    }
    access_token = _create_access_token({"sub": row["id"]})
    return TokenResponse(access_token=access_token, user=UserOut.model_validate(user_data))


@router.get("/me", response_model=UserOut)
async def me(current_user: Mapping[str, Any] = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(dict(current_user))

