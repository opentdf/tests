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

import pytest

import abac
import tdfs
from otdfctl import OpentdfCommandLineTool


@pytest.fixture(scope="session")
def platform_url_ers_ms() -> str:
    """URL for the multi-strategy ERS platform instance."""
    return os.getenv("PLATFORMURL_ERS_MS", "http://localhost:8090")


@pytest.fixture(scope="session")
def kas_url_ers_ms(platform_url_ers_ms: str) -> str:
    """KAS URL colocated with the multi-strategy ERS platform."""
    return f"{platform_url_ers_ms}/kas"


@pytest.fixture(scope="module")
def kas_entry_ers_ms(
    otdfctl: OpentdfCommandLineTool,
    cached_kas_keys: abac.PublicKey,
    kas_url_ers_ms: str,
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
