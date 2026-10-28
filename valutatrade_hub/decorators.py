import logging
from collections.abc import Callable
from functools import wraps

from valutatrade_hub.logging_config import ACTION_LOGGER_NAME

logger = logging.getLogger(ACTION_LOGGER_NAME)


def log_action(*, verbose: bool = False) -> Callable:
    """Log a trade result or error, optionally including changes in both wallets"""

    def decorate(func: Callable) -> Callable:
        action = func.__name__.upper()

        @wraps(func)
        def wrapper(user_id: int | None, currency_code: str, amount: float) -> dict:
            try:
                report = func(
                    user_id=user_id, currency_code=currency_code, amount=amount
                )
            except Exception as error:
                logger.error(
                    "%s user_id=%r currency_code=%r amount=%r base='USD' "
                    "result=ERROR error_type=%s error_message=%r",
                    action,
                    user_id,
                    currency_code,
                    amount,
                    type(error).__name__,
                    str(error),
                )

                raise

            message = (
                "%s user_id=%r currency_code=%r amount=%r rate=%r base='USD' result=OK"
            )
            values = [
                action,
                user_id,
                report["currency"],
                report["amount"],
                report["rate"],
            ]

            if verbose:
                message += (
                    " balance_before=%r balance_after=%r usd_before=%r usd_after=%r"
                )
                values.extend(
                    [
                        report["before"],
                        report["after"],
                        report["usd_before"],
                        report["usd_after"],
                    ]
                )

            logger.info(message, *values)

            return report

        return wrapper

    return decorate
