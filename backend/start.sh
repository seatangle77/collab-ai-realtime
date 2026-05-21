#!/bin/bash
# 后端生产启动脚本，由 systemd 调用
set -e

export TZ=Asia/Shanghai
export APP_ENV=production

cd /var/www/collab-ai-realtime/backend
source /var/www/collab-ai-realtime/venv/bin/activate

exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 1
