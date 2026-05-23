#!/bin/bash
# Agent 生产启动脚本，由 systemd 调用
set -euo pipefail

ROOT_DIR="/root/workspace/collab-ai-realtime"
LOG_DIR="$ROOT_DIR/logs"
LOG_FILE="$LOG_DIR/agent-$(date +%Y%m%d-%H%M%S).log"

mkdir -p "$LOG_DIR"

cd "$ROOT_DIR/agent"

if ! command -v node >/dev/null 2>&1; then
  echo "node not found, aborting agent startup"
  exit 127
fi

echo "Agent log: $LOG_FILE"
node dist/index.js 2>&1 | tee "$LOG_FILE"
