#!/bin/bash
# 后端生产启动脚本，由 systemd 调用
set -e

export TZ=Asia/Shanghai
export APP_ENV=production

ROOT_DIR="/root/workspace/collab-ai-realtime"
LOG_DIR="$ROOT_DIR/logs"
LOG_FILE="$LOG_DIR/backend-$(date +%Y%m%d-%H%M%S).log"

mkdir -p "$LOG_DIR"

cd "$ROOT_DIR/backend"
source "$ROOT_DIR/backend/venv/bin/activate"

echo "Backend log: $LOG_FILE"
uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 1 \
    2>&1 | tee "$LOG_FILE"
