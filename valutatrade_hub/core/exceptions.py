"""Domain errors raised by wallet operations"""


class InsufficientFundsError(ValueError):
    """Report the available and required balances for a withdrawal"""

    def __init__(self, available: float, required: float, code: str) -> None:
        self.available = available
        self.required = required
        self.code = code

        super().__init__(
            f"Недостаточно средств: доступно {available} {code}, "
            f"требуется {required} {code}"
        )
