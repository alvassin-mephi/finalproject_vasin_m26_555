"""Collect provider quotes and persist successful measurements"""

import logging
from datetime import UTC, datetime
from time import perf_counter

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.logging_config import PARSER_LOGGER_NAME
from valutatrade_hub.parser_service.api_clients import (
    BaseApiClient,
    CoinGeckoClient,
    ExchangeRateApiClient,
)
from valutatrade_hub.parser_service.storage import RatesStorage, make_records

logger = logging.getLogger(PARSER_LOGGER_NAME)


class RatesUpdater:
    """Poll providers independently and save all successful measurements"""

    def __init__(
        self,
        clients: list[BaseApiClient] | None = None,
        storage: RatesStorage | None = None,
    ) -> None:
        self.storage = storage if storage is not None else RatesStorage()
        self.clients = (
            clients
            if clients is not None
            else [
                CoinGeckoClient(config=self.storage.config),
                ExchangeRateApiClient(config=self.storage.config),
            ]
        )

    def run_update(self) -> dict:
        """Return updated count, refresh time, and any failed provider messages"""
        logger.info("Starting rates update: sources=%s", len(self.clients))

        records = []
        errors = {}

        for client in self.clients:
            source = client.SOURCE
            logger.info("Fetching rates: source=%s", source)

            started_at = perf_counter()

            try:
                rates = client.fetch_rates()
                request_ms = round((perf_counter() - started_at) * 1000, 3)

                source_records = make_records(
                    rates,
                    source=source,
                    # Cache freshness is measured from retrieval time
                    timestamp=datetime.now(UTC),
                    meta={"request_ms": request_ms},
                )
            except ApiRequestError as error:
                errors[source] = str(error)
                logger.error("Rate request failed: source=%s error=%s", source, error)
                continue
            except (KeyError, TypeError, ValueError, AttributeError):
                # Do not log a raw provider response or a credential-bearing URL
                errors[source] = "Некорректные данные API-клиента"
                logger.error("Invalid rate response: source=%s", source)
                continue

            logger.debug(
                "Request completed: source=%s request_ms=%s pairs=%s",
                source,
                request_ms,
                ",".join(rates),
            )

            if isinstance(client, CoinGeckoClient):
                for record in source_records:
                    record["meta"]["raw_id"] = client.config.CRYPTO_ID_MAP[
                        record["from_currency"]
                    ]

            records.extend(source_records)
            logger.info(
                "Rates received: source=%s count=%s", source, len(source_records)
            )

        if not records:
            if errors:
                logger.error("Rates update failed: no valid measurements")

                raise ApiRequestError(reason="; ".join(errors.values()))

            logger.info("Rates update finished: no measurements")

            return {"updated": 0, "last_refresh": None, "errors": {}}

        logger.info("Saving rate measurements: count=%s", len(records))
        logger.debug(
            "Saving rates: cache=%s history=%s",
            self.storage.config.RATES_FILE_PATH,
            self.storage.config.HISTORY_FILE_PATH,
        )

        try:
            result = self.storage.save_records(records)
        except (OSError, KeyError, TypeError, ValueError) as error:
            logger.error(
                "Rates update failed during storage: error_type=%s",
                type(error).__name__,
            )

            raise

        result["errors"] = errors
        logger.info(
            "Rates update finished: updated=%s failed_sources=%s last_refresh=%s",
            result["updated"],
            len(errors),
            result["last_refresh"],
        )

        return result
