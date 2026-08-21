from __future__ import annotations

import datetime
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


logger = logging.getLogger(__name__)

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_LOG_DIR = REPO_ROOT / "logs" / "data-analysis" / "coi-ai-coding"
DEFAULT_RETENTION_DAYS = 14
DEFAULT_MAX_FIELD_CHARS = 200_000
DEFAULT_ROTATION_HOURS = 4

_write_lock = threading.Lock()
_last_cleanup_key: tuple[str, datetime.date] | None = None


def _enabled() -> bool:
    return os.getenv("COI_AI_AUDIT_LOG_ENABLED", "true").strip().lower() not in {
        "0", "false", "no", "off",
    }


def _log_dir() -> Path:
    configured = os.getenv("COI_AI_AUDIT_LOG_DIR", "").strip()
    return Path(configured) if configured else DEFAULT_LOG_DIR


def _positive_int_env(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


def _limit_value(value: Any, max_chars: int) -> Any:
    if isinstance(value, str):
        if len(value) <= max_chars:
            return value
        return value[:max_chars] + f"…[truncated {len(value) - max_chars} chars]"
    if isinstance(value, dict):
        return {str(key): _limit_value(item, max_chars) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_limit_value(item, max_chars) for item in value]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


def _log_file_path(log_dir: Path, now: datetime.datetime) -> Path:
    rotation_hours = min(
        _positive_int_env("COI_AI_AUDIT_ROTATION_HOURS", DEFAULT_ROTATION_HOURS),
        24,
    )
    bucket_hour = now.hour - now.hour % rotation_hours
    return log_dir / f"coi-ai-coding-{now:%Y%m%d}-{bucket_hour:02d}.jsonl"


def _cleanup_expired_files(log_dir: Path, now: datetime.datetime) -> None:
    global _last_cleanup_key

    cleanup_key = (str(log_dir.resolve()), now.date())
    if _last_cleanup_key == cleanup_key:
        return

    retention_days = _positive_int_env(
        "COI_AI_AUDIT_RETENTION_DAYS", DEFAULT_RETENTION_DAYS,
    )
    cutoff = now.timestamp() - retention_days * 24 * 60 * 60
    for path in log_dir.glob("coi-ai-coding-*.jsonl"):
        try:
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError as exc:
            logger.warning("[CoI/AI-AUDIT] 清理旧日志失败 path=%s error=%s", path, exc)
    _last_cleanup_key = cleanup_key


def write_coi_ai_audit(record: dict[str, Any]) -> bool:
    """Append one structured audit event without affecting the coding request."""
    if not _enabled():
        return False

    now = datetime.datetime.now(tz=SHANGHAI_TZ)
    log_dir = _log_dir()
    max_chars = _positive_int_env(
        "COI_AI_AUDIT_MAX_FIELD_CHARS", DEFAULT_MAX_FIELD_CHARS,
    )
    payload = {
        "timestamp": now.isoformat(timespec="milliseconds"),
        **_limit_value(record, max_chars),
    }
    line = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"

    try:
        with _write_lock:
            log_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            try:
                log_dir.chmod(0o700)
            except OSError:
                pass
            _cleanup_expired_files(log_dir, now)
            log_file = _log_file_path(log_dir, now)
            file_descriptor = os.open(
                log_file,
                os.O_APPEND | os.O_CREAT | os.O_WRONLY,
                0o600,
            )
            with os.fdopen(file_descriptor, "a", encoding="utf-8") as stream:
                stream.write(line)
            try:
                log_file.chmod(0o600)
            except OSError:
                pass
        return True
    except Exception as exc:
        logger.warning("[CoI/AI-AUDIT] 写入审计日志失败: %s", exc)
        return False
