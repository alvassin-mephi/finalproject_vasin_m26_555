"""Run periodic rate updates as a separate foreground process"""

from time import sleep

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.infra.settings import SettingsLoader
from valutatrade_hub.logging_config import setup_parser_logging
from valutatrade_hub.parser_service.updater import RatesUpdater


def main() -> None:
    """Update immediately, then wait between runs until interrupted"""
    try:
        interval = SettingsLoader().get("UPDATE_INTERVAL_SECONDS")

        if isinstance(interval, bool) or not isinstance(interval, int) or interval <= 0:
            raise ValueError(
                "UPDATE_INTERVAL_SECONDS должен быть положительным целым числом"
            )

        setup_parser_logging()

        updater = RatesUpdater()
        print(
            f"Планировщик запущен. Интервал между обновлениями: {interval} с. "
            "Для остановки нажмите Ctrl+C."
        )

        while True:
            try:
                updater.run_update()
            except ApiRequestError as error:
                print(f"{error}. Следующая попытка через {interval} с.")

            sleep(interval)
    except KeyboardInterrupt:
        print("\nПланировщик остановлен.")
    except (TypeError, ValueError, OSError) as error:
        print(f"Ошибка планировщика: {error}")

        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
