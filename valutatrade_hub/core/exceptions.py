"""Domain errors for wallets, currencies, and exchange-rate providers"""

from valutatrade_hub.core.utils import format_amount


class InsufficientFundsError(ValueError):
    """Report the available and required balances for a withdrawal"""

    def __init__(self, available: float, required: float, code: str) -> None:
        self.available = available
        self.required = required
        self.code = code

        available_text = format_amount(available, code)
        required_text = format_amount(required, code)

        super().__init__(
            f"Недостаточно средств: доступно {available_text} {code}, "
            f"требуется {required_text} {code}"
        )


class CurrencyNotFoundError(ValueError):
    """Report a currency code that is absent from the registry"""

    def __init__(self, code: str) -> None:
        self.code = code

        super().__init__(f"Неизвестная валюта '{code}'")


class ApiRequestError(Exception):
    """Report a failure to obtain usable data from an exchange-rate provider"""

    def __init__(self, reason: str) -> None:
        self.reason = reason

        super().__init__(f"Ошибка при обращении к внешнему API: {reason}")
