"""JWT Utils."""

import logging
from datetime import datetime, timedelta
from ...errors import Error

logger = logging.getLogger(__name__)


def exp_env_to_time(env_value):
    if env_value:
        exptime = {
            "exp_days": "days",
            "exp_hours": "hours",
            "exp_mins": "minutes",
            "exp_sec": "seconds",
        }
        key, value = next(iter(env_value.items()))
        if key not in exptime:
            logger.error(
                "Undefined value in EAS_ENTITY_EXPIRATION variable. Use exp_days, exp_hrs, exp_min or exp_sec"
            )
            raise Error(
                "Undefined value in EAS_ENTITY_EXPIRATION variable. Use exp_days, exp_hrs, exp_min or exp_sec"
            )
        if value <= 0:
            logger.error(
                "Value in EAS_ENTITY_EXPIRATION variable is negative or equal 0. Use positive number"
            )
            raise Error(
                "Value in EAS_ENTITY_EXPIRATION variable is negative or equal 0. Use positive number"
            )

        kwargs = {exptime[key]: value}
        now = datetime.now()
        delta = timedelta(**kwargs)
        return (now + delta).timestamp()
