"""Configuration for exchange-rate API clients and parser storage"""

import os
from dataclasses import dataclass, field
from pathlib import Path

from valutatrade_hub.core.utils import validate_currency_code, validate_number
from valutatrade_hub.infra.settings import SettingsLoader


@dataclass
class ParserConfig:
    """Keep parser options together and read API keys when creating a config"""

    EXCHANGERATE_API_KEY: str | None = field(
        default_factory=lambda: os.getenv("EXCHANGERATE_API_KEY"), repr=False
    )
    COINGECKO_API_KEY: str | None = field(
        default_factory=lambda: os.getenv("COINGECKO_API_KEY"), repr=False
    )

    COINGECKO_URL: str = "https://api.coingecko.com/api/v3/simple/price"
    EXCHANGERATE_API_URL: str = "https://v6.exchangerate-api.com/v6"

    BASE_CURRENCY: str = "USD"
    FIAT_CURRENCIES: tuple[str, ...] = ("EUR", "RUB")
    CRYPTO_CURRENCIES: tuple[str, ...] = ("BTC", "ETH")
    CRYPTO_ID_MAP: dict[str, str] = field(
        default_factory=lambda: {"BTC": "bitcoin", "ETH": "ethereum"}
    )

    REQUEST_TIMEOUT: float = 10.0

    RATES_FILE_PATH: Path = field(
        default_factory=lambda: Path(SettingsLoader().get("RATES_FILE"))
    )
    HISTORY_FILE_PATH: Path = field(
        default_factory=lambda: Path(SettingsLoader().get("HISTORY_FILE"))
    )

    def __post_init__(self) -> None:
        """Normalize currency codes and reject invalid request timeouts"""
        self.BASE_CURRENCY = validate_currency_code(self.BASE_CURRENCY)
        self.FIAT_CURRENCIES = tuple(
            validate_currency_code(code) for code in self.FIAT_CURRENCIES
        )
        self.CRYPTO_CURRENCIES = tuple(
            validate_currency_code(code) for code in self.CRYPTO_CURRENCIES
        )

        self.REQUEST_TIMEOUT = validate_number(self.REQUEST_TIMEOUT)

        if self.REQUEST_TIMEOUT <= 0:
            raise ValueError("REQUEST_TIMEOUT должен быть положительным числом")
