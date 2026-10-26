"""Validation, JSON storage, and fixed example exchange rates"""

import json
import math
from pathlib import Path
from tempfile import NamedTemporaryFile

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


def load_records(file_path: Path) -> list[dict]:
    """Read JSON records, treating a missing file as an empty collection"""
    try:
        with file_path.open(encoding="utf-8") as source:
            records = json.load(source)
    except FileNotFoundError:
        return []
    except json.JSONDecodeError as error:
        raise ValueError(f"Некорректный JSON в файле '{file_path}'") from error

    if not isinstance(records, list) or any(
        not isinstance(record, dict) for record in records
    ):
        raise ValueError(f"Файл '{file_path}' должен содержать список объектов")

    return records


def save_records(file_path: Path, records: list[dict]) -> None:
    """Write JSON records through a temporary file to avoid partial writes"""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None

    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=file_path.parent,
            prefix=f".{file_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as target:
            temporary_path = Path(target.name)
            json.dump(records, target, ensure_ascii=False, indent=2, allow_nan=False)
            target.write("\n")

        temporary_path.replace(file_path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
