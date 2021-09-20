"""Test Keycloak bootstrap."""

import pytest
import bootstrap
from unittest.mock import MagicMock, patch


def test_noop():
    assert True


@patch("bootstrap.KeycloakAdmin")
def test_main(kc_admin_mock):
    """Test main."""
    rc = bootstrap.main()
    assert rc is True
