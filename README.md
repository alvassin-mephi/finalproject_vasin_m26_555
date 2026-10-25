# Платформа для отслеживания и симуляции торговли валютами

Проект реализован в виде консольного приложения, имитирующего работу валютного
кошелька, и оформлен как пакет Python.

Включает два сервиса:

- Основной Сервис (Core Service): предоставляет
  пользовательский интерфейс (CLI), управляет пользователями, их кошельками,
  журналом действий и взаимодействует с сервисом парсинга для получения актуальных
  курсов валют.
- Сервис Парсинга (Parser Service): по запросу
  или расписанию обращается к публичным API, получает актуальные курсы валют,
  обновляет локальный кэш и сохраняет историю курсов валют в JSON-файл.

## Оглавление

- [Установка и запуск](#установка-и-запуск)
- [Структура](#структура)
- [Проверка кода и сборка](#проверка-кода-и-сборка)

## Установка и запуск

Требуются Python 3.12 или новее и uv. Выполняйте команды из корня проекта:

```sh
uv sync
uv run valutatrade
```

Другие способы запуска: `uv run python main.py` и
`uv run python -m valutatrade_hub`.

## Структура

```text
valutatrade_hub/
    cli/                # console interface
    core/               # models and business logic
    infra/              # configuration and JSON storage
    parser_service/     # exchange rate retrieval and storage
    __main__.py         # package entry point for python -m

data/
    users.json          # users
    portfolios.json     # portfolios and wallets
    rates.json          # latest exchange rate cache
    exchange_rates.json # exchange rate history

main.py
pyproject.toml
uv.lock
```

## Проверка кода и сборка

```sh
uv run ruff check .
uv run ruff format --check .
uv build
```

Для форматирования: `uv run ruff format .`.
