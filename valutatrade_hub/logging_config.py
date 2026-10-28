"""Configure rotating trade logs"""

import logging
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from valutatrade_hub.infra.settings import SettingsLoader

ACTION_LOGGER_NAME = "valutatrade_hub.actions"
LOG_DATE_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def setup_logging() -> logging.Logger:
    """Configure the action logger once, with UTC timestamps and size rotation"""
    logger = logging.getLogger(ACTION_LOGGER_NAME)

    if logger.handlers:
        return logger

    settings = SettingsLoader()
    max_bytes = settings.get("LOG_MAX_BYTES")
    backup_count = settings.get("LOG_BACKUP_COUNT")

    for key, value in (
        ("LOG_MAX_BYTES", max_bytes),
        ("LOG_BACKUP_COUNT", backup_count),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"{key} должен быть положительным целым числом")

    logger.setLevel(settings.get("LOG_LEVEL"))

    formatter = logging.Formatter(
        fmt=settings.get("LOG_FORMAT"), datefmt=LOG_DATE_FORMAT
    )
    formatter.converter = time.gmtime

    log_path = Path(settings.get("LOG_FILE"))
    log_path.parent.mkdir(parents=True, exist_ok=True)

    handler = RotatingFileHandler(
        filename=log_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.setFormatter(formatter)

    logger.addHandler(handler)
    logger.propagate = False

    return logger
