"""Multi-strategy ERS fixtures.

Fixtures for tests that target the second platform instance (`platform-ers-ms`
on port 8090) which runs with `entityresolution: type: multi-strategy` and a
SQL provider. otdf-local boots this instance alongside the default
Keycloak-ERS platform; CI does the equivalent via a start-additional-platform
step.

Tests that don't reference these fixtures are unaffected — mirroring the
kas_entry_alpha / kas_entry_beta / ... pattern in fixtures.kas.
"""

import os
import random
import string
from urllib.error import URLError
from urllib.request import urlopen

import pytest

import abac
import tdfs
from otdfctl import OpentdfCommandLineTool


@pytest.fixture(scope="session")
def platform_url_ers_ms() -> str:
    """URL for the multi-strategy ERS platform instance."""
    return os.getenv("PLATFORMURL_ERS_MS", "http://localhost:8090")


@pytest.fixture(scope="session")
def _require_ers_ms_platform(platform_url_ers_ms: str) -> None:
    """Skip tests that depend on the ers-ms platform when it isn't running.

    The multi-strategy platform requires both opentdf/platform#3645 and
    opentdf/platform#3543 to be present. Until both land upstream, CI will
    start the ers-ms platform on a best-effort basis and this fixture is
    what keeps the test from producing a hard failure that masks unrelated
    xtest results.
    """
    healthz = f"{platform_url_ers_ms}/healthz"
    try:
        with urlopen(healthz, timeout=3.0) as resp:
            if resp.status == 200:
                return
            pytest.skip(
                f"ers-ms platform at {platform_url_ers_ms} not healthy (HTTP {resp.status}); "
                "requires opentdf/platform#3645 and #3543 to be present"
            )
    except (URLError, TimeoutError, OSError) as e:
        pytest.skip(
            f"ers-ms platform at {platform_url_ers_ms} not reachable ({e}); "
            "requires opentdf/platform#3645 and #3543 to be present"
        )


@pytest.fixture(scope="session")
def kas_url_ers_ms(platform_url_ers_ms: str) -> str:
    """KAS URL colocated with the multi-strategy ERS platform."""
    return f"{platform_url_ers_ms}/kas"


@pytest.fixture(scope="module")
def kas_entry_ers_ms(
    otdfctl: OpentdfCommandLineTool,
    cached_kas_keys: abac.PublicKey,
    kas_url_ers_ms: str,
    _require_ers_ms_platform: None,
) -> abac.KasEntry:
    """KAS registry entry for the multi-strategy-ERS platform's KAS."""
    return otdfctl.kas_registry_create_if_not_present(kas_url_ers_ms, cached_kas_keys)


@pytest.fixture(scope="module")
def scs_department_finance(
    otdfctl: OpentdfCommandLineTool,
) -> abac.SubjectConditionSet:
    """SCS that matches subjects whose flattened claims include department=finance.

    The multi-strategy SQL provider maps `azp` (or `userName`) -> a row in
    ers_attributes and emits `department` in the output_mapping. The PDP
    flattens the returned EntityRepresentation into dot-notation claims, so
    `.department` selects the value emitted by the provider.
    """
    return otdfctl.scs_create(
        [
            abac.SubjectSet(
                condition_groups=[
                    abac.ConditionGroup(
                        boolean_operator=abac.ConditionBooleanTypeEnum.AND,
                        conditions=[
                            abac.Condition(
                                subject_external_selector_value=".department",
                                operator=abac.SubjectMappingOperatorEnum.IN,
                                subject_external_values=["finance"],
                            )
                        ],
                    )
                ]
            )
        ]
    )


@pytest.fixture(scope="module")
def attribute_ers_ms_finance_grant(
    otdfctl: OpentdfCommandLineTool,
    kas_entry_ers_ms: abac.KasEntry,
    kas_public_key_r1: abac.KasPublicKey,
    scs_department_finance: abac.SubjectConditionSet,
    _require_ers_ms_platform: None,
) -> abac.AttributeValue:
    """Attribute value `department/finance` granted to the ers-ms KAS.

    The KAS URL baked into the TDF's keyAccess entry is the ers-ms KAS
    (localhost:8090), so decrypt naturally routes rewrap through the
    multi-strategy platform. Access is gated by the .department=finance
    subject condition.
    """
    ns_name = "ersms-" + "".join(random.choices(string.ascii_lowercase, k=8)) + ".com"
    ns = otdfctl.namespace_create(ns_name)

    attr = otdfctl.attribute_create(
        ns, "department", abac.AttributeRule.ANY_OF, ["finance", "legal"]
    )
    assert attr.values
    finance = next(v for v in attr.values if v.value == "finance")

    otdfctl.scs_map(scs_department_finance, finance)

    pfs = tdfs.get_platform_features()
    if "key_management" not in pfs.features:
        otdfctl.grant_assign_value(kas_entry_ers_ms, finance)
    else:
        kas_key = otdfctl.kas_registry_create_public_key_only(
            kas_entry_ers_ms, kas_public_key_r1
        )
        otdfctl.key_assign_value(kas_key, finance)

    return finance
