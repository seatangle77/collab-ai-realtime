import datetime
import logging
import sys
import zoneinfo
from typing import Optional


SHANGHAI_TZ = zoneinfo.ZoneInfo("Asia/Shanghai")
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
ACCESS_LOG_FORMAT = '%(asctime)s [%(levelname)s] %(client_addr)s - "%(request_line)s" %(status_code)s'


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


def _set_handlers(logger: logging.Logger, handler: logging.Handler, level: int) -> None:
    logger.handlers = [handler]
    logger.setLevel(level)


def configure_logging(level: int = logging.INFO) -> None:
    app_handler = _make_handler(CSTFormatter(LOG_FORMAT))
    access_handler = _make_handler(CSTFormatter(ACCESS_LOG_FORMAT))

    _set_handlers(logging.getLogger(), app_handler, level)

    for logger_name in ("uvicorn", "uvicorn.error"):
        logger = logging.getLogger(logger_name)
        _set_handlers(logger, app_handler, level)
        logger.propagate = False

    access_logger = logging.getLogger("uvicorn.access")
    _set_handlers(access_logger, access_handler, level)
    access_logger.propagate = False
