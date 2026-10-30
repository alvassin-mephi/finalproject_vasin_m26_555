"""Application operations for managing users and currency portfolios"""

from datetime import UTC, datetime

from valutatrade_hub.core.currencies import CURRENCIES, CryptoCurrency, get_currency
from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    InsufficientFundsError,
)
from valutatrade_hub.core.models import Portfolio, User, Wallet
from valutatrade_hub.core.utils import (
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

    if not portfolio.wallets:
        return {
            "username": user.username,
            "base_currency": base,
            "wallets": [],
            "total_value": 0.0,
        }

    currency_codes = {
        code for code, wallet in portfolio.wallets.items() if wallet.balance > 0
    }
    usd_rates = _load_rates(currency_codes, base_currency=base)["rates"]

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

    rate = get_rate(code, "USD")["rate"]
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


def _get_cached_rates(
    cache: dict,
    currency_codes: set[str],
    base_currency: str,
    now: datetime,
    *,
    allow_stale: bool = False,
) -> dict | None:
    """Validate quotes, optionally retaining stale entries for cache inspection"""
    usd_rates = {"USD": 1.0}
    timestamps = []
    sources = set()
    is_stale = False

    try:
        pairs = cache["pairs"]

        for code in currency_codes | {base_currency}:
            if code == "USD":
                continue

            entry = pairs[f"{code}_USD"]
            source = entry["source"]

            if not isinstance(source, str) or not source.strip() or source == "Stub":
                return None

            rate = validate_number(entry["rate"])
            updated_at = datetime.fromisoformat(entry["updated_at"])

            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=UTC)

            updated_at = updated_at.astimezone(UTC)
            age = (now - updated_at).total_seconds()

            if rate <= 0 or age < 0:
                return None

            entry_is_stale = age >= settings.get("RATES_TTL_SECONDS")

            if entry_is_stale and not allow_stale:
                return None

            usd_rates[code] = rate
            timestamps.append(updated_at)
            sources.add(source.strip())
            is_stale = is_stale or entry_is_stale

        base_rate = usd_rates[base_currency]

        for code in currency_codes:
            rate = validate_number(usd_rates[code] / base_rate)
            reverse_rate = validate_number(base_rate / usd_rates[code])

            if rate <= 0 or reverse_rate <= 0:
                return None
    except (KeyError, TypeError, ValueError, OverflowError):
        return None

    return {
        "rates": usd_rates,
        # A cross rate is only as fresh as its oldest quote
        "updated_at": min(timestamps, default=now).isoformat(timespec="seconds"),
        "source": ", ".join(sorted(sources)),
        "stale": is_stale,
    }


def _load_rates(currency_codes: set[str], base_currency: str = "USD") -> dict:
    """Read fresh cached quotes without network requests or automatic refresh"""
    now = datetime.now(UTC)
    required_codes = currency_codes | {base_currency}

    if required_codes <= {"USD"}:
        return {
            "rates": {"USD": 1.0},
            "updated_at": now.isoformat(timespec="seconds"),
        }

    cache = database.get_rates()

    snapshot = _get_cached_rates(cache, currency_codes, base_currency, now)

    if snapshot is None:
        codes = ", ".join(sorted(required_codes - {"USD"}))

        raise ApiRequestError(
            reason=f"Курсы для {codes} отсутствуют, устарели или некорректны. "
            "Выполните update-rates для обновления кэша."
        )

    return snapshot


def get_rate(from_currency: str, to_currency: str) -> dict:
    """Return a pair from the shared rate source without requiring login"""
    from_currency = get_currency(from_currency).code
    to_currency = get_currency(to_currency).code

    if from_currency == to_currency:
        return {
            "from_currency": from_currency,
            "to_currency": to_currency,
            "rate": 1.0,
            "reverse_rate": 1.0,
            "updated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }

    snapshot = _load_rates({from_currency, to_currency}, base_currency=to_currency)
    usd_rates = snapshot["rates"]

    return {
        "from_currency": from_currency,
        "to_currency": to_currency,
        "rate": usd_rates[from_currency] / usd_rates[to_currency],
        "reverse_rate": usd_rates[to_currency] / usd_rates[from_currency],
        "updated_at": snapshot["updated_at"],
    }


def show_rates(
    currency: str | None = None,
    top: int | None = None,
    base_currency: str = "USD",
) -> dict:
    """Inspect valid cached quotes, including their sources and freshness"""
    base = get_currency(base_currency).code
    code = get_currency(currency).code if currency is not None else None

    if top is not None and (
        isinstance(top, bool) or not isinstance(top, int) or top <= 0
    ):
        raise ValueError("--top должен быть положительным целым числом")

    cache = database.get_rates()

    if not cache or ("pairs" not in cache and cache.get("source") == "Stub"):
        raise ApiRequestError(
            reason="Локальный кэш курсов пуст. Выполните update-rates."
        )

    pairs = cache.get("pairs")

    if not isinstance(pairs, dict):
        raise ValueError("В кэше курсов отсутствует объект pairs")

    if not pairs:
        raise ApiRequestError(
            reason="Локальный кэш курсов пуст. Выполните update-rates."
        )

    codes = (
        {code}
        if code is not None
        else {code for code in CURRENCIES if f"{code}_USD" in pairs}
    )

    if top is not None:
        codes = {
            code for code in codes if isinstance(get_currency(code), CryptoCurrency)
        }

    if not codes:
        raise ValueError("В кэше нет валют, подходящих под выбранные фильтры")

    now = datetime.now(UTC)

    if _get_cached_rates(cache, set(), base, now, allow_stale=True) is None:
        raise ApiRequestError(
            reason=f"Курс базовой валюты {base} отсутствует или некорректен. "
            "Выполните update-rates."
        )

    rows = []
    unavailable = []

    for code in sorted(codes):
        snapshot = _get_cached_rates(cache, {code}, base, now, allow_stale=True)

        if snapshot is None:
            unavailable.append(code)
            continue

        rates = snapshot["rates"]
        rows.append(
            {
                "currency": code,
                "rate": rates[code] / rates[base],
                "updated_at": (
                    None if code == base == "USD" else snapshot["updated_at"]
                ),
                "source": snapshot["source"],
                "stale": snapshot["stale"],
            }
        )

    if not rows:
        raise ApiRequestError(
            reason=f"Нет корректных курсов для {', '.join(unavailable)}. "
            "Выполните update-rates."
        )

    if top is not None:
        rows.sort(key=lambda row: (-row["rate"], row["currency"]))
        rows = rows[:top]

    return {"base_currency": base, "rates": rows, "unavailable": unavailable}
