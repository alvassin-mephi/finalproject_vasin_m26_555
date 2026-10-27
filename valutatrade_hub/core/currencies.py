"""Currency types and the registry used to resolve supported codes"""

from abc import ABC, abstractmethod

from valutatrade_hub.core.exceptions import CurrencyNotFoundError
from valutatrade_hub.core.utils import validate_currency_code, validate_number


def _validate_text(value: str, field: str) -> str:
    """Return trimmed text, rejecting empty and non-string values"""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Поле '{field}' должно быть непустой строкой")

    return value.strip()


class Currency(ABC):
    """Define validated currency metadata and a common display interface"""

    def __init__(self, name: str, code: str) -> None:
        self.name = _validate_text(name, "name")
        self.code = validate_currency_code(code)

    @abstractmethod
    def get_display_info(self) -> str:
        """Return currency details for display and logging"""


class FiatCurrency(Currency):
    """Describe a fiat currency and its issuing country or monetary area"""

    def __init__(self, name: str, code: str, issuing_country: str) -> None:
        super().__init__(name=name, code=code)

        self.issuing_country = _validate_text(issuing_country, "issuing_country")

    def get_display_info(self) -> str:
        """Include the issuing country in the currency description"""
        return f"[FIAT] {self.code} — {self.name} (Issuing: {self.issuing_country})"


class CryptoCurrency(Currency):
    """Describe crypto metadata, using zero for unavailable market capitalization"""

    def __init__(
        self, name: str, code: str, algorithm: str, market_cap: float = 0.0
    ) -> None:
        super().__init__(name=name, code=code)

        self.algorithm = _validate_text(algorithm, "algorithm")
        self.market_cap = validate_number(market_cap)

        if self.market_cap < 0:
            raise ValueError("Капитализация не может быть отрицательной")

    def get_display_info(self) -> str:
        """Include the algorithm and a compact market capitalization"""
        market_cap = "n/a"

        if self.market_cap > 0:
            mantissa, exponent = f"{self.market_cap:.2e}".split("e")
            market_cap = f"{mantissa}e{int(exponent)}"

        return (
            f"[CRYPTO] {self.code} — {self.name} "
            f"(Algo: {self.algorithm}, MCAP: {market_cap})"
        )


# Metadata follows the assignment examples; market capitalization is not loaded yet
CURRENCIES: dict[str, Currency] = {
    "USD": FiatCurrency(name="US Dollar", code="USD", issuing_country="United States"),
    "EUR": FiatCurrency(name="Euro", code="EUR", issuing_country="Eurozone"),
    "RUB": FiatCurrency(name="Russian Ruble", code="RUB", issuing_country="Russia"),
    "BTC": CryptoCurrency(name="Bitcoin", code="BTC", algorithm="SHA-256"),
    "ETH": CryptoCurrency(name="Ethereum", code="ETH", algorithm="Ethash"),
}


def get_currency(code: str) -> Currency:
    """Resolve a normalized currency code or raise CurrencyNotFoundError"""
    code = validate_currency_code(code)

    try:
        return CURRENCIES[code]
    except KeyError:
        raise CurrencyNotFoundError(code=code) from None
