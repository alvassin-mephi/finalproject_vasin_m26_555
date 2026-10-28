"""Application operations for managing users and currency portfolios"""

from datetime import UTC, datetime

from valutatrade_hub.core.currencies import CURRENCIES, get_currency
from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    InsufficientFundsError,
)
from valutatrade_hub.core.models import Portfolio, User, Wallet
from valutatrade_hub.core.utils import (
    EXCHANGE_RATES,
    validate_amount,
    validate_number,
)
from valutatrade_hub.decorators import log_action
from valutatrade_hub.infra.database import DatabaseManager
from valutatrade_hub.infra.settings import SettingsLoader

# All use cases share the same configuration and storage manager
settings = SettingsLoader()
database = DatabaseManager()


def register(username: str, password: str) -> User:
    """Create a user with the configured USD balance without starting a session"""
    users = database.get_users()

    if any(user.username == username for user in users):
        raise ValueError(f"Имя пользователя '{username}' уже занято")

    user_id = max((user.user_id for user in users), default=0) + 1
    user = User.create(user_id, username, password)
    usd_wallet = Wallet(
        currency_code="USD", balance=settings.get("INITIAL_USD_BALANCE")
    )
    portfolio = Portfolio(user_id=user.user_id, wallets={"USD": usd_wallet}, user=user)

    database.create_user(user=user, portfolio=portfolio)

    return user


def login(username: str, password: str) -> User:
    """Authenticate an existing user for the caller's current session"""
    user = database.get_user(username)

    if user is None:
        raise ValueError(f"Пользователь '{username}' не найден")

    if not user.verify_password(password):
        raise ValueError("Неверный пароль")

    return user


def _load_portfolio(user_id: int, *, user: User | None = None) -> Portfolio:
    """Load a portfolio by owner ID, retaining the supplied user when available"""
    portfolio = database.get_portfolio(user_id, user=user)

    if portfolio is None:
        raise ValueError(f"Портфель пользователя с ID {user_id} не найден")

    return portfolio


def show_portfolio(user: User | None, base_currency: str | None = None) -> dict:
    """Load a portfolio and prepare its values for display in the base currency"""
    if user is None:
        raise ValueError("Сначала выполните login")

    if base_currency is None:
        base_currency = settings.get("DEFAULT_BASE_CURRENCY")

    base = get_currency(base_currency).code
    portfolio = _load_portfolio(user.user_id, user=user)
    usd_rates = {base: _get_stub_usd_rate(base)}

    for code, wallet in portfolio.wallets.items():
        if wallet.balance > 0:
            usd_rates[code] = _get_stub_usd_rate(code)

    total_value = portfolio.get_total_value(base_currency=base, rates=usd_rates)
    base_rate = usd_rates[base]
    rows = []

    for code, wallet in portfolio.wallets.items():
        value = 0.0

        if wallet.balance > 0:
            value = wallet.balance * (usd_rates[code] / base_rate)

        rows.append((code, wallet.balance, value))

    return {
        "username": user.username,
        "base_currency": base,
        "wallets": rows,
        "total_value": total_value,
    }


@log_action(verbose=True)
def buy(user_id: int | None, currency_code: str, amount: float) -> dict:
    """Buy currency using the user's USD balance"""
    return _trade(user_id, currency_code, amount, is_sale=False)


@log_action(verbose=True)
def sell(user_id: int | None, currency_code: str, amount: float) -> dict:
    """Sell currency and credit the proceeds to the user's USD wallet"""
    return _trade(user_id, currency_code, amount, is_sale=True)


def _trade(
    user_id: int | None, currency_code: str, amount: float, *, is_sale: bool
) -> dict:
    """Exchange currency and USD, persisting both balances after all checks pass"""
    if user_id is None:
        raise ValueError("Сначала выполните login")

    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        raise ValueError("ID пользователя должен быть положительным целым числом")

    code = get_currency(currency_code).code

    if code == "USD":
        raise ValueError("USD используется для расчетов: выберите другую валюту")

    amount = validate_amount(amount)
    portfolio = _load_portfolio(user_id)

    # Check available funds before requesting the exchange rate
    if is_sale:
        if code not in portfolio.wallets:
            raise InsufficientFundsError(available=0.0, required=amount, code=code)

        wallet = portfolio.get_wallet(code)

        if amount > wallet.balance:
            raise InsufficientFundsError(
                available=wallet.balance, required=amount, code=code
            )
    else:
        wallet = portfolio.add_currency(code)

    rate = _get_stub_usd_rate(code)
    value_usd = validate_amount(amount * rate)

    usd_wallet = portfolio.add_currency("USD")
    before = wallet.balance
    usd_before = usd_wallet.balance

    if is_sale:
        wallet.withdraw(amount)
        usd_wallet.deposit(value_usd)
    else:
        usd_wallet.withdraw(value_usd)
        wallet.deposit(amount)

    database.save_portfolio(portfolio)

    return {
        "operation": "sell" if is_sale else "buy",
        "currency": code,
        "amount": amount,
        "rate": rate,
        "value_usd": value_usd,
        "before": before,
        "after": wallet.balance,
        "usd_before": usd_before,
        "usd_after": usd_wallet.balance,
    }


def _get_stub_usd_rate(code: str) -> float:
    """Validate a stub quote and distinguish provider errors from unknown codes"""
    if code == "USD":
        return 1.0

    try:
        rate = validate_number(EXCHANGE_RATES[code])

        if rate <= 0:
            raise ValueError("Курс должен быть положительным")
    except (KeyError, TypeError, ValueError) as error:
        raise ApiRequestError(
            reason=f"Не удалось получить курс для {code}→USD"
        ) from error

    return rate


def _get_cached_rate(
    cache: dict, from_currency: str, to_currency: str, now: datetime
) -> dict | None:
    """Resolve a pair through fresh USD quotes, using their oldest timestamp"""
    usd_rates = {"USD": 1.0}
    timestamps = []

    try:
        for code in (from_currency, to_currency):
            if code == "USD":
                continue

            entry = cache[f"{code}_USD"]
            rate = validate_number(entry["rate"])
            updated_at = datetime.fromisoformat(entry["updated_at"])

            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=UTC)

            updated_at = updated_at.astimezone(UTC)
            age = (now - updated_at).total_seconds()

            if rate <= 0 or not 0 <= age < settings.get("RATES_TTL_SECONDS"):
                return None

            usd_rates[code] = rate
            timestamps.append(updated_at)

        rate = validate_number(usd_rates[from_currency] / usd_rates[to_currency])
        reverse_rate = validate_number(
            usd_rates[to_currency] / usd_rates[from_currency]
        )

        if rate <= 0 or reverse_rate <= 0:
            return None
    except (KeyError, TypeError, ValueError, OverflowError):
        return None

    return {
        "rate": rate,
        "reverse_rate": reverse_rate,
        # A cross rate is only as fresh as its oldest quote
        "updated_at": min(timestamps).isoformat(timespec="seconds"),
    }


def _fetch_stub_rates(now: datetime) -> dict:
    """Build a cache snapshot from the assignment's fixed USD prices"""
    timestamp = now.isoformat(timespec="seconds")
    cache = {
        f"{code}_USD": {
            "rate": _get_stub_usd_rate(code),
            "updated_at": timestamp,
        }
        for code in CURRENCIES
        if code != "USD"
    }
    cache["source"] = "Stub"
    cache["last_refresh"] = timestamp

    return cache


def get_rate(from_currency: str, to_currency: str) -> dict:
    """Return a cached rate or refresh it from the stub without requiring login"""
    from_currency = get_currency(from_currency).code
    to_currency = get_currency(to_currency).code

    now = datetime.now(UTC)

    if from_currency == to_currency:
        return {
            "from_currency": from_currency,
            "to_currency": to_currency,
            "rate": 1.0,
            "reverse_rate": 1.0,
            "updated_at": now.isoformat(timespec="seconds"),
        }

    cache = database.get_rates()

    result = _get_cached_rate(cache, from_currency, to_currency, now)

    if result is None:
        unavailable = f"Курс {from_currency}→{to_currency} недоступен"

        try:
            cache = _fetch_stub_rates(now)
        except (TypeError, ValueError, OSError) as error:
            raise ApiRequestError(reason=unavailable) from error

        result = _get_cached_rate(cache, from_currency, to_currency, now)

        if result is None:
            raise ApiRequestError(reason=unavailable)

        database.save_rates(cache)

    return {"from_currency": from_currency, "to_currency": to_currency, **result}
