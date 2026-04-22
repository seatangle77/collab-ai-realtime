import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from .config_voice import VOICE_AUDIO_BASE_DIR
from .db import DBNotConfiguredError, get_sessionmaker, ping_db
from .routes import router as db_router
from .auth import router as auth_router
from .groups import router as groups_router
from .sessions import router as sessions_router
from .voice_profiles import router as voice_profiles_router
from .admin.users import router as admin_users_router
from .admin.groups import router as admin_groups_router
from .admin.memberships import router as admin_memberships_router
from .admin.chat_sessions import router as admin_chat_sessions_router
from .admin.voice_profiles import router as admin_voice_profiles_router
from .admin.transcripts import router as admin_transcripts_router
from .admin.discussion_states import router as admin_discussion_states_router
from .admin.discussion_rules import router as admin_discussion_rules_router
from .push_logs import router as push_logs_router
from .admin.push_logs import router as admin_push_logs_router
from .ws_sessions import router as ws_sessions_router
from .nlp.router import router as nlp_router
from .nlp import embedder as nlp_embedder
from .nlp.segmenter import get_pipeline as get_nlp_pipeline
from .settings import nlp_settings
from .info_gap import router as info_gap_router
from .discussion_summary import router as discussion_summary_router
from .window_metrics_api import router as window_metrics_router
from .admin.push_queue import router as admin_push_queue_router
from .admin.window_metrics import router as admin_window_metrics_router
from .admin.discussion_summaries import router as admin_discussion_summaries_router
from .admin.info_gap_buttons import router as admin_info_gap_buttons_router
from .admin.info_gap_skw import router as admin_info_gap_skw_router
from .admin.window_metrics_keywords import router as admin_window_metrics_keywords_router
from .admin.speech_transcripts import router as admin_speech_transcripts_router
from .admin.test_seed import router as test_seed_router
from .vad import router as vad_router
from .admin.ai_push_analysis import router as admin_ai_push_analysis_router
from .admin.info_gap_recall_analysis import router as admin_info_gap_recall_analysis_router

app = FastAPI()

# CORS 配置：开发环境显式允许本地前端，避免通配符与凭证冲突
frontend_origin = os.getenv("FRONTEND_ORIGIN")
# Capacitor Android App 的 WebView origin 固定为 https://localhost / capacitor://localhost
_capacitor_origins = ["https://localhost", "capacitor://localhost"]
allow_origins = (
    [frontend_origin] + _capacitor_origins
    if frontend_origin
    else [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ] + _capacitor_origins
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
app.include_router(voice_profiles_router)
app.include_router(admin_users_router)
app.include_router(admin_groups_router)
app.include_router(admin_memberships_router)
app.include_router(admin_chat_sessions_router)
app.include_router(admin_voice_profiles_router)
app.include_router(admin_transcripts_router)
app.include_router(admin_discussion_states_router)
app.include_router(admin_discussion_rules_router)
app.include_router(push_logs_router)
app.include_router(admin_push_logs_router)
app.include_router(admin_push_queue_router)
app.include_router(admin_window_metrics_router)
app.include_router(admin_discussion_summaries_router)
app.include_router(admin_info_gap_buttons_router)
app.include_router(admin_info_gap_skw_router)
app.include_router(admin_window_metrics_keywords_router)
app.include_router(admin_speech_transcripts_router)
app.include_router(admin_ai_push_analysis_router)
app.include_router(admin_info_gap_recall_analysis_router)
app.include_router(ws_sessions_router)
app.include_router(nlp_router)
app.include_router(info_gap_router)
app.include_router(discussion_summary_router)
app.include_router(window_metrics_router)
app.include_router(test_seed_router)
app.include_router(vad_router)

# 本地开发环境下直接通过 FastAPI 提供音频静态访问能力，
# 与生产环境中通过 Nginx 映射 /audio/voice-profiles 到挂载目录的行为保持一致。
app.mount(
    "/audio/voice-profiles",
    StaticFiles(directory=str(VOICE_AUDIO_BASE_DIR), check_dir=False),
    name="voice-audio",
)


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

    # 进程重启后，内存态 WS 连接会清空；把历史残留计数统一归零，避免 agent 误判活跃会话。
    session_factory = get_sessionmaker()
    async with session_factory() as db:
        await db.execute(
            text(
                """
                UPDATE chat_sessions
                SET active_ws_count = 0
                WHERE status = 'ongoing'
                """
            )
        )
        await db.commit()

    # 预加载 NLP sentence-transformers 模型，避免第一个请求冷启动延迟
    nlp_embedder.load_model(nlp_settings.embed_model)
    # 预加载 HanLP MTL 模型，避免第一个 NLP 请求冷启动
    get_nlp_pipeline()
