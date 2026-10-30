"""JSON storage helpers and a shared manager for application data"""

import json
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile

from valutatrade_hub.core.exceptions import CurrencyNotFoundError
from valutatrade_hub.core.models import Portfolio, User, Wallet
from valutatrade_hub.infra.settings import SettingsLoader


def load(file_path: Path, *, default: list | dict) -> object:
    """Read JSON, using the default only when the file is absent"""
    try:
        with file_path.open(encoding="utf-8") as source:
            return json.load(source)
    except FileNotFoundError:
        return default
    except json.JSONDecodeError as error:
        raise ValueError(f"Некорректный JSON в файле '{file_path}'") from error


def load_records(file_path: Path) -> list[dict]:
    """Read JSON records, treating a missing file as an empty collection"""
    records = load(file_path, default=[])

    if not isinstance(records, list) or any(
        not isinstance(record, dict) for record in records
    ):
        raise ValueError(f"Файл '{file_path}' должен содержать список объектов")

    return records


def save(file_path: Path, data: list | dict) -> None:
    """Write JSON data through a temporary file to avoid partial writes"""
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
            json.dump(data, target, ensure_ascii=False, indent=2, allow_nan=False)
            target.write("\n")

        temporary_path.replace(file_path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _serialize_portfolio(portfolio: Portfolio) -> dict:
    """Convert a portfolio to its stored representation"""
    return {
        "user_id": portfolio.user_id,
        "wallets": {
            code: {"balance": wallet.balance}
            for code, wallet in portfolio.wallets.items()
        },
    }


class DatabaseManager:
    """Hide storage paths and serialization from application use cases"""

    _instance = None

    # Use __new__ to keep singleton creation simple without a separate metaclass
    def __new__(cls):
        if cls._instance is None:
            settings = SettingsLoader()
            instance = super().__new__(cls)
            instance._users_file = Path(settings.get("USERS_FILE"))
            instance._portfolios_file = Path(settings.get("PORTFOLIOS_FILE"))
            instance._rates_file = Path(settings.get("RATES_FILE"))
            cls._instance = instance

        return cls._instance

    def _restore_user(self, record: dict) -> User:
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
                f"Некорректные данные пользователя в файле '{self._users_file}'"
            ) from error

    def get_users(self) -> list[User]:
        """Load all registered users"""
        records = load_records(self._users_file)

        return [self._restore_user(record) for record in records]

    def get_user(self, username: str) -> User | None:
        """Find a user by username, returning None when absent"""
        return next(
            (user for user in self.get_users() if user.username == username), None
        )

    def create_user(self, user: User, portfolio: Portfolio) -> None:
        """Save a new user and portfolio, rolling back the user on storage failure"""
        users = load_records(self._users_file)
        portfolios = load_records(self._portfolios_file)

        user_record = {
            "user_id": user.user_id,
            "username": user.username,
            "hashed_password": user.hashed_password,
            "salt": user.salt,
            "registration_date": user.registration_date.isoformat(),
        }
        portfolio_record = _serialize_portfolio(portfolio)

        save(self._users_file, users + [user_record])

        try:
            save(self._portfolios_file, portfolios + [portfolio_record])
        except (OSError, TypeError, ValueError):
            save(self._users_file, users)

            raise

    def get_portfolio(
        self, user_id: int, *, user: User | None = None
    ) -> Portfolio | None:
        """Restore a portfolio by owner ID without loading the user"""
        records = load_records(self._portfolios_file)
        record = next(
            (record for record in records if record.get("user_id") == user_id),
            None,
        )

        if record is None:
            return None

        try:
            stored_wallets = record["wallets"]

            if not isinstance(stored_wallets, dict):
                raise TypeError("Кошельки должны быть переданы словарем")

            wallets = {
                code: Wallet(currency_code=code, balance=wallet["balance"])
                for code, wallet in stored_wallets.items()
            }

            return Portfolio(user_id=record["user_id"], wallets=wallets, user=user)
        except CurrencyNotFoundError:
            # Preserve CurrencyNotFoundError before handling other ValueError exceptions
            raise
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(
                f"Некорректные данные портфеля в файле '{self._portfolios_file}'"
            ) from error

    def save_portfolio(self, portfolio: Portfolio) -> None:
        """Save all wallets together while preserving the other users' portfolios"""
        records = load_records(self._portfolios_file)

        for record in records:
            if record.get("user_id") == portfolio.user_id:
                record["wallets"] = _serialize_portfolio(portfolio)["wallets"]
                save(self._portfolios_file, records)

                return

        raise ValueError(f"Портфель пользователя с ID {portfolio.user_id} не найден")

    def get_rates(self) -> dict:
        """Load the exchange-rate cache, returning an empty mapping when absent"""
        cache = load(self._rates_file, default={})

        if not isinstance(cache, dict):
            raise ValueError(
                f"Файл '{self._rates_file}' должен содержать объект с курсами"
            )

        return cache
