from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """
    约定：
    - 非敏感默认值进 git（host/port/name/user）
    - 密码只从环境变量/服务器环境文件注入（不进 git）
    - 线上更规范：/etc/collab-ai-realtime.env
    """

    model_config = SettingsConfigDict(
        env_prefix="DB_",
        env_file=(
            str(BACKEND_DIR / ".env.local"),  # 本地开发（不进git）
            str(BACKEND_DIR / ".env.production"),  # 服务器项目目录可选（不进git）
            "/etc/collab-ai-realtime.env",  # 线上更规范（不进git）
        ),
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
        env_file=(
            str(BACKEND_DIR / ".env.local"),
            str(BACKEND_DIR / ".env.production"),
            "/etc/collab-ai-realtime.env",
        ),
        extra="ignore",
    )

    appid: str = ""
    secret_id: str = ""
    secret_key: str = ""
    asr_engine: str = "16k_zh"


tencent_asr_settings = TencentASRSettings()


class NLPSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NLP_",
        env_file=(
            str(BACKEND_DIR / ".env.local"),
            str(BACKEND_DIR / ".env.production"),
            "/etc/collab-ai-realtime.env",
        ),
        extra="ignore",
    )

    # sentence-transformers 模型名，可通过环境变量 NLP_EMBED_MODEL 覆盖
    embed_model: str = "paraphrase-multilingual-MiniLM-L12-v2"

    # 论证判定 LLM：Qwen，模型名可通过环境变量 NLP_REASONING_MODEL 覆盖
    # 香港区域使用国际端点，稳定性更好
    reasoning_model: str = "qwen-plus"
    qwen_api_key: str = Field(default="")
    qwen_base_url: str = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"


nlp_settings = NLPSettings()


class JPushSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="JPUSH_",
        env_file=(
            str(BACKEND_DIR / ".env.local"),
            str(BACKEND_DIR / ".env.production"),
            "/etc/collab-ai-realtime.env",
        ),
        extra="ignore",
    )

    app_key: str = ""
    master_secret: str = Field(default="")


jpush_settings = JPushSettings()
