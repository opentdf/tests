import filecmp
import random
import string

import abac
import tdfs


otdfctl = abac.OpentdfCommandLineTool()


def test_namespaces_list():
    ns = otdfctl.namespace_list()
    assert len(ns) >= 4


def test_attribute_create():
    random_ns = "".join(random.choices(string.ascii_lowercase, k=8)) + ".com"
    ns = otdfctl.namespace_create(random_ns)
    anyof = otdfctl.attribute_create(
        ns, "free", abac.AttributeRule.ANY_OF, ["1", "2", "3"]
    )
    allof = otdfctl.attribute_create(
        ns, "strict", abac.AttributeRule.ALL_OF, ["1", "2", "3"]
    )
    assert anyof != allof


def test_scs_create():
    c = abac.Condition(
        subject_external_selector_value=".clientId",
        operator=abac.SubjectMappingOperatorEnum.IN,
        subject_external_values=["opentdf-sdk"],
    )
    cg = abac.ConditionGroup(
        boolean_operator=abac.ConditionBooleanTypeEnum.OR, conditions=[c]
    )

    sc = otdfctl.scs_create(
        [abac.SubjectSet(condition_groups=[cg])],
    )
    assert len(sc.subject_sets) == 1


def load_cached_kas_keys() -> abac.PublicKey:
    keyset: list[abac.KasPublicKey] = []
    with open("../../platform/kas-cert.pem", "r") as rsaFile:
        keyset.append(
            abac.KasPublicKey(
                alg=abac.KAS_PUBLIC_KEY_ALG_ENUM_RSA_2048,
                kid="r1",
                pem=rsaFile.read(),
            )
        )
    with open("../../platform/kas-ec-cert.pem", "r") as ecFile:
        keyset.append(
            abac.KasPublicKey(
                alg=abac.KAS_PUBLIC_KEY_ALG_ENUM_EC_SECP256R1,
                kid="e1",
                pem=ecFile.read(),
            )
        )
    return abac.PublicKey(
        cached=abac.KasPublicKeySet(
            keys=keyset,
        )
    )


def load_local_kas_key() -> abac.PublicKey:
    with open("../../platform/kas-cert.pem", "r") as rsaFile:
        return abac.PublicKey(
            local=rsaFile.read(),
        )


def test_autoconfigure_one_attribute(tmp_dir, pt_file):
    # Create a new attribute in a random namespace
    random_ns = "".join(random.choices(string.ascii_lowercase, k=8)) + ".com"
    ns = otdfctl.namespace_create(random_ns)
    anyof = otdfctl.attribute_create(ns, "letra", abac.AttributeRule.ANY_OF, ["alpha"])
    assert anyof.values
    (alpha,) = anyof.values
    assert alpha.value == "alpha"

    # Then assign it to all clientIds = opentdf-sdk
    sc = otdfctl.scs_create(
        [
            abac.SubjectSet(
                condition_groups=[
                    abac.ConditionGroup(
                        boolean_operator=abac.ConditionBooleanTypeEnum.OR,
                        conditions=[
                            abac.Condition(
                                subject_external_selector_value=".clientId",
                                operator=abac.SubjectMappingOperatorEnum.IN,
                                subject_external_values=["opentdf", "opentdf-sdk"],
                            )
                        ],
                    )
                ]
            )
        ],
    )
    sm = otdfctl.scs_map(sc, alpha)
    assert sm.attribute_value.value == "alpha"
    # Now assign it to the current KAS
    kas_entry_alpha = otdfctl.kas_registry_create_if_not_present(
        "http://localhost:8080/kas",
        load_local_kas_key(),
    )
    otdfctl.grant_assign_value(kas_entry_alpha, alpha)

    # We have a grant for alpha to localhost kas. Now try to use it...

    # Encrypt go
    ct_file = f"{tmp_dir}test-abac-one.tdf"
    tdfs.encrypt(
        "go",
        pt_file,
        ct_file,
        mime_type="text/plain",
        fmt="ztdf",
        attr_values=[f"https://{random_ns}/attr/letra/value/alpha"],
    )
    manifest = tdfs.manifest(ct_file)
    assert len(manifest.encryptionInformation.keyAccess) == 1

    rt_file = f"{tmp_dir}test-abac-one.untdf"
    rt_file_2 = f"{tmp_dir}test-abac-one-2.untdf"
    tdfs.decrypt("go", ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)
    tdfs.decrypt("java", ct_file, rt_file_2, "ztdf")
    assert filecmp.cmp(pt_file, rt_file_2)

    # Encrypt java
    ct_file = f"{tmp_dir}test-abac-one-2.tdf"
    tdfs.encrypt(
        "java",
        pt_file,
        ct_file,
        mime_type="text/plain",
        fmt="ztdf",
        attr_values=[f"https://{random_ns}/attr/letra/value/alpha"],
    )
    manifest = tdfs.manifest(ct_file)
    assert len(manifest.encryptionInformation.keyAccess) == 1

    rt_file = f"{tmp_dir}test-abac-one-3.untdf"
    rt_file_2 = f"{tmp_dir}test-abac-one-4.untdf"
    tdfs.decrypt("go", ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)
    tdfs.decrypt("java", ct_file, rt_file_2, "ztdf")
    assert filecmp.cmp(pt_file, rt_file_2)


def test_autoconfigure_two_kas_or(tmp_dir, pt_file):
    # Create a new attribute in a random namespace
    random_ns = "".join(random.choices(string.ascii_lowercase, k=8)) + ".com"
    ns = otdfctl.namespace_create(random_ns)
    anyof = otdfctl.attribute_create(
        ns, "letra", abac.AttributeRule.ANY_OF, ["alpha", "beta"]
    )
    assert anyof.values
    alpha, beta = anyof.values
    assert alpha.value == "alpha"
    assert beta.value == "beta"

    # Then assign it to all clientIds = opentdf-sdk
    sc = otdfctl.scs_create(
        [
            abac.SubjectSet(
                condition_groups=[
                    abac.ConditionGroup(
                        boolean_operator=abac.ConditionBooleanTypeEnum.OR,
                        conditions=[
                            abac.Condition(
                                subject_external_selector_value=".clientId",
                                operator=abac.SubjectMappingOperatorEnum.IN,
                                subject_external_values=["opentdf", "opentdf-sdk"],
                            )
                        ],
                    )
                ]
            )
        ],
    )
    sm = otdfctl.scs_map(sc, alpha)
    assert sm.attribute_value.value == "alpha"
    # Now assign it to the current KAS
    kas_entry_alpha = otdfctl.kas_registry_create_if_not_present(
        "http://localhost:8080/kas",
        load_cached_kas_keys(),
    )
    otdfctl.grant_assign_value(kas_entry_alpha, alpha)

    kas_entry_beta = otdfctl.kas_registry_create_if_not_present(
        "http://localhost:8282/kas",
        load_cached_kas_keys(),
    )
    otdfctl.grant_assign_value(kas_entry_beta, beta)

    # We have a grant for alpha to localhost kas. Now try to use it...
    # encrypt go
    ct_file = f"{tmp_dir}test-abac-or.tdf"
    tdfs.encrypt(
        "go",
        pt_file,
        ct_file,
        mime_type="text/plain",
        fmt="ztdf",
        attr_values=[
            f"https://{random_ns}/attr/letra/value/alpha",
            f"https://{random_ns}/attr/letra/value/beta",
        ],
    )
    manifest = tdfs.manifest(ct_file)
    assert len(manifest.encryptionInformation.keyAccess) == 2
    assert (
        manifest.encryptionInformation.keyAccess[0].sid
        == manifest.encryptionInformation.keyAccess[1].sid
    )
    assert set(["http://localhost:8080/kas", "http://localhost:8282/kas"]) == set(
        [kao.url for kao in manifest.encryptionInformation.keyAccess]
    )

    rt_file = f"{tmp_dir}test-abac-or.untdf"
    rt_file_2 = f"{tmp_dir}test-abac-or-2.untdf"
    tdfs.decrypt("go", ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)
    tdfs.decrypt("java", ct_file, rt_file_2, "ztdf")
    assert filecmp.cmp(pt_file, rt_file_2)

    # encrypt java
    ct_file = f"{tmp_dir}test-abac-or-2.tdf"
    tdfs.encrypt(
        "java",
        pt_file,
        ct_file,
        mime_type="text/plain",
        fmt="ztdf",
        attr_values=[
            f"https://{random_ns}/attr/letra/value/alpha",
            f"https://{random_ns}/attr/letra/value/beta",
        ],
    )
    manifest = tdfs.manifest(ct_file)
    assert len(manifest.encryptionInformation.keyAccess) == 2
    assert (
        manifest.encryptionInformation.keyAccess[0].sid
        == manifest.encryptionInformation.keyAccess[1].sid
    )
    assert set(["http://localhost:8080/kas", "http://localhost:8282/kas"]) == set(
        [kao.url for kao in manifest.encryptionInformation.keyAccess]
    )

    rt_file = f"{tmp_dir}test-abac-or-3.untdf"
    rt_file_2 = f"{tmp_dir}test-abac-or-4.untdf"
    tdfs.decrypt("go", ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)
    tdfs.decrypt("java", ct_file, rt_file_2, "ztdf")
    assert filecmp.cmp(pt_file, rt_file_2)


def test_autoconfigure_double_kas_and(tmp_dir, pt_file):
    # Create a new attribute in a random namespace
    random_ns = "".join(random.choices(string.ascii_lowercase, k=8)) + ".com"
    ns = otdfctl.namespace_create(random_ns)
    allof = otdfctl.attribute_create(
        ns, "ot", abac.AttributeRule.ALL_OF, ["alef", "bet", "gimmel"]
    )
    assert allof.values
    alef, bet, gimmel = allof.values
    assert alef.value == "alef"
    assert bet.value == "bet"
    assert gimmel.value == "gimmel"

    # Then assign it to all clientIds = opentdf-sdk
    sc = otdfctl.scs_create(
        [
            abac.SubjectSet(
                condition_groups=[
                    abac.ConditionGroup(
                        boolean_operator=abac.ConditionBooleanTypeEnum.OR,
                        conditions=[
                            abac.Condition(
                                subject_external_selector_value=".clientId",
                                operator=abac.SubjectMappingOperatorEnum.IN,
                                subject_external_values=["opentdf", "opentdf-sdk"],
                            )
                        ],
                    )
                ]
            )
        ],
    )
    sm1 = otdfctl.scs_map(sc, alef)
    assert sm1.attribute_value.value == "alef"
    sm2 = otdfctl.scs_map(sc, bet)
    assert sm2.attribute_value.value == "bet"
    # Now assign it to the current KAS
    kas_entry_alpha = otdfctl.kas_registry_create_if_not_present(
        "http://localhost:8080/kas",
        load_cached_kas_keys(),
    )
    otdfctl.grant_assign_value(kas_entry_alpha, alef)

    kas_entry_beta = otdfctl.kas_registry_create_if_not_present(
        "http://localhost:8282/kas",
        load_cached_kas_keys(),
    )
    otdfctl.grant_assign_value(kas_entry_beta, bet)

    # We have a grant for alpha to localhost kas. Now try to use it...
    # encrypt go
    ct_file = f"{tmp_dir}test-abac-double.tdf"
    tdfs.encrypt(
        "go",
        pt_file,
        ct_file,
        mime_type="text/plain",
        fmt="ztdf",
        attr_values=[
            f"https://{random_ns}/attr/ot/value/alef",
            f"https://{random_ns}/attr/ot/value/bet",
        ],
    )
    manifest = tdfs.manifest(ct_file)
    assert len(manifest.encryptionInformation.keyAccess) == 2
    assert (
        manifest.encryptionInformation.keyAccess[0].sid
        != manifest.encryptionInformation.keyAccess[1].sid
    )
    assert set(["http://localhost:8080/kas", "http://localhost:8282/kas"]) == set(
        [kao.url for kao in manifest.encryptionInformation.keyAccess]
    )

    rt_file = f"{tmp_dir}test-abac-double.untdf"
    rt_file_2 = f"{tmp_dir}test-abac-double-2.untdf"
    tdfs.decrypt("go", ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)
    tdfs.decrypt("java", ct_file, rt_file_2, "ztdf")
    assert filecmp.cmp(pt_file, rt_file_2)

    # encrypt java
    ct_file = f"{tmp_dir}test-abac-double-2.tdf"
    tdfs.encrypt(
        "java",
        pt_file,
        ct_file,
        mime_type="text/plain",
        fmt="ztdf",
        attr_values=[
            f"https://{random_ns}/attr/ot/value/alef",
            f"https://{random_ns}/attr/ot/value/bet",
        ],
    )
    manifest = tdfs.manifest(ct_file)
    assert len(manifest.encryptionInformation.keyAccess) == 2
    assert (
        manifest.encryptionInformation.keyAccess[0].sid
        != manifest.encryptionInformation.keyAccess[1].sid
    )
    assert set(["http://localhost:8080/kas", "http://localhost:8282/kas"]) == set(
        [kao.url for kao in manifest.encryptionInformation.keyAccess]
    )

    rt_file = f"{tmp_dir}test-abac-double-3.untdf"
    rt_file_2 = f"{tmp_dir}test-abac-double-4.untdf"
    tdfs.decrypt("go", ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)
    tdfs.decrypt("java", ct_file, rt_file_2, "ztdf")
    assert filecmp.cmp(pt_file, rt_file_2)
