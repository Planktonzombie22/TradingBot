import logging
import json
from logging.handlers import RotatingFileHandler
from logging.config import dictConfig
from typing import Optional


DEFAULT_LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s %(levelname)s [%(name)s] %(message)s",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
            "level": "INFO",
        }
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "timestamp": self.formatTime(record, self.datefmt),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging(
    config: Optional[dict] = None,
    json_logs: bool = False,
    log_file: Optional[str] = None,
    max_bytes: int = 1_000_000,
    backup_count: int = 3,
) -> None:
    """Configure application logging once at process startup."""

    if config is not None:
        dictConfig(config)
        return

    dictConfig(DEFAULT_LOGGING)
    root = logging.getLogger()
    formatter: logging.Formatter = JsonFormatter() if json_logs else logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    )
    for handler in root.handlers:
        handler.setFormatter(formatter)
    if log_file:
        file_handler = RotatingFileHandler(log_file, maxBytes=max_bytes, backupCount=backup_count)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
