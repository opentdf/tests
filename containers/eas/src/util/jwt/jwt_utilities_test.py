"""Test JWT Utils."""

import pytest

from datetime import datetime, timedelta
from .jwt_utilities import exp_env_to_time
from ...eas_config import EASConfig


def test_jwt_utilities_expiration_24hrs():
    """Test expiration time."""
    now = datetime.now()
    exp = (now + timedelta(hours=24)).timestamp()
    hrs23 = now + timedelta(hours=23)
    hrs25 = now + timedelta(hours=25)
    assert datetime.fromtimestamp(exp) > hrs23
    assert datetime.fromtimestamp(exp) < hrs25


def test_key_in_dict():
    """Test key exists."""
    env_value = EASConfig.get_instance().get_item("EAS_ENTITY_EXPIRATION")
    exptime = {
        "exp_days": "days",
        "exp_hours": "hours",
        "exp_mins": "minutes",
        "exp_sec": "seconds",
    }
    key, value = next(iter(env_value.items()))
    if key in exptime:
        assert value == 120


def test_exp_env_to_time_func():
    now = datetime.now()
    delta = timedelta(days=120)
    expected = (now + delta).timestamp()
    date = exp_env_to_time(EASConfig.get_instance().get_item("EAS_ENTITY_EXPIRATION"))
    assert expected == pytest.approx(date)
