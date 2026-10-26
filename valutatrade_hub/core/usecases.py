"""Application operations for managing users and currency portfolios"""

from datetime import datetime
from pathlib import Path

from valutatrade_hub.core.models import Portfolio, User, Wallet
from valutatrade_hub.core.utils import (
    EXCHANGE_RATES,
    SUPPORTED_CURRENCIES,
    load_records,
    save_records,
    validate_currency_code,
)

USERS_FILE = Path("data/users.json")
PORTFOLIOS_FILE = Path("data/portfolios.json")


def _restore_user(record: dict) -> User:
    """Restore a user without generating a new salt or password hash"""
    try:
        return User(
            user_id=record["user_id"],
            username=record["username"],
            hashed_password=record["hashed_password"],
            salt=record["salt"],
            registration_date=datetime.fromisoformat(record["registration_date"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(
            f"Некорректные данные пользователя в файле '{USERS_FILE}'"
        ) from error


def register(username: str, password: str) -> User:
    """Create a user and persist an empty portfolio without starting a session"""
    records = load_records(USERS_FILE)
    users = [_restore_user(record) for record in records]

    if any(user.username == username for user in users):
        raise ValueError(f"Имя пользователя '{username}' уже занято")

    user_id = max((user.user_id for user in users), default=0) + 1
    user = User.create(user_id, username, password)

    portfolios = load_records(PORTFOLIOS_FILE)

    user_record = {
        "user_id": user.user_id,
        "username": user.username,
        "hashed_password": user.hashed_password,
        "salt": user.salt,
        "registration_date": user.registration_date.isoformat(),
    }
    portfolio_record = {"user_id": user.user_id, "wallets": {}}

    save_records(USERS_FILE, records + [user_record])

    try:
        save_records(PORTFOLIOS_FILE, portfolios + [portfolio_record])
    except (OSError, TypeError, ValueError):
        save_records(USERS_FILE, records)

        raise

    return user


def login(username: str, password: str) -> User:
    """Authenticate an existing user for the caller's current session"""
    users = [_restore_user(record) for record in load_records(USERS_FILE)]
    user = next((user for user in users if user.username == username), None)

    if user is None:
        raise ValueError(f"Пользователь '{username}' не найден")

    if not user.verify_password(password):
        raise ValueError("Неверный пароль")

    return user


def _load_portfolio(user_id: int, *, user: User | None = None) -> Portfolio:
    """Load a portfolio by owner ID, retaining the supplied user when available"""
    records = load_records(PORTFOLIOS_FILE)
    record = next(
        (record for record in records if record.get("user_id") == user_id), None
    )

    if record is None:
        raise ValueError(f"Портфель пользователя с ID {user_id} не найден")

    try:
        stored_wallets = record["wallets"]

        if not isinstance(stored_wallets, dict):
            raise TypeError("Кошельки должны быть переданы словарем")

        wallets = {
            code: Wallet(currency_code=code, balance=wallet["balance"])
            for code, wallet in stored_wallets.items()
        }

        return Portfolio(user_id=record["user_id"], wallets=wallets, user=user)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(
            f"Некорректные данные портфеля в файле '{PORTFOLIOS_FILE}'"
        ) from error


def show_portfolio(user: User | None, base_currency: str = "USD") -> dict:
    """Load a portfolio and prepare its values for display in the base currency"""
    if user is None:
        raise ValueError("Сначала выполните login")

    base = validate_currency_code(base_currency)

    if base not in SUPPORTED_CURRENCIES:
        raise ValueError(f"Неизвестная базовая валюта '{base}'")

    portfolio = _load_portfolio(user.user_id, user=user)
    total_value = portfolio.get_total_value(base_currency=base, rates=EXCHANGE_RATES)
    base_rate = 1.0 if base == "USD" else EXCHANGE_RATES[base]
    rows = []

    for code, wallet in portfolio.wallets.items():
        value = 0.0

        if wallet.balance > 0:
            usd_rate = 1.0 if code == "USD" else EXCHANGE_RATES[code]
            value = wallet.balance * (usd_rate / base_rate)

        rows.append((code, wallet.balance, value))

    return {
        "username": user.username,
        "base_currency": base,
        "wallets": rows,
        "total_value": total_value,
    }
