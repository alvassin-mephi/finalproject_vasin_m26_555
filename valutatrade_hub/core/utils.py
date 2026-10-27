"""Validation and fixed example exchange rates"""

import math

# Example USD prices per currency unit from the assignment, not live rates
EXCHANGE_RATES = {
    "USD": 1.0,
    "EUR": 1.0786,
    "RUB": 0.01016,
    "BTC": 59337.21,
    "ETH": 3720.0,
}


def validate_currency_code(currency_code: str) -> str:
    """Return an uppercase currency code containing two to five ASCII letters"""
    if not isinstance(currency_code, str):
        raise TypeError("Код валюты должен быть строкой")

    code = currency_code.strip()

    if not (2 <= len(code) <= 5 and code.isascii() and code.isalpha()):
        raise ValueError("Код валюты должен содержать от 2 до 5 латинских букв")

    return code.upper()


def validate_number(value: float) -> float:
    """Return a finite float, rejecting booleans and nonnumeric values"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("Значение должно быть числом")

    try:
        number = float(value)
    except OverflowError as error:
        raise ValueError("Значение должно быть конечным числом") from error

    if not math.isfinite(number):
        raise ValueError("Значение должно быть конечным числом")

    return number


def validate_amount(amount: float) -> float:
    """Return a finite, strictly positive transaction amount"""
    amount = validate_number(amount)

    if amount <= 0:
        raise ValueError("'amount' должен быть положительным числом")

    return amount
