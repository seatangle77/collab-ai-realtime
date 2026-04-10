from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


BACKEND_DIR = Path(__file__).resolve().parents[1]
SECRETS_FILE = str(BACKEND_DIR.parent / "secrets.env")

# 提前加载密钥文件，使 os.getenv() 全局可见（auth.py 等直接读环境变量的地方）
load_dotenv(SECRETS_FILE, override=False)


_ENV_FILES = (
    SECRETS_FILE,                          # 统一密钥（不进git）
    str(BACKEND_DIR / ".env.production"),  # 生产配置（可进git）
    "/etc/collab-ai-realtime.env",         # 线上覆盖（不进git）
    str(BACKEND_DIR / ".env.local"),       # 本地配置（可进git）
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DB_",
        env_file=_ENV_FILES,
        extra="ignore",
    )

    host: str = "127.0.0.1"
    port: int = 5432
    name: str = "collaborative_ai_chatbot"
    user: str = "app_user"
    password: str = Field(default="")

    def sqlalchemy_database_url(self) -> URL:
        if not self.password:
            raise RuntimeError("DB_PASSWORD 未设置")
        return URL.create(
            drivername="postgresql+asyncpg",
            username=self.user,
            password=self.password,
            host=self.host,
            port=self.port,
            database=self.name,
        )


settings = Settings()


class TencentASRSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TENCENT_",
        env_file=_ENV_FILES,
        extra="ignore",
    )

    appid: str = ""
    secret_id: str = ""
    secret_key: str = ""
    asr_engine: str = "16k_zh"
    vad_silence_time_ms: int = 400
    local_split_gap_ms: int = 400


tencent_asr_settings = TencentASRSettings()


class NLPSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NLP_",
        env_file=_ENV_FILES,
        extra="ignore",
    )

    embed_model: str = "paraphrase-multilingual-MiniLM-L12-v2"
    reasoning_model: str = "qwen-plus"
    qwen_api_key: str = Field(default="")
    qwen_base_url: str = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"


nlp_settings = NLPSettings()


class JPushSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="JPUSH_",
        env_file=_ENV_FILES,
        extra="ignore",
    )

    app_key: str = ""
    master_secret: str = Field(default="")


jpush_settings = JPushSettings()
