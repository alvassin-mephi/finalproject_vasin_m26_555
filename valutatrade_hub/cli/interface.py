"""Parse interactive commands, track the current user, and display results"""

import argparse
import shlex

from prettytable import PrettyTable

from valutatrade_hub.core.models import User
from valutatrade_hub.core.usecases import login, register, show_portfolio


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
    portfolio_command.add_argument("--base", default="USD", help="Базовая валюта")

    commands.add_parser("help", help="Показать список команд")
    commands.add_parser("exit", help="Завершить работу")

    return parser


def _format_amount(amount: float, currency_code: str) -> str:
    """Keep eight decimal places for crypto amounts and two for fiat amounts"""
    precision = 8 if currency_code in ("BTC", "ETH") else 2

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


def main() -> None:
    """Run the command loop and keep the current user in memory"""
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

            elif command.command == "help":
                parser.print_help()

            elif command.command == "exit":
                break
        except (TypeError, ValueError) as error:
            print(error)
        except OSError as error:
            print(f"Ошибка работы с хранилищем: {error}")
