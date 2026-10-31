"""HTTP clients that normalize provider quotes to USD prices per currency unit"""

from abc import ABC, abstractmethod
from urllib.parse import quote

import requests

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.core.utils import validate_number
from valutatrade_hub.parser_service.config import ParserConfig

HTTP_ERRORS = {
    400: "некорректные параметры запроса",
    401: "отсутствует или неверен API-ключ; проверьте ключ",
    403: "доступ к API запрещен",
    408: "сервер не успел обработать запрос; повторите update-rates позже",
    429: "превышен лимит запросов; повторите попытку позже",
    500: "внутренняя ошибка сервера; повторите update-rates позже",
    503: "сервис временно недоступен; повторите update-rates позже",
}

EXCHANGERATE_ERRORS = {
    "unsupported-code": "API не поддерживает базовую валюту",
    "unknown-code": "API не поддерживает базовую валюту",
    "malformed-request": "некорректные параметры запроса",
    "invalid-key": "неверный API-ключ; проверьте EXCHANGERATE_API_KEY в окружении",
    "inactive-account": "учетная запись не активирована; подтвердите email",
    "quota-reached": "исчерпана квота запросов; повторите попытку позже",
}


class BaseApiClient(ABC):
    """Share HTTP handling while leaving provider-specific parsing to subclasses"""

    SOURCE = "API"

    def __init__(self, config: ParserConfig | None = None) -> None:
        self.config = config if config is not None else ParserConfig()

    @abstractmethod
    def fetch_rates(self) -> dict[str, float]:
        """Return finite positive rates keyed by currency pairs such as BTC_USD"""

    def _request_json(
        self,
        url: str,
        *,
        params: dict | None = None,
        headers: dict | None = None,
    ) -> dict:
        """Fetch a JSON object without exposing credentials from request errors"""
        try:
            with requests.get(
                url,
                params=params,
                headers=headers,
                timeout=self.config.REQUEST_TIMEOUT,
                allow_redirects=False,
            ) as response:
                if response.status_code != 200:
                    reason = HTTP_ERRORS.get(response.status_code, "неожиданный ответ")

                    raise ApiRequestError(
                        reason=f"{self.SOURCE}: HTTP {response.status_code}, {reason}"
                    )

                try:
                    data = response.json()
                except ValueError:
                    raise ApiRequestError(
                        reason=f"{self.SOURCE}: ответ не содержит корректный JSON"
                    ) from None
        except requests.exceptions.Timeout:
            raise ApiRequestError(
                reason=f"{self.SOURCE}: превышено время ожидания ответа. "
                "Повторите update-rates позже."
            ) from None
        except requests.exceptions.RequestException:
            # Request exceptions may include the URL with the API key
            raise ApiRequestError(
                reason=f"{self.SOURCE}: не удалось выполнить HTTP-запрос. "
                "Проверьте подключение к интернету и повторите update-rates."
            ) from None

        if not isinstance(data, dict):
            raise ApiRequestError(reason=f"{self.SOURCE}: ожидался JSON-объект")

        return data

    def _positive_rate(self, value: object, code: str) -> float:
        """Validate a provider value or computed quote without echoing raw data"""
        try:
            rate = validate_number(value)

            if rate <= 0:
                raise ValueError("Курс должен быть положительным")
        except (TypeError, ValueError):
            raise ApiRequestError(
                reason=f"{self.SOURCE}: некорректный курс для {code}"
            ) from None

        return rate


class CoinGeckoClient(BaseApiClient):
    """Fetch configured cryptocurrencies by CoinGecko IDs in one request"""

    SOURCE = "CoinGecko"

    def fetch_rates(self) -> dict[str, float]:
        """Return crypto prices in USD, optionally using a Demo API key"""
        if not self.config.CRYPTO_CURRENCIES:
            return {}

        ids = {}

        for code in self.config.CRYPTO_CURRENCIES:
            coin_id = self.config.CRYPTO_ID_MAP.get(code)

            if not isinstance(coin_id, str) or not coin_id.strip():
                raise ApiRequestError(
                    reason=f"{self.SOURCE}: не задан API ID для {code}"
                )

            ids[code] = coin_id.strip()

        headers = {}

        if self.config.COINGECKO_API_KEY:
            headers["x-cg-demo-api-key"] = self.config.COINGECKO_API_KEY

        data = self._request_json(
            self.config.COINGECKO_URL,
            params={"ids": ",".join(ids.values()), "vs_currencies": "usd"},
            headers=headers,
        )

        rates = {}

        for code, coin_id in ids.items():
            try:
                value = data[coin_id]["usd"]
            except (KeyError, TypeError):
                raise ApiRequestError(
                    reason=f"{self.SOURCE}: отсутствует курс для {code}"
                ) from None

            rates[f"{code}_USD"] = self._positive_rate(value, code)

        return rates


class ExchangeRateApiClient(BaseApiClient):
    """Fetch fiat conversion rates and normalize their direction to currency/USD"""

    SOURCE = "ExchangeRate-API"

    def fetch_rates(self) -> dict[str, float]:
        """Return fiat prices in USD regardless of the configured request base"""
        if not self.config.FIAT_CURRENCIES:
            return {}

        key = self.config.EXCHANGERATE_API_KEY

        if not key or not key.strip():
            raise ApiRequestError(
                reason=f"{self.SOURCE}: задайте EXCHANGERATE_API_KEY в окружении"
            )

        base = self.config.BASE_CURRENCY
        url = (
            f"{self.config.EXCHANGERATE_API_URL.rstrip('/')}/"
            f"{quote(key.strip(), safe='')}/latest/{base}"
        )
        data = self._request_json(url)

        if data.get("result") != "success":
            error_type = data.get("error-type")
            reason = "API не подтвердил успешный результат"

            if isinstance(error_type, str):
                reason = EXCHANGERATE_ERRORS.get(error_type, reason)

            raise ApiRequestError(reason=f"{self.SOURCE}: {reason}")

        if data.get("base_code") != base:
            raise ApiRequestError(
                reason=f"{self.SOURCE}: неверная базовая валюта ответа"
            )

        conversions = data.get("conversion_rates")

        if not isinstance(conversions, dict):
            raise ApiRequestError(reason=f"{self.SOURCE}: отсутствует conversion_rates")

        usd_per_base = self._positive_rate(conversions.get("USD"), "USD")

        if base == "USD" and usd_per_base != 1.0:
            raise ApiRequestError(reason=f"{self.SOURCE}: курс USD к USD должен быть 1")

        rates = {}

        for code in self.config.FIAT_CURRENCIES:
            units_per_base = self._positive_rate(conversions.get(code), code)
            # The API quotes currency units per base unit; Core needs USD per unit
            rates[f"{code}_USD"] = self._positive_rate(
                usd_per_base / units_per_base, code
            )

        return rates
