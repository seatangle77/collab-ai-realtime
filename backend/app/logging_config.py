import datetime
import logging
import os
from pathlib import Path
import re
import sys
import threading
import zoneinfo
from typing import Iterable, Optional


SHANGHAI_TZ = zoneinfo.ZoneInfo("Asia/Shanghai")
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
ACCESS_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
REPO_ROOT = Path(__file__).resolve().parents[2]
SESSION_LOG_DIR = Path(os.getenv("SESSION_LOG_DIR", REPO_ROOT / "logs" / "sessions"))
SESSION_ID_PATTERN = re.compile(r"\bsession(?:_id|Id)?=([A-Za-z0-9_.:-]+)")


def _session_log_timestamp() -> str:
    return datetime.datetime.now(tz=SHANGHAI_TZ).strftime("%Y%m%d-%H%M%S")


class CSTFormatter(logging.Formatter):
    def formatTime(self, record: logging.LogRecord, datefmt: Optional[str] = None) -> str:
        dt = datetime.datetime.fromtimestamp(record.created, tz=SHANGHAI_TZ)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.strftime("%Y-%m-%d %H:%M:%S +08")


def _make_handler(formatter: logging.Formatter) -> logging.StreamHandler:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    return handler


def _safe_session_id(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return re.sub(r"[^A-Za-z0-9_.:-]", "_", value.strip())


class SessionFileHandler(logging.Handler):
    """Copy records with a session_id into a per-run file under logs/sessions/<session_id>/."""

    def __init__(self, base_dir: Path, filename: str) -> None:
        super().__init__()
        self.base_dir = base_dir
        self.filename = filename
        self._lock = threading.Lock()

    def _extract_session_id(self, record: logging.LogRecord) -> str | None:
        explicit = getattr(record, "session_id", None) or getattr(record, "sessionId", None)
        safe = _safe_session_id(explicit)
        if safe:
            return safe

        match = SESSION_ID_PATTERN.search(record.getMessage())
        if match:
            return _safe_session_id(match.group(1))
        return None

    def emit(self, record: logging.LogRecord) -> None:
        try:
            session_id = self._extract_session_id(record)
            if not session_id:
                return
            line = self.format(record)
            session_dir = self.base_dir / session_id
            with self._lock:
                session_dir.mkdir(parents=True, exist_ok=True)
                with (session_dir / self.filename).open("a", encoding="utf-8") as file:
                    file.write(line + "\n")
        except Exception:
            self.handleError(record)


def _set_handlers(logger: logging.Logger, handlers: Iterable[logging.Handler], level: int) -> None:
    logger.handlers = list(handlers)
    logger.setLevel(level)


def configure_logging(level: int = logging.INFO) -> None:
    app_handler = _make_handler(CSTFormatter(LOG_FORMAT))
    access_handler = _make_handler(CSTFormatter(ACCESS_LOG_FORMAT))
    session_log_filename = f"backend-{_session_log_timestamp()}.log"
    session_app_handler = SessionFileHandler(SESSION_LOG_DIR, session_log_filename)
    session_app_handler.setFormatter(CSTFormatter(LOG_FORMAT))
    session_access_handler = SessionFileHandler(SESSION_LOG_DIR, session_log_filename)
    session_access_handler.setFormatter(CSTFormatter(ACCESS_LOG_FORMAT))

    _set_handlers(logging.getLogger(), [app_handler, session_app_handler], level)

    for logger_name in ("uvicorn", "uvicorn.error"):
        logger = logging.getLogger(logger_name)
        _set_handlers(logger, [app_handler, session_app_handler], level)
        logger.propagate = False

    access_logger = logging.getLogger("uvicorn.access")
    _set_handlers(access_logger, [access_handler, session_access_handler], level)
    access_logger.propagate = False
