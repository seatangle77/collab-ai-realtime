from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from .db import DBNotConfiguredError, get_db
from .settings import settings

router = APIRouter(prefix="/db", tags=["db"])


@router.get("/ping")
async def db_ping(db: AsyncSession = Depends(get_db)):
    try:
        r = await db.execute(text("SELECT 1 AS ok"))
        return {"ok": r.mappings().one()["ok"]}
    except DBNotConfiguredError as e:
        raise HTTPException(
            status_code=503,
            detail={
                "error": str(e),
                "hint": "请配置 DB_PASSWORD（本地用 backend/.env.local，线上用 /etc/collab-ai-realtime.env）",
            },
        ) from e
    except SQLAlchemyError as e:
        orig = getattr(e, "orig", None)
        # 这里通常是：隧道没通 / 端口没转发 / 密码不对 / 库名不存在 / pg_hba 拒绝等
        raise HTTPException(
            status_code=502,
            detail={
                "error": "数据库连接/查询失败",
                "error_class": e.__class__.__name__,
                "driver_error": str(orig) if orig else None,
                "db": {
                    "host": settings.host,
                    "port": settings.port,
                    "name": settings.name,
                    "user": settings.user,
                },
                "hint": "优先检查 SSH 隧道是否成功绑定本地端口，以及本机 5432 是否被占用（必要时改用本地 15432 并设置 DB_PORT=15432）",
            },
        ) from e
