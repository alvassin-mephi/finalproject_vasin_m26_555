"""Cached settings from the working directory's pyproject.toml, with defaults"""

import tomllib
from pathlib import Path
from typing import Any

DEFAULT_SETTINGS = {
    "USERS_FILE": "data/users.json",
    "PORTFOLIOS_FILE": "data/portfolios.json",
    "RATES_FILE": "data/rates.json",
    "INITIAL_USD_BALANCE": 10_000.0,
    "RATES_TTL_SECONDS": 300,
    "DEFAULT_BASE_CURRENCY": "USD",
    "LOG_FILE": "logs/actions.log",
    "LOG_FORMAT": "%(levelname)s %(asctime)s %(message)s",
    "LOG_LEVEL": "INFO",
    "LOG_MAX_BYTES": 1_048_576,
    "LOG_BACKUP_COUNT": 3,
}


class SettingsLoader:
    """Load [tool.valutatrade] once and share its values across the application"""

    _instance = None

    # Use __new__ to keep singleton creation simple without a separate metaclass
    def __new__(cls):
        if cls._instance is None:
            instance = super().__new__(cls)
            instance._settings = instance._load()
            cls._instance = instance

        return cls._instance

    def _load(self) -> dict:
        """Read configuration from the working directory, filling missing defaults"""
        config_path = Path("pyproject.toml")

        try:
            with config_path.open("rb") as source:
                config = tomllib.load(source)
        except FileNotFoundError:
            return DEFAULT_SETTINGS.copy()
        except tomllib.TOMLDecodeError as error:
            raise ValueError(f"Некорректный TOML в файле '{config_path}'") from error

        tool_config = config.get("tool", {})

        if not isinstance(tool_config, dict):
            raise ValueError("Секция [tool] должна быть таблицей TOML")

        settings = tool_config.get("valutatrade", {})

        if not isinstance(settings, dict):
            raise ValueError("Секция [tool.valutatrade] должна быть таблицей TOML")

        return DEFAULT_SETTINGS | settings

    def get(self, key: str, default: Any = None) -> Any:
        """Return a configured value, or default if the key is unknown"""
        return self._settings.get(key, default)
