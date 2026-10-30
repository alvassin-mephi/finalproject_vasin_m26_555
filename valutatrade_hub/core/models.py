"""Domain models and validation rules for the currency wallet"""

import hashlib
import hmac
import math
import secrets
import string
from datetime import UTC, datetime

from valutatrade_hub.core.currencies import get_currency
from valutatrade_hub.core.exceptions import InsufficientFundsError
from valutatrade_hub.core.utils import validate_amount, validate_number

MIN_PASSWORD_LENGTH = 4
SALT_BYTES = 16
SHA256_HEX_LENGTH = 64


class User:
    """Store user details and a salted password hash"""

    def __init__(
        self,
        user_id: int,
        username: str,
        hashed_password: str,
        salt: str,
        registration_date: datetime,
    ) -> None:
        if (
            isinstance(user_id, bool)
            or not isinstance(user_id, int)
            or user_id <= 0
        ):
            raise ValueError("ID пользователя должен быть положительным целым числом")

        if (
            not isinstance(hashed_password, str)
            or len(hashed_password) != SHA256_HEX_LENGTH
            or any(character not in string.hexdigits for character in hashed_password)
        ):
            raise ValueError("Некорректный SHA-256 хеш пароля")

        if not isinstance(salt, str) or not salt:
            raise ValueError("Соль должна быть непустой строкой")

        if not isinstance(registration_date, datetime):
            raise TypeError("Дата регистрации должна иметь тип datetime")

        self._user_id = user_id
        self.username = username
        self._hashed_password = hashed_password.lower()
        self._salt = salt
        self._registration_date = registration_date

    @classmethod
    def create(cls, user_id: int, username: str, password: str) -> "User":
        """Create a user with a random salt and the current registration time"""
        cls._validate_password(password)

        salt = secrets.token_hex(SALT_BYTES)

        return cls(
            user_id=user_id,
            username=username,
            hashed_password=cls._hash_password(password, salt),
            salt=salt,
            registration_date=datetime.now(UTC),
        )

    @staticmethod
    def _validate_password(password: str) -> None:
        """Check the password requirements from the assignment"""
        if not isinstance(password, str):
            raise TypeError("Пароль должен быть строкой")

        if len(password) < MIN_PASSWORD_LENGTH:
            raise ValueError("Пароль должен быть не короче 4 символов")

    @staticmethod
    def _hash_password(password: str, salt: str) -> str:
        """Hash a password and its salt using the assignment's SHA-256 scheme"""
        return hashlib.sha256((password + salt).encode("utf-8")).hexdigest()

    @property
    def user_id(self) -> int:
        """Return the immutable user identifier"""
        return self._user_id

    @property
    def username(self) -> str:
        """Return the username"""
        return self._username

    @username.setter
    def username(self, value: str) -> None:
        """Set a nonempty username"""
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Имя пользователя не может быть пустым")

        self._username = value

    @property
    def hashed_password(self) -> str:
        """Return the password hash for storage"""
        return self._hashed_password

    @property
    def salt(self) -> str:
        """Return the user's salt for storage"""
        return self._salt

    @property
    def registration_date(self) -> datetime:
        """Return the registration date"""
        return self._registration_date

    def get_user_info(self) -> dict[str, int | str]:
        """Return public user details with an ISO-formatted registration date"""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "registration_date": self.registration_date.isoformat(),
        }

    def change_password(self, new_password: str) -> None:
        """Validate and replace the password hash"""
        self._validate_password(new_password)

        self._hashed_password = self._hash_password(new_password, self.salt)

    def verify_password(self, password: str) -> bool:
        """Check a supplied password against the stored hash"""
        if not isinstance(password, str):
            raise TypeError("Пароль должен быть строкой")

        candidate = self._hash_password(password, self.salt)

        return hmac.compare_digest(candidate, self.hashed_password)


class Wallet:
    """Manage a nonnegative balance for one currency"""

    def __init__(self, currency_code: str, balance: float = 0.0) -> None:
        self._currency_code = get_currency(currency_code).code
        self.balance = balance

    @property
    def currency_code(self) -> str:
        """Return the immutable currency code used as a portfolio key"""
        return self._currency_code

    @property
    def balance(self) -> float:
        """Return the current balance"""
        return self._balance

    @balance.setter
    def balance(self, value: float) -> None:
        """Set a finite, nonnegative balance"""
        value = validate_number(value)

        if value < 0:
            raise ValueError("Баланс не может быть отрицательным")

        self._balance = value

    def deposit(self, amount: float) -> None:
        """Add a positive amount to the balance"""
        amount = validate_amount(amount)

        self.balance += amount

    def withdraw(self, amount: float) -> None:
        """Withdraw a positive amount if the balance is sufficient"""
        amount = validate_amount(amount)

        if amount > self.balance:
            raise InsufficientFundsError(
                available=self.balance, required=amount, code=self.currency_code
            )

        self.balance -= amount

    def get_balance_info(self) -> str:
        """Return the currency code and balance for display"""
        return f"{self.currency_code}: {self.balance}"


class Portfolio:
    """Group a user's wallets and calculate their value in a base currency"""

    def __init__(
        self,
        user_id: int,
        wallets: dict[str, Wallet] | None = None,
        user: User | None = None,
    ) -> None:
        if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
            raise ValueError("ID пользователя должен быть положительным целым числом")

        if user is not None:
            if not isinstance(user, User):
                raise TypeError("Владелец портфеля должен быть объектом User")

            if user.user_id != user_id:
                raise ValueError("ID владельца не совпадает с ID пользователя портфеля")

        if wallets is not None and not isinstance(wallets, dict):
            raise TypeError("Кошельки должны быть переданы словарем")

        self._user = user
        self._user_id = user_id
        self._wallets: dict[str, Wallet] = {}

        if wallets is not None:
            for code, wallet in wallets.items():
                code = get_currency(code).code

                if not isinstance(wallet, Wallet):
                    raise TypeError("Значение словаря должно быть объектом Wallet")

                if code != wallet.currency_code:
                    raise ValueError("Ключ словаря не совпадает с валютой кошелька")

                if code in self._wallets:
                    raise ValueError(f"Кошелек '{code}' уже существует")

                self._wallets[code] = wallet

    @property
    def user_id(self) -> int:
        """Return the portfolio owner's identifier"""
        return self._user_id

    @property
    def user(self) -> User | None:
        """Return the supplied owner, if any, without allowing reassignment"""
        return self._user

    @property
    def wallets(self) -> dict[str, Wallet]:
        """Return a shallow copy of the wallet mapping"""
        return self._wallets.copy()

    def add_currency(self, currency_code: str) -> Wallet:
        """Create a wallet if absent, otherwise return the existing wallet"""
        code = get_currency(currency_code).code

        if code not in self._wallets:
            self._wallets[code] = Wallet(code)

        return self._wallets[code]

    def get_wallet(self, currency_code: str) -> Wallet:
        """Return a wallet, raising ValueError if it does not exist"""
        code = get_currency(currency_code).code

        if code not in self._wallets:
            raise ValueError(f"Кошелек '{code}' не найден")

        return self._wallets[code]

    def get_total_value(
        self,
        base_currency: str = "USD",
        rates: dict[str, float] | None = None,
    ) -> float:
        """Value wallets using supplied USD prices keyed by uppercase currency codes.

        USD has an implicit rate of 1. Empty portfolios are worth zero.
        Missing quotes raise ValueError; this model performs no I/O.
        """
        base = get_currency(base_currency).code

        exchange_rates = {} if rates is None else rates

        if not isinstance(exchange_rates, dict):
            raise TypeError("Курсы валют должны быть переданы словарем")

        if not self._wallets:
            return 0.0

        def get_usd_rate(code: str) -> float:
            if code == "USD":
                return 1.0

            if code not in exchange_rates:
                raise ValueError(f"Не удалось получить курс для {code}→USD")

            rate = validate_number(exchange_rates[code])

            if rate <= 0:
                raise ValueError(f"Курс для {code}→USD должен быть положительным")

            return rate

        base_rate = get_usd_rate(base)
        values = []

        for wallet in self._wallets.values():
            if wallet.balance == 0:
                continue

            rate = get_usd_rate(wallet.currency_code) / base_rate
            values.append(wallet.balance * rate)

        return validate_number(math.fsum(values))
