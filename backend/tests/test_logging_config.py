from __future__ import annotations

from pathlib import Path
import logging
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.logging_config import ACCESS_LOG_FORMAT, CSTFormatter, LOG_FORMAT


def _record(message: str = "hello") -> logging.LogRecord:
    record = logging.LogRecord(
        name="app.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )
    record.created = 1778138400.0  # 2026-05-07T07:20:00Z
    return record


def test_cst_formatter_formats_time_in_asia_shanghai() -> None:
    formatter = CSTFormatter(LOG_FORMAT)
    record = _record()

    assert formatter.formatTime(record) == "2026-05-07 15:20:00 +08"


def test_cst_formatter_formats_app_log_line() -> None:
    formatter = CSTFormatter(LOG_FORMAT)
    record = _record("service started")

    assert formatter.format(record) == "2026-05-07 15:20:00 +08 [INFO] service started"


def test_cst_formatter_formats_uvicorn_access_log_line() -> None:
    formatter = CSTFormatter(ACCESS_LOG_FORMAT)
    record = _record()
    record.client_addr = "127.0.0.1:5173"
    record.request_line = "GET /db/ping HTTP/1.1"
    record.status_code = 200

    assert (
        formatter.format(record)
        == '2026-05-07 15:20:00 +08 [INFO] 127.0.0.1:5173 - "GET /db/ping HTTP/1.1" 200'
    )
