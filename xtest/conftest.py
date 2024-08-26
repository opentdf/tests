import abac
import os
import pytest


def pytest_addoption(parser) -> None:
    parser.addoption(
        "--large",
        action="store_true",
        help="generate a large (greater than 4 GiB) file for testing",
    )
    parser.addoption(
        "--sdks", help="select which sdks to run by default, unless overridden"
    )
    parser.addoption("--sdks-decrypt", help="select which sdks to run for decrypt only")
    parser.addoption("--sdks-encrypt", help="select which sdks to run for encrypt only")
    parser.addoption("--containers", help="which container formats to test")
    parser.addoption("--feature-flags", help="which experimental features to test")


def pytest_generate_tests(metafunc) -> None:
    if "size" in metafunc.fixturenames:
        metafunc.parametrize(
            "size", ["large" if metafunc.config.getoption("large") else "small"]
        )
    if "encrypt_sdk" in metafunc.fixturenames:
        if metafunc.config.getoption("--sdks-encrypt"):
            encrypt_sdks = metafunc.config.getoption("--sdks-encrypt").split()
        elif metafunc.config.getoption("--sdks"):
            encrypt_sdks = metafunc.config.getoption("--sdks").split()
        else:
            encrypt_sdks = ["js", "go", "java"]
        metafunc.parametrize("encrypt_sdk", encrypt_sdks)
    if "decrypt_sdk" in metafunc.fixturenames:
        if metafunc.config.getoption("--sdks-decrypt"):
            decrypt_sdks = metafunc.config.getoption("--sdks-decrypt").split()
        elif metafunc.config.getoption("--sdks"):
            decrypt_sdks = metafunc.config.getoption("--sdks").split()
        else:
            decrypt_sdks = ["js", "go", "java"]
        metafunc.parametrize("decrypt_sdk", decrypt_sdks)
    if "container" in metafunc.fixturenames:
        if metafunc.config.getoption("--containers"):
            containers = metafunc.config.getoption("--containers").split()
        else:
            containers = ["nano", "ztdf"]
        metafunc.parametrize("container", containers)
    if "feature_flag" in metafunc.fixturenames:
        if metafunc.config.getoption("--feature-flags"):
            flags = metafunc.config.getoption("--feature-flags").split()
            feature_flags = set(["standard"] + flags)
        else:
            feature_flags = set(["standard"])
        metafunc.parametrize("feature_flag", feature_flags)


@pytest.fixture
def pt_file(tmp_dir: str, size) -> str:
    pt_file = f"{tmp_dir}test-plain-{size}.txt"
    length = (5 * 2**30) if size == "large" else 128
    with open(pt_file, "w") as f:
        for i in range(0, length, 16):
            f.write("{:15,d}\n".format(i))
    return pt_file


@pytest.fixture
def tmp_dir() -> str:
    dname = "tmp/"
    isExist = os.path.exists(dname)
    if not isExist:
        os.makedirs(dname)
    return dname


@pytest.fixture
def kas_public_keys(feature_flag: str) -> abac.PublicKey:
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

    if feature_flag == "cached_key":
        return load_cached_kas_keys()
    return load_local_kas_key()
