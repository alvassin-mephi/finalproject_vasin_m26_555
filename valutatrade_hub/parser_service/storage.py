"""Persist parser measurements and the latest exchange-rate cache"""

from datetime import UTC, datetime

from valutatrade_hub.core.utils import validate_amount, validate_currency_code
from valutatrade_hub.infra.database import load, load_records, save
from valutatrade_hub.parser_service.config import ParserConfig


def _parse_timestamp(value: str) -> datetime:
    """Read ISO timestamps, interpreting a missing timezone as UTC"""
    timestamp = datetime.fromisoformat(value)

    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)

    return timestamp.astimezone(UTC)


def _validate_record(record: dict) -> None:
    """Reject malformed measurements before changing either storage file"""
    source_code = validate_currency_code(record["from_currency"])
    target_code = validate_currency_code(record["to_currency"])

    if (
        source_code != record["from_currency"]
        or target_code != record["to_currency"]
        or target_code != "USD"
    ):
        raise ValueError("Котировки должны иметь формат CODE_USD")

    validate_amount(record["rate"])
    _parse_timestamp(record["timestamp"])

    expected_id = f"{source_code}_{target_code}_{record['timestamp']}"

    if record["id"] != expected_id:
        raise ValueError("ID измерения не соответствует паре и времени")

    source = record["source"]

    if not isinstance(source, str) or not source.strip() or source == "Stub":
        raise ValueError("Не указан источник реального курса")

    if not isinstance(record.get("meta", {}), dict):
        raise ValueError("Метаданные измерения должны быть объектом")


def make_records(
    rates: dict[str, float], *, source: str, timestamp: datetime, meta: dict
) -> list[dict]:
    """Build validated history records from one successful provider response"""
    if not isinstance(rates, dict):
        raise TypeError("API-клиент должен вернуть словарь курсов")

    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)

    timestamp_text = timestamp.astimezone(UTC).isoformat().replace("+00:00", "Z")
    records = []

    for pair, rate in rates.items():
        source_code, target_code = pair.split("_")

        record = {
            "id": f"{pair}_{timestamp_text}",
            "from_currency": source_code,
            "to_currency": target_code,
            "rate": validate_amount(rate),
            "timestamp": timestamp_text,
            "source": source,
            "meta": meta.copy(),
        }
        _validate_record(record)
        records.append(record)

    return records


class RatesStorage:
    """Keep a deduplicated history and atomically replace each JSON file"""

    def __init__(self, config: ParserConfig | None = None) -> None:
        self.config = config if config is not None else ParserConfig()

        if (
            self.config.RATES_FILE_PATH.resolve()
            == self.config.HISTORY_FILE_PATH.resolve()
        ):
            raise ValueError("Кэш и история должны храниться в разных файлах")

    def load_cache(self) -> dict:
        """Read the current schema, treating the old stub cache as empty"""
        cache = load(self.config.RATES_FILE_PATH, default={})

        if not isinstance(cache, dict):
            raise ValueError("Кэш курсов должен содержать JSON-объект")

        if not cache or ("pairs" not in cache and cache.get("source") == "Stub"):
            return {"pairs": {}, "last_refresh": None}

        if not isinstance(cache.get("pairs"), dict):
            raise ValueError("В кэше курсов отсутствует объект pairs")

        return cache

    def save_records(self, records: list[dict]) -> dict:
        """Append unique measurements and replace quotes only with newer ones"""
        for record in records:
            _validate_record(record)

        cache = self.load_cache()
        history = load_records(self.config.HISTORY_FILE_PATH)

        try:
            for record in history:
                _validate_record(record)
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("Некорректная запись в истории курсов") from error

        by_id = {record["id"]: record for record in history}
        pairs = cache["pairs"].copy()
        updated_pairs = set()
        history_changed = False

        for incoming in records:
            # Replaying an ID preserves the first recorded measurement
            record = by_id.get(incoming["id"])

            if record is None:
                record = incoming
                history.append(record)
                by_id[record["id"]] = record
                history_changed = True

            pair = f"{record['from_currency']}_{record['to_currency']}"
            current = pairs.get(pair)

            try:
                validate_amount(current["rate"])
                current_timestamp = _parse_timestamp(current["updated_at"])
                source = current["source"]

                if (
                    not isinstance(source, str)
                    or not source.strip()
                    or source == "Stub"
                ):
                    current_timestamp = None
            except (KeyError, TypeError, ValueError):
                current_timestamp = None

            if (
                current_timestamp is not None
                and _parse_timestamp(record["timestamp"]) <= current_timestamp
            ):
                continue

            pairs[pair] = {
                "rate": record["rate"],
                "updated_at": record["timestamp"],
                "source": record["source"],
            }
            updated_pairs.add(pair)

        last_refresh = cache.get("last_refresh")

        # History goes first: a failed cache write leaves the old snapshot usable
        if history_changed:
            save(self.config.HISTORY_FILE_PATH, history)

        if updated_pairs:
            last_refresh = datetime.now(UTC).isoformat().replace("+00:00", "Z")
            save(
                self.config.RATES_FILE_PATH,
                {"pairs": pairs, "last_refresh": last_refresh},
            )

        return {"updated": len(updated_pairs), "last_refresh": last_refresh}
