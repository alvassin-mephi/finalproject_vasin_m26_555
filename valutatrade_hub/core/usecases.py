"""Application operations for managing users and currency portfolios"""

from datetime import datetime
from pathlib import Path

from valutatrade_hub.core.models import User
from valutatrade_hub.core.utils import load_records, save_records

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
