"""Parse interactive commands, track the current user, and display results"""

import argparse
import shlex

from prettytable import PrettyTable

from valutatrade_hub.core.currencies import CURRENCIES, CryptoCurrency, get_currency
from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    CurrencyNotFoundError,
    InsufficientFundsError,
)
from valutatrade_hub.core.models import User
from valutatrade_hub.core.usecases import (
    buy,
    get_rate,
    login,
    register,
    sell,
    show_portfolio,
)
from valutatrade_hub.logging_config import setup_logging


def _build_parser() -> argparse.ArgumentParser:
    """Describe supported commands and their required arguments"""
    parser = argparse.ArgumentParser(prog="valutatrade")
    commands = parser.add_subparsers(dest="command", required=True)

    for name, description in (
        ("register", "Зарегистрировать пользователя"),
        ("login", "Войти в систему"),
    ):
        command = commands.add_parser(name, help=description, allow_abbrev=False)
        command.add_argument("--username", required=True)
        command.add_argument("--password", required=True)

    portfolio_command = commands.add_parser(
        "show-portfolio", help="Показать портфель", allow_abbrev=False
    )
    portfolio_command.add_argument("--base", help="Базовая валюта")

    for name, description in (
        ("buy", "Купить валюту за USD"),
        ("sell", "Продать валюту за USD"),
    ):
        command = commands.add_parser(name, help=description, allow_abbrev=False)
        command.add_argument("--currency", required=True, help="Код валюты")
        command.add_argument(
            "--amount", required=True, type=float, help="Количество единиц валюты"
        )

    rate_command = commands.add_parser(
        "get-rate", help="Показать курс валюты", allow_abbrev=False
    )
    rate_command.add_argument("--from", dest="from_currency", required=True)
    rate_command.add_argument("--to", dest="to_currency", required=True)

    commands.add_parser("help", help="Показать список команд")
    commands.add_parser("exit", help="Завершить работу")

    return parser


def _format_amount(amount: float, currency_code: str) -> str:
    """Keep eight decimal places for crypto amounts and two for fiat amounts"""
    precision = 8 if isinstance(get_currency(currency_code), CryptoCurrency) else 2

    return f"{amount:,.{precision}f}"


def _print_portfolio(report: dict) -> None:
    """Display a portfolio report without performing financial calculations"""
    if not report["wallets"]:
        print(f"Портфель пользователя '{report['username']}' пуст.")

        return

    base = report["base_currency"]
    table = PrettyTable(["Валюта", "Баланс", f"Стоимость ({base})"])
    table.align["Валюта"] = "l"
    table.align["Баланс"] = "r"
    table.align[f"Стоимость ({base})"] = "r"

    for code, balance, value in report["wallets"]:
        table.add_row(
            [code, _format_amount(balance, code), _format_amount(value, base)]
        )

    print(f"Портфель пользователя '{report['username']}' (база: {base}):")
    print(table)
    print(f"ИТОГО: {_format_amount(report['total_value'], base)} {base}")


def _print_trade(report: dict) -> None:
    """Display the exchanged amount and the changes in both wallets"""
    code = report["currency"]
    operation = "Продажа" if report["operation"] == "sell" else "Покупка"
    value_label = "Выручка" if report["operation"] == "sell" else "Стоимость покупки"

    print(
        f"{operation} выполнена: {_format_amount(report['amount'], code)} {code} "
        f"по курсу {report['rate']:,.8f} USD/{code}"
    )
    print("Изменения в портфеле:")
    print(
        f"- {code}: было {_format_amount(report['before'], code)} "
        f"→ стало {_format_amount(report['after'], code)}"
    )
    print(
        f"- USD: было {_format_amount(report['usd_before'], 'USD')} "
        f"→ стало {_format_amount(report['usd_after'], 'USD')}"
    )
    print(f"{value_label}: {_format_amount(report['value_usd'], 'USD')} USD")


def _print_rate(report: dict) -> None:
    """Display both rate directions and the timestamp with its UTC offset"""
    source = report["from_currency"]
    target = report["to_currency"]
    timestamp = report["updated_at"].replace("T", " ")

    print(f"Курс {source}→{target}: {report['rate']:.8f} (обновлено: {timestamp})")
    print(f"Обратный курс {target}→{source}: {report['reverse_rate']:.8f}")


def main() -> None:
    """Run the command loop and keep the current user in memory"""
    try:
        setup_logging()
    except (OSError, TypeError, ValueError) as error:
        print(f"Не удалось настроить логирование: {error}")

        return

    parser = _build_parser()
    current_user: User | None = None

    print("ValutaTrade Hub — симулятор валютного кошелька")
    print("Введите help для списка команд, exit для выхода.")

    while True:
        try:
            command_line = input("> ")
        except (EOFError, KeyboardInterrupt):
            print()
            break

        try:
            arguments = shlex.split(command_line)
        except ValueError as error:
            print(f"Ошибка команды: {error}")
            continue

        if not arguments:
            continue

        try:
            command = parser.parse_args(arguments)
        except SystemExit:
            continue

        try:
            if command.command == "register":
                user = register(command.username, command.password)

                print(
                    f"Пользователь '{user.username}' зарегистрирован "
                    f"(id={user.user_id}). Войдите: "
                    f"login --username {shlex.quote(user.username)} --password ****"
                )

            elif command.command == "login":
                current_user = login(command.username, command.password)

                print(f"Вы вошли как '{current_user.username}'")

            elif command.command == "show-portfolio":
                report = show_portfolio(current_user, command.base)

                _print_portfolio(report)

            elif command.command == "buy":
                report = buy(
                    user_id=current_user.user_id if current_user is not None else None,
                    currency_code=command.currency,
                    amount=command.amount,
                )

                _print_trade(report)

            elif command.command == "sell":
                report = sell(
                    user_id=current_user.user_id if current_user is not None else None,
                    currency_code=command.currency,
                    amount=command.amount,
                )

                _print_trade(report)

            elif command.command == "get-rate":
                report = get_rate(
                    from_currency=command.from_currency,
                    to_currency=command.to_currency,
                )

                _print_rate(report)

            elif command.command == "help":
                parser.print_help()

            elif command.command == "exit":
                break
        except InsufficientFundsError as error:
            print(error)
        except CurrencyNotFoundError as error:
            print(error)
            print(f"Поддерживаемые валюты: {', '.join(CURRENCIES)}")
        except ApiRequestError as error:
            print(error)
            print("Повторите попытку позже.")
        except (TypeError, ValueError) as error:
            print(error)
        except OSError as error:
            print(f"Ошибка работы с хранилищем: {error}")
