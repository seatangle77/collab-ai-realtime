import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .db import DBNotConfiguredError, ping_db
from .routes import router as db_router
from .auth import router as auth_router
from .groups import router as groups_router
from .sessions import router as sessions_router
from .admin.users import router as admin_users_router
from .admin.groups import router as admin_groups_router
from .admin.memberships import router as admin_memberships_router
from .admin.chat_sessions import router as admin_chat_sessions_router

app = FastAPI()

# CORS 配置：开发环境显式允许本地前端，避免通配符与凭证冲突
frontend_origin = os.getenv("FRONTEND_ORIGIN")
allow_origins = (
    [frontend_origin]
    if frontend_origin
    else [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(db_router)
app.include_router(auth_router)
app.include_router(groups_router)
app.include_router(sessions_router)
app.include_router(admin_users_router)
app.include_router(admin_groups_router)
app.include_router(admin_memberships_router)
app.include_router(admin_chat_sessions_router)


@app.exception_handler(DBNotConfiguredError)
async def _db_not_configured(_request, exc: DBNotConfiguredError):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.get("/")
def root():
    return {"status": "backend running"}


@app.on_event("startup")
async def _startup():
    # 避免未配置 DB_PASSWORD 时无法启动服务；需要验证连通性请访问 /db/ping
    if os.getenv("DB_PASSWORD"):
        await ping_db()