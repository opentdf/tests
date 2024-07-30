import os
import pytest


def pytest_addoption(parser):
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


def pytest_generate_tests(metafunc):
    if "large" in metafunc.fixturenames:
        metafunc.parametrize("large", [metafunc.config.getoption("large")])
    if "encrypt_sdk" in metafunc.fixturenames:
        if metafunc.config.getoption("--sdks-encrypt"):
            encrypt_sdks = metafunc.config.getoption("--sdks-encrypt").split()
        elif metafunc.config.getoption("--sdks"):
            encrypt_sdks = metafunc.config.getoption("--sdks").split()
        else:
            encrypt_sdks = ["sdk/js/cli/cli.sh", "sdk/go/cli.sh", "sdk/java/cli.sh"]
        metafunc.parametrize("encrypt_sdk", encrypt_sdks)
    if "decrypt_sdk" in metafunc.fixturenames:
        if metafunc.config.getoption("--sdks-decrypt"):
            decrypt_sdks = metafunc.config.getoption("--sdks-decrypt").split()
        elif metafunc.config.getoption("--sdks"):
            decrypt_sdks = metafunc.config.getoption("--sdks").split()
        else:
            decrypt_sdks = ["sdk/js/cli/cli.sh", "sdk/go/cli.sh", "sdk/java/cli.sh"]
        metafunc.parametrize("decrypt_sdk", decrypt_sdks)


@pytest.fixture
def pt_file(tmp_dir, large):
    pt_file = f"{tmp_dir}test-plain-{'large' if large else 'small'}.txt"
    length = (5 * 2**30) if large else 128
    with open(pt_file, "w") as f:
        for i in range(0, length, 16):
            f.write("{:15,d}\n".format(i))
    return pt_file


@pytest.fixture
def tmp_dir():
    dname = "tmp/"
    isExist = os.path.exists(dname)
    if not isExist:
        os.makedirs(dname)
    return dname
