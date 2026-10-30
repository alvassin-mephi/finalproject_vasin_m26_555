"""Configure rotating trade and parser logs"""

import logging
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from valutatrade_hub.infra.settings import SettingsLoader

ACTION_LOGGER_NAME = "valutatrade_hub.actions"
PARSER_LOGGER_NAME = "valutatrade_hub.parser"
LOG_DATE_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def setup_logging() -> logging.Logger:
    """Configure the action logger once, with UTC timestamps and size rotation"""
    return _setup_file_logger(ACTION_LOGGER_NAME, "LOG_FILE")


def setup_parser_logging() -> logging.Logger:
    """Configure a separate rotating file for parser updates and source errors"""
    return _setup_file_logger(
        PARSER_LOGGER_NAME, "PARSER_LOG_FILE", level=logging.DEBUG
    )


def _setup_file_logger(
    name: str, file_setting: str, *, level: int | None = None
) -> logging.Logger:
    """Share file configuration without mixing parser and trading messages"""
    logger = logging.getLogger(name)

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

    log_level = settings.get("LOG_LEVEL") if level is None else level
    logger.setLevel(log_level)

    formatter = logging.Formatter(
        fmt=settings.get("LOG_FORMAT"), datefmt=LOG_DATE_FORMAT
    )
    formatter.converter = time.gmtime

    log_path = Path(settings.get(file_setting))
    log_path.parent.mkdir(parents=True, exist_ok=True)

    handler = RotatingFileHandler(
        filename=log_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.setLevel(log_level)
    handler.setFormatter(formatter)

    logger.addHandler(handler)
    logger.propagate = False

    return logger
