from __future__ import annotations

import os
from pathlib import Path


# 本地文件系统中用于存放声纹相关音频文件的根目录。
# - 本地开发默认使用项目下的 ./local-voice-audio
# - 线上部署时建议通过环境变量 VOICE_AUDIO_BASE_DIR 配置为挂载的对象存储目录（如 /cos/voice-profiles）
VOICE_AUDIO_BASE_DIR: Path = Path(
    os.getenv("VOICE_AUDIO_BASE_DIR", "./local-voice-audio")
).resolve()


# 对外访问音频文件的基础 URL 前缀。
# - 本地开发默认假设通过 /audio/voice-profiles 映射到 VOICE_AUDIO_BASE_DIR
# - 线上部署时可设置为实际域名，例如 https://example.com/audio/voice-profiles
VOICE_AUDIO_PUBLIC_BASE_URL: str = os.getenv(
    "VOICE_AUDIO_PUBLIC_BASE_URL",
    "http://127.0.0.1:8000/audio/voice-profiles",
).rstrip("/")

