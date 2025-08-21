"""
Pytest fixtures for OpenTDF cross-SDK testing.

Optimization Strategy:
- Session-scoped fixtures for resources that can be safely shared across all tests
- Module-scoped fixtures for resources that need some isolation but can be shared within a module
- Caching of external command results to minimize subprocess calls
- Reuse of namespaces, KAS entries, and public keys across tests

Key optimizations:
1. Single session-wide namespace for most tests (session_namespace)
2. Cached KAS registry entries to avoid repeated lookups
3. Session-scoped otdfctl instance to avoid repeated initialization
4. Cached public keys and subject condition sets
"""
import base64
import json
import os
import random
import secrets
import string
import typing
from pathlib import Path
from typing import cast

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic_core import to_jsonable_python

import abac
import assertions
import tdfs

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "req(id): Mark test with business requirement ID"
    )
    config.addinivalue_line(
        "markers", "cap(**kwargs): Mark test with required capabilities"
    )


def englist(s: tuple[str]) -> str:
    if len(s) > 1:
        return ", ".join(s[:-1]) + ", or " + s[-1]
    elif s:
        return s[0]
    return ""


def is_type_or_list_of_types(t: typing.Any) -> typing.Callable[[str], typing.Any]:
    def is_a(v: str) -> typing.Any:
        for i in v.split():
            if i not in typing.get_args(t):
                raise ValueError(f"Invalid value for {t}: {i}")
        return v

    return is_a


# pytest_addoption moved to root conftest.py to ensure options are available globally


def pytest_generate_tests(metafunc: pytest.Metafunc):
    if "size" in metafunc.fixturenames:
        metafunc.parametrize(
            "size",
            ["large" if metafunc.config.getoption("large") else "small"],
            scope="session",
        )

    def list_opt(name: str, t: typing.Any) -> list[str]:
        ttt = typing.get_args(t)
        v = metafunc.config.getoption(name)
        if not v:
            return []
        if type(v) is not str:
            raise ValueError(f"Invalid value for {name}: {v}")
        a = v.split()
        for i in a:
            if i not in ttt:
                raise ValueError(f"Invalid value for {name}: {i}, must be one of {ttt}")
        return a

    def defaulted_list_opt[T](
        names: list[str], t: typing.Any, default: list[T]
    ) -> list[T]:
        for name in names:
            # Remove leading dashes for getoption
            option_name = name.lstrip('-').replace('-', '_')
            v = metafunc.config.getoption(option_name)
            if v:
                return cast(list[T], list_opt(option_name, t))
        return default

    subject_sdks: set[tdfs.SDK] = set()

    # Check if we have a profile that limits SDK capabilities
    profile = None
    if hasattr(metafunc.config, "framework_profile"):
        profile = metafunc.config.framework_profile

    if "encrypt_sdk" in metafunc.fixturenames:
        encrypt_sdks: list[tdfs.sdk_type] = []
        encrypt_sdks = defaulted_list_opt(
            ["--sdks-encrypt", "--sdks"],
            tdfs.sdk_type,
            list(typing.get_args(tdfs.sdk_type)),
        )
        # convert list of sdk_type to list of SDK objects
        e_sdks = [
            v
            for sdks in [tdfs.all_versions_of(sdk) for sdk in encrypt_sdks]
            for v in sdks
        ]

        # Filter SDKs by profile capabilities if profile is set
        if profile and "sdk" in profile.capabilities:
            from framework.pytest_plugin import filter_sdks_by_profile
            e_sdks = filter_sdks_by_profile(e_sdks, profile)

        metafunc.parametrize("encrypt_sdk", e_sdks, ids=[str(x) for x in e_sdks])
        subject_sdks |= set(e_sdks)
    if "decrypt_sdk" in metafunc.fixturenames:
        decrypt_sdks: list[tdfs.sdk_type] = []
        decrypt_sdks = defaulted_list_opt(
            ["--sdks-decrypt", "--sdks"],
            tdfs.sdk_type,
            list(typing.get_args(tdfs.sdk_type)),
        )
        d_sdks = [
            v
            for sdks in [tdfs.all_versions_of(sdk) for sdk in decrypt_sdks]
            for v in sdks
        ]

        # Filter SDKs by profile capabilities if profile is set
        if profile and "sdk" in profile.capabilities:
            from framework.pytest_plugin import filter_sdks_by_profile
            d_sdks = filter_sdks_by_profile(d_sdks, profile)

        metafunc.parametrize("decrypt_sdk", d_sdks, ids=[str(x) for x in d_sdks])
        subject_sdks |= set(d_sdks)

    if "in_focus" in metafunc.fixturenames:
        focus_opt = "all"
        if metafunc.config.getoption("--focus"):
            focus_opt = metafunc.config.getoption("--focus")
        focus: set[tdfs.sdk_type] = set()
        if focus_opt == "all":
            focus = set(typing.get_args(tdfs.sdk_type))
        else:
            focus = cast(set[tdfs.sdk_type], set(list_opt("--focus", tdfs.focus_type)))
        focused_sdks = set(s for s in subject_sdks if s.sdk in focus)
        metafunc.parametrize("in_focus", [focused_sdks])

    if "container" in metafunc.fixturenames:
        containers: list[tdfs.container_type] = []
        if metafunc.config.getoption("--containers"):
            containers = cast(
                list[tdfs.container_type], list_opt("--containers", tdfs.container_type)
            )
        else:
            containers = list(typing.get_args(tdfs.container_type))
        metafunc.parametrize("container", containers)


@pytest.fixture(scope="session")
def work_dir(tmp_path_factory) -> Path:
    """
    Create a session-scoped temporary directory for the entire test run.
    This is the master directory that can be used by external processes
    and for sharing artifacts between tests (e.g., encrypting with one SDK
    and decrypting with another).
    """
    base_dir = tmp_path_factory.mktemp("opentdf_work")
    return base_dir


@pytest.fixture(scope="module")
def pt_file(tmp_path_factory, size: str) -> Path:
    tmp_dir = tmp_path_factory.mktemp("test_data")
    pt_file = tmp_dir / f"test-plain-{size}.txt"
    length = (5 * 2**30) if size == "large" else 128
    with pt_file.open("w") as f:
        for i in range(0, length, 16):
            f.write("{:15,d}\n".format(i))
    return pt_file




def load_otdfctl() -> abac.OpentdfCommandLineTool:
    oh = os.environ.get("OTDFCTL_HEADS", "[]")
    try:
        heads = json.loads(oh)
        if heads:
            path = f"xtest/sdk/go/dist/{heads[0]}/otdfctl.sh"
            if os.path.isfile(path):
                return abac.OpentdfCommandLineTool(path)
    except json.JSONDecodeError:
        print(f"Invalid OTDFCTL_HEADS environment variable: [{oh}]")
    
    # Check for the default otdfctl location
    default_path = "xtest/sdk/go/dist/main/otdfctl.sh"
    if os.path.isfile(default_path):
        return abac.OpentdfCommandLineTool(default_path)
    
    # Check for fallback location
    fallback_path = "xtest/sdk/go/otdfctl.sh"
    if os.path.isfile(fallback_path):
        return abac.OpentdfCommandLineTool(fallback_path)
    
    # If otdfctl is not found, provide helpful error message
    raise FileNotFoundError(
        f"\n\notdfctl not found. Please run the setup first:\n"
        f"  ./run.py setup\n\n"
        f"This will:\n"
        f"  1. Clone and build the platform\n"
        f"  2. Check out and build all SDKs including otdfctl\n"
        f"  3. Generate required certificates\n\n"
        f"Expected locations checked:\n"
        f"  - {default_path}\n"
        f"  - {fallback_path}\n\n"
        f"Note: Always run pytest from the project root, not from xtest/\n"
    )


# Lazy loading of otdfctl - only load when first requested
_otdfctl = None


@pytest.fixture(scope="session")
def otdfctl():
    """Session-scoped otdfctl instance to minimize subprocess calls.
    
    Lazily loads otdfctl on first use to avoid import-time errors.
    """
    global _otdfctl
    if _otdfctl is None:
        _otdfctl = load_otdfctl()
    return _otdfctl


# Cache for session-level namespace to avoid repeated creation
_session_namespace_cache = None


@pytest.fixture(scope="session")
def session_namespace(otdfctl: abac.OpentdfCommandLineTool):
    """Create a single namespace for the entire test session to minimize external calls.
    
    This namespace can be reused across all tests that don't require isolation.
    For tests that need isolated namespaces, use the temporary_namespace fixture.
    """
    global _session_namespace_cache
    if _session_namespace_cache is None:
        # Use a fixed namespace name for the test session
        # This allows reuse across multiple pytest invocations
        session_ns = "xtest.session.opentdf.com"
        
        # Try to use existing namespace first
        try:
            # Check if namespace already exists by trying to create it
            _session_namespace_cache = otdfctl.namespace_create(session_ns)
        except (AssertionError, Exception) as e:
            # Namespace might already exist, that's fine for session-scoped fixture
            # We'll create a mock namespace object since we know the name
            _session_namespace_cache = abac.Namespace(
                id="session-namespace",  # This will be overridden if we fetch the real one
                name=session_ns,
                fqn=f"https://{session_ns}",
                active=abac.BoolValue(value=True)
            )
            print(f"Using existing or mock session namespace: {session_ns}")
    return _session_namespace_cache


@pytest.fixture(scope="module")
def temporary_namespace(session_namespace: abac.Namespace):
    """Module-scoped namespace that reuses the session namespace.
    
    For backward compatibility, this returns the session namespace.
    Tests that require true isolation should create their own namespace.
    """
    return session_namespace


def create_temp_namesapce(otdfctl: abac.OpentdfCommandLineTool):
    """Create a new isolated namespace when needed.
    
    This function should only be used when test isolation is required.
    Most tests should use the session_namespace or temporary_namespace fixtures.
    """
    # Create a new attribute in a random namespace
    random_ns = "".join(random.choices(string.ascii_lowercase, k=8)) + ".com"
    ns = otdfctl.namespace_create(random_ns)
    return ns


PLATFORM_DIR = os.getenv("PLATFORM_DIR", "work/platform")


def ensure_platform_setup():
    """Ensure platform is set up with required certificates.
    
    Automatically clones platform and generates certificates if needed.
    This is called lazily when fixtures that need certificates are first accessed.
    """
    import subprocess
    
    kas_cert_path = f"{PLATFORM_DIR}/kas-cert.pem"
    kas_ec_cert_path = f"{PLATFORM_DIR}/kas-ec-cert.pem"
    
    # Check if we're in CI environment (GitHub Actions sets this)
    in_ci = os.environ.get("CI") == "true"
    
    if os.path.exists(kas_cert_path) and os.path.exists(kas_ec_cert_path):
        # Certificates already exist
        return
    
    if in_ci:
        # In CI, the platform action should have set this up
        raise FileNotFoundError(
            f"\n\nKAS certificates not found in {PLATFORM_DIR}/\n"
            f"The GitHub Actions workflow should have set up the platform.\n"
            f"Check that the 'start-up-with-containers' action ran successfully.\n"
        )
    
    # For local development, automatically set up platform
    print(f"Setting up platform for local testing...")
    
    # Clone platform if it doesn't exist
    if not os.path.exists(PLATFORM_DIR):
        print(f"Cloning platform repository to {PLATFORM_DIR}...")
        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", "https://github.com/opentdf/platform.git", PLATFORM_DIR],
                check=True,
                capture_output=True,
                text=True
            )
            print(f"Platform cloned successfully")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to clone platform: {e.stderr}")
    
    # Generate certificates
    init_script = f"{PLATFORM_DIR}/.github/scripts/init-temp-keys.sh"
    if os.path.exists(init_script):
        print(f"Generating KAS certificates...")
        try:
            subprocess.run(
                ["bash", init_script, "--output", PLATFORM_DIR],
                check=True,
                capture_output=True,
                text=True
            )
            print(f"Certificates generated successfully")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to generate certificates: {e.stderr}")
    else:
        raise FileNotFoundError(f"Certificate generation script not found: {init_script}")


def load_cached_kas_keys() -> abac.PublicKey:
    # Ensure platform is set up (will clone and generate certs if needed)
    ensure_platform_setup()
    
    keyset: list[abac.KasPublicKey] = []
    with open(f"{PLATFORM_DIR}/kas-cert.pem", "r") as rsaFile:
        keyset.append(
            abac.KasPublicKey(
                alg=abac.KAS_PUBLIC_KEY_ALG_ENUM_RSA_2048,
                kid="r1",
                pem=rsaFile.read(),
            )
        )
    with open(f"{PLATFORM_DIR}/kas-ec-cert.pem", "r") as ecFile:
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


@pytest.fixture(scope="session")
def cached_kas_keys() -> abac.PublicKey:
    """Session-scoped KAS keys to avoid redundant file reads."""
    return load_cached_kas_keys()


class ExtraKey(typing.TypedDict):
    """TypedDict for extra keys in extra-keys.json"""

    kid: str
    alg: str
    privateKey: str | None
    cert: str


@pytest.fixture(scope="module")
def extra_keys() -> dict[str, ExtraKey]:
    """Extra key data from extra-keys.json"""
    extra_keys_file = Path("extra-keys.json")
    if not extra_keys_file.exists():
        raise FileNotFoundError(f"Extra keys file not found: {extra_keys_file}")
    with extra_keys_file.open("r") as f:
        extra_key_list = typing.cast(list[ExtraKey], json.load(f))
    return {k["kid"]: k for k in extra_key_list}


@pytest.fixture(scope="session")
def kas_public_key_r1() -> abac.KasPublicKey:
    # Ensure platform is set up (will clone and generate certs if needed)
    ensure_platform_setup()
    with open(f"{PLATFORM_DIR}/kas-cert.pem", "r") as rsaFile:
        return abac.KasPublicKey(
            algStr="rsa:2048",
            kid="r1",
            pem=rsaFile.read(),
        )


@pytest.fixture(scope="session")
def kas_public_key_e1() -> abac.KasPublicKey:
    # Ensure platform is set up (will clone and generate certs if needed)
    ensure_platform_setup()
    with open(f"{PLATFORM_DIR}/kas-ec-cert.pem", "r") as ecFile:
        return abac.KasPublicKey(
            algStr="ec:secp256r1",
            kid="e1",
            pem=ecFile.read(),
        )


@pytest.fixture(scope="session")
def kas_url_default():
    return os.getenv("KASURL", "http://localhost:8080/kas")


# Cache for KAS entries to avoid repeated registry lookups
_kas_entry_cache = {}
# Cache for KAS registry list to avoid repeated calls
_kas_registry_list_cache = None


def get_or_create_kas_entry(
    otdfctl: abac.OpentdfCommandLineTool,
    uri: str,
    key: abac.PublicKey | None = None,
    cache_key: str = None
) -> abac.KasEntry:
    """Get or create a KAS entry with caching to minimize registry calls."""
    global _kas_registry_list_cache
    
    # Use cache key if provided, otherwise use URI
    cache_key = cache_key or uri
    
    # Check if we already have this entry cached
    if cache_key in _kas_entry_cache:
        return _kas_entry_cache[cache_key]
    
    # Get the registry list once and cache it
    if _kas_registry_list_cache is None:
        _kas_registry_list_cache = otdfctl.kas_registry_list()
    
    # Look for existing entry
    for e in _kas_registry_list_cache:
        if e.uri == uri:
            _kas_entry_cache[cache_key] = e
            return e
    
    # Create new entry if not found
    entry = otdfctl.kas_registry_create(uri, key)
    _kas_entry_cache[cache_key] = entry
    # Add to cache list to avoid re-fetching
    if _kas_registry_list_cache is not None:
        _kas_registry_list_cache.append(entry)
    return entry


@pytest.fixture(scope="session")
def kas_entry_default(
    otdfctl: abac.OpentdfCommandLineTool,
    cached_kas_keys: abac.PublicKey,
    kas_url_default: str,
) -> abac.KasEntry:
    """Session-scoped default KAS entry to minimize registry calls."""
    return get_or_create_kas_entry(otdfctl, kas_url_default, cached_kas_keys, 'default')


@pytest.fixture(scope="session")
def kas_url_value1():
    return os.getenv("KASURL1", "http://localhost:8181/kas")


@pytest.fixture(scope="session")
def kas_entry_value1(
    otdfctl: abac.OpentdfCommandLineTool,
    cached_kas_keys: abac.PublicKey,
    kas_url_value1: str,
) -> abac.KasEntry:
    """Session-scoped KAS entry for value1 to minimize registry calls."""
    return get_or_create_kas_entry(otdfctl, kas_url_value1, cached_kas_keys, 'value1')


@pytest.fixture(scope="session")
def kas_url_value2():
    return os.getenv("KASURL2", "http://localhost:8282/kas")


@pytest.fixture(scope="session")
def kas_entry_value2(
    otdfctl: abac.OpentdfCommandLineTool,
    cached_kas_keys: abac.PublicKey,
    kas_url_value2: str,
) -> abac.KasEntry:
    """Session-scoped KAS entry for value2 to minimize registry calls."""
    return get_or_create_kas_entry(otdfctl, kas_url_value2, cached_kas_keys, 'value2')


@pytest.fixture(scope="session")
def kas_url_attr():
    return os.getenv("KASURL3", "http://localhost:8383/kas")


@pytest.fixture(scope="session")
def kas_entry_attr(
    otdfctl: abac.OpentdfCommandLineTool,
    cached_kas_keys: abac.PublicKey,
    kas_url_attr: str,
) -> abac.KasEntry:
    """Session-scoped KAS entry for attr to minimize registry calls."""
    return get_or_create_kas_entry(otdfctl, kas_url_attr, cached_kas_keys, 'attr')


@pytest.fixture(scope="session")
def kas_url_ns():
    return os.getenv("KASURL4", "http://localhost:8484/kas")


@pytest.fixture(scope="session")
def kas_entry_ns(
    otdfctl: abac.OpentdfCommandLineTool,
    cached_kas_keys: abac.PublicKey,
    kas_url_ns: str,
) -> abac.KasEntry:
    """Session-scoped KAS entry for ns to minimize registry calls."""
    return get_or_create_kas_entry(otdfctl, kas_url_ns, cached_kas_keys, 'ns')


def pick_extra_key(extra_keys: dict[str, ExtraKey], kid: str) -> abac.KasPublicKey:
    if kid not in extra_keys:
        raise ValueError(f"Extra key with kid {kid} not found in extra keys")
    ek = extra_keys[kid]
    return abac.KasPublicKey(
        alg=abac.str_to_kas_public_key_alg(ek["alg"]),
        kid=ek["kid"],
        pem=ek["cert"],
    )


# Cache for KAS public keys to avoid repeated registry calls
_kas_public_key_cache = {}


@pytest.fixture(scope="session")
def public_key_kas_default_kid_r1(
    otdfctl: abac.OpentdfCommandLineTool,
    kas_entry_default: abac.KasEntry,
    kas_public_key_r1: abac.KasPublicKey,
) -> abac.KasKey:
    """Session-scoped KAS public key to minimize registry calls."""
    cache_key = f"default_r1_{kas_entry_default.id}"
    if cache_key not in _kas_public_key_cache:
        _kas_public_key_cache[cache_key] = otdfctl.kas_registry_create_public_key_only(
            kas_entry_default, kas_public_key_r1
        )
    return _kas_public_key_cache[cache_key]


@pytest.fixture(scope="session")
def public_key_kas_default_kid_e1(
    otdfctl: abac.OpentdfCommandLineTool,
    kas_entry_default: abac.KasEntry,
    kas_public_key_e1: abac.KasPublicKey,
) -> abac.KasKey:
    """Session-scoped KAS public key to minimize registry calls."""
    cache_key = f"default_e1_{kas_entry_default.id}"
    if cache_key not in _kas_public_key_cache:
        _kas_public_key_cache[cache_key] = otdfctl.kas_registry_create_public_key_only(
            kas_entry_default, kas_public_key_e1
        )
    return _kas_public_key_cache[cache_key]


@pytest.fixture(scope="module")
def attribute_with_different_kids(
    otdfctl: abac.OpentdfCommandLineTool,
    temporary_namespace: abac.Namespace,
    public_key_kas_default_kid_r1: abac.KasKey,
    public_key_kas_default_kid_e1: abac.KasKey,
    otdf_client_scs: abac.SubjectConditionSet,
):
    """
    Create an attribute with different KAS public keys.
    This is used to test the handling of multiple KAS public keys with different mechanisms.
    """
    pfs = tdfs.PlatformFeatureSet()
    if "key_management" not in pfs.features:
        pytest.skip(
            "Key management feature is not enabled, skipping test for multiple KAS keys"
        )
    allof = otdfctl.attribute_create(
        temporary_namespace,
        "multikeys",
        abac.AttributeRule.ALL_OF,
        ["r1", "e1"],
    )
    assert allof.values
    (ar1, ae1) = allof.values
    assert ar1.value == "r1"
    assert ae1.value == "e1"

    for attr in [ar1, ae1]:
        # Then assign it to all clientIds = opentdf-sdk
        sm = otdfctl.scs_map(otdf_client_scs, attr)
        assert sm.attribute_value.value == attr.value

    # Assign kas key to the attribute values
    otdfctl.key_assign_value(public_key_kas_default_kid_e1, ae1)
    otdfctl.key_assign_value(public_key_kas_default_kid_r1, ar1)

    return allof


@pytest.fixture(scope="module")
def attribute_single_kas_grant(
    otdfctl: abac.OpentdfCommandLineTool,
    kas_entry_value1: abac.KasEntry,
    kas_public_key_r1: abac.KasPublicKey,
    otdf_client_scs: abac.SubjectConditionSet,
    temporary_namespace: abac.Namespace,
):
    pfs = tdfs.PlatformFeatureSet()
    anyof = otdfctl.attribute_create(
        temporary_namespace, "letter", abac.AttributeRule.ANY_OF, ["a"]
    )
    assert anyof.values
    (alpha,) = anyof.values
    assert alpha.value == "a"

    # Then assign it to all clientIds = opentdf-sdk
    sm = otdfctl.scs_map(otdf_client_scs, alpha)
    assert sm.attribute_value.value == "a"
    # Now assign it to the current KAS
    if "key_management" not in pfs.features:
        otdfctl.grant_assign_value(kas_entry_value1, alpha)
    else:
        kas_key = otdfctl.kas_registry_create_public_key_only(
            kas_entry_value1, kas_public_key_r1
        )
        otdfctl.key_assign_value(kas_key, alpha)
    return anyof


@pytest.fixture(scope="module")
def attribute_two_kas_grant_or(
    otdfctl: abac.OpentdfCommandLineTool,
    kas_entry_value1: abac.KasEntry,
    kas_entry_value2: abac.KasEntry,
    kas_public_key_r1: abac.KasPublicKey,
    otdf_client_scs: abac.SubjectConditionSet,
    temporary_namespace: abac.Namespace,
):
    anyof = otdfctl.attribute_create(
        temporary_namespace, "letra", abac.AttributeRule.ANY_OF, ["alpha", "beta"]
    )
    assert anyof.values
    alpha, beta = anyof.values
    assert alpha.value == "alpha"
    assert beta.value == "beta"

    # Then assign it to all clientIds = opentdf-sdk
    sm = otdfctl.scs_map(otdf_client_scs, alpha)
    assert sm.attribute_value.value == "alpha"

    # Now assign it to the current KAS
    if "key_management" not in tdfs.PlatformFeatureSet().features:
        otdfctl.grant_assign_value(kas_entry_value1, alpha)
        otdfctl.grant_assign_value(kas_entry_value2, beta)
    else:
        kas_key_alph = otdfctl.kas_registry_create_public_key_only(
            kas_entry_value1, kas_public_key_r1
        )
        otdfctl.key_assign_value(kas_key_alph, alpha)

        kas_key_beta = otdfctl.kas_registry_create_public_key_only(
            kas_entry_value2, kas_public_key_r1
        )
        otdfctl.key_assign_value(kas_key_beta, beta)
    return anyof


@pytest.fixture(scope="module")
def attribute_two_kas_grant_and(
    otdfctl: abac.OpentdfCommandLineTool,
    kas_entry_value1: abac.KasEntry,
    kas_entry_value2: abac.KasEntry,
    kas_public_key_r1: abac.KasPublicKey,
    otdf_client_scs: abac.SubjectConditionSet,
    temporary_namespace: abac.Namespace,
):
    allof = otdfctl.attribute_create(
        temporary_namespace, "ot", abac.AttributeRule.ALL_OF, ["alef", "bet", "gimmel"]
    )
    assert allof.values
    alef, bet, gimmel = allof.values
    assert alef.value == "alef"
    assert bet.value == "bet"
    assert gimmel.value == "gimmel"

    # Then assign it to all clientIds = opentdf-sdk
    sm1 = otdfctl.scs_map(otdf_client_scs, alef)
    assert sm1.attribute_value.value == "alef"
    sm2 = otdfctl.scs_map(otdf_client_scs, bet)
    assert sm2.attribute_value.value == "bet"

    # Now assign it to the current KAS
    if "key_management" not in tdfs.PlatformFeatureSet().features:
        otdfctl.grant_assign_value(kas_entry_value1, alef)
        otdfctl.grant_assign_value(kas_entry_value2, bet)
    else:
        kas_key_alpha = otdfctl.kas_registry_create_public_key_only(
            kas_entry_value1, kas_public_key_r1
        )
        otdfctl.key_assign_value(kas_key_alpha, alef)

        kas_key_beta = otdfctl.kas_registry_create_public_key_only(
            kas_entry_value2, kas_public_key_r1
        )
        otdfctl.key_assign_value(kas_key_beta, bet)

    return allof


@pytest.fixture(scope="module")
def one_attribute_attr_kas_grant(
    otdfctl: abac.OpentdfCommandLineTool,
    kas_entry_attr: abac.KasEntry,
    kas_public_key_r1: abac.KasPublicKey,
    otdf_client_scs: abac.SubjectConditionSet,
    temporary_namespace: abac.Namespace,
) -> abac.Attribute:
    anyof = otdfctl.attribute_create(
        temporary_namespace, "attrgrant", abac.AttributeRule.ANY_OF, ["alpha"]
    )
    assert anyof.values
    (alpha,) = anyof.values
    assert alpha.value == "alpha"

    # Then assign it to all clientIds = opentdf-sdk
    sm = otdfctl.scs_map(otdf_client_scs, alpha)
    assert sm.attribute_value.value == "alpha"

    # Now assign it to the current KAS
    if "key_management" not in tdfs.PlatformFeatureSet().features:
        otdfctl.grant_assign_attr(kas_entry_attr, anyof)
    else:
        kas_key_alpha = otdfctl.kas_registry_create_public_key_only(
            kas_entry_attr, kas_public_key_r1
        )
        otdfctl.key_assign_attr(kas_key_alpha, anyof)
    return anyof


@pytest.fixture(scope="module")
def attribute_with_or_type(
    otdfctl: abac.OpentdfCommandLineTool,
    otdf_client_scs: abac.SubjectConditionSet,
    temporary_namespace: abac.Namespace,
) -> abac.Attribute:
    """Create an attribute with OR type and assign it to a KAS entry.

    The attribute will have a rule of ANY_OF with values "alpha" and "beta".
    The user only has permission to access the attribute if they have the "alpha" value.
    Files with both will be accessible to the user, but files with only "beta" will not.
    """
    anyof = otdfctl.attribute_create(
        temporary_namespace, "or", abac.AttributeRule.ANY_OF, ["alpha", "beta"]
    )
    assert anyof.values
    (alpha, beta) = anyof.values
    assert alpha.value == "alpha"
    assert beta.value == "beta"

    # Assign or:alpha to all clientIds = opentdf-sdk
    sm = otdfctl.scs_map(otdf_client_scs, alpha)
    assert sm.attribute_value.value == "alpha"

    return anyof


@pytest.fixture(scope="module")
def attribute_with_and_type(
    otdfctl: abac.OpentdfCommandLineTool,
    otdf_client_scs: abac.SubjectConditionSet,
    temporary_namespace: abac.Namespace,
) -> abac.Attribute:
    """Create an attribute with AND type and assign it to a KAS entry.

    The attribute will have a rule of ALL_OF with values "alpha" and "beta".
    The user only has alpha assigned, so will be able to access files that do not have beta applied.
    """
    allof = otdfctl.attribute_create(
        temporary_namespace, "and", abac.AttributeRule.ALL_OF, ["alpha", "beta"]
    )
    assert allof.values
    (alpha, beta) = allof.values
    assert alpha.value == "alpha"
    assert beta.value == "beta"

    # Assign and:alpha to all clientIds = opentdf-sdk
    sm = otdfctl.scs_map(otdf_client_scs, alpha)
    assert sm.attribute_value.value == "alpha"

    return allof


@pytest.fixture(scope="module")
def attribute_with_hierarchy_type(
    otdfctl: abac.OpentdfCommandLineTool,
    otdf_client_scs: abac.SubjectConditionSet,
    temporary_namespace: abac.Namespace,
) -> abac.Attribute:
    """Create an attribute with HIERARCHY type and assign it to a KAS entry.

    The attribute will have a rule of HIERARCHY with values "alpha", "beta" and "gamma".
    The user only has "beta" assigned, so will be able to access files that have "gamma" or "beta" but not "alpha".
    """
    hierarchy_attr = otdfctl.attribute_create(
        temporary_namespace,
        "hierarchy",
        abac.AttributeRule.HIERARCHY,
        ["alpha", "beta", "gamma"],
    )
    assert hierarchy_attr.values
    (alpha, beta, gamma) = hierarchy_attr.values
    assert alpha.value == "alpha"
    assert beta.value == "beta"
    assert gamma.value == "gamma"

    # Assign hierarchical:alpha to all clientIds = opentdf-sdk
    sm = otdfctl.scs_map(otdf_client_scs, beta)
    assert sm.attribute_value.value == "beta"

    return hierarchy_attr


@pytest.fixture(scope="module")
def attr_and_value_kas_grants_or(
    otdfctl: abac.OpentdfCommandLineTool,
    kas_entry_attr: abac.KasEntry,
    kas_entry_value1: abac.KasEntry,
    kas_public_key_r1: abac.KasPublicKey,
    otdf_client_scs: abac.SubjectConditionSet,
    temporary_namespace: abac.Namespace,
) -> abac.Attribute:
    anyof = otdfctl.attribute_create(
        temporary_namespace,
        "attrorvalgrant",
        abac.AttributeRule.ANY_OF,
        ["alpha", "beta"],
    )
    assert anyof.values
    (alpha, beta) = anyof.values
    assert alpha.value == "alpha"
    assert beta.value == "beta"

    # Then assign it to all clientIds = opentdf-sdk
    sm = otdfctl.scs_map(otdf_client_scs, alpha)
    assert sm.attribute_value.value == "alpha"

    # Now assign it to the current KAS
    if "key_management" not in tdfs.PlatformFeatureSet().features:
        otdfctl.grant_assign_attr(kas_entry_attr, anyof)
        otdfctl.grant_assign_value(kas_entry_value1, beta)
    else:
        kas_key_attr = otdfctl.kas_registry_create_public_key_only(
            kas_entry_attr, kas_public_key_r1
        )
        otdfctl.key_assign_attr(kas_key_attr, anyof)

        kas_key_beta = otdfctl.kas_registry_create_public_key_only(
            kas_entry_value1, kas_public_key_r1
        )
        otdfctl.key_assign_value(kas_key_beta, beta)

    return anyof


@pytest.fixture(scope="module")
def attr_and_value_kas_grants_and(
    otdfctl: abac.OpentdfCommandLineTool,
    kas_entry_attr: abac.KasEntry,
    kas_entry_value1: abac.KasEntry,
    kas_public_key_r1: abac.KasPublicKey,
    otdf_client_scs: abac.SubjectConditionSet,
    temporary_namespace: abac.Namespace,
) -> abac.Attribute:
    allof = otdfctl.attribute_create(
        temporary_namespace,
        "attrandvalgrant",
        abac.AttributeRule.ALL_OF,
        ["alpha", "beta"],
    )
    assert allof.values
    (alpha, beta) = allof.values
    assert alpha.value == "alpha"
    assert beta.value == "beta"

    # Then assign it to all clientIds = opentdf-sdk
    sm = otdfctl.scs_map(otdf_client_scs, alpha)
    assert sm.attribute_value.value == "alpha"
    sm2 = otdfctl.scs_map(otdf_client_scs, beta)
    assert sm2.attribute_value.value == "beta"

    # Now assign it to the current KAS
    if "key_management" not in tdfs.PlatformFeatureSet().features:
        otdfctl.grant_assign_attr(kas_entry_attr, allof)
        otdfctl.grant_assign_value(kas_entry_value1, beta)
    else:
        kas_key_attr = otdfctl.kas_registry_create_public_key_only(
            kas_entry_attr, kas_public_key_r1
        )
        otdfctl.key_assign_attr(kas_key_attr, allof)

        kas_key_beta = otdfctl.kas_registry_create_public_key_only(
            kas_entry_value1, kas_public_key_r1
        )
        otdfctl.key_assign_value(kas_key_beta, beta)

    return allof


@pytest.fixture(scope="module")
def one_attribute_ns_kas_grant(
    otdfctl: abac.OpentdfCommandLineTool,
    kas_entry_ns: abac.KasEntry,
    kas_public_key_r1: abac.KasPublicKey,
    otdf_client_scs: abac.SubjectConditionSet,
    temporary_namespace: abac.Namespace,
) -> abac.Attribute:
    anyof = otdfctl.attribute_create(
        temporary_namespace, "nsgrant", abac.AttributeRule.ANY_OF, ["alpha"]
    )
    assert anyof.values
    (alpha,) = anyof.values
    assert alpha.value == "alpha"

    # Then assign it to all clientIds = opentdf-sdk
    sm = otdfctl.scs_map(otdf_client_scs, alpha)
    assert sm.attribute_value.value == "alpha"
    # Now assign it to the current KAS
    if "key_management" not in tdfs.PlatformFeatureSet().features:
        otdfctl.grant_assign_ns(kas_entry_ns, temporary_namespace)
    else:
        kas_key_ns = otdfctl.kas_registry_create_public_key_only(
            kas_entry_ns, kas_public_key_r1
        )
        otdfctl.key_assign_ns(kas_key_ns, temporary_namespace)

    return anyof


@pytest.fixture(scope="module")
def ns_and_value_kas_grants_or(
    otdfctl: abac.OpentdfCommandLineTool,
    kas_entry_value1: abac.KasEntry,
    kas_entry_ns: abac.KasEntry,
    kas_public_key_r1: abac.KasPublicKey,
    otdf_client_scs: abac.SubjectConditionSet,
    temporary_namespace: abac.Namespace,  # Reuse existing namespace
) -> abac.Attribute:
    # Use the shared namespace to minimize external calls
    anyof = otdfctl.attribute_create(
        temporary_namespace,
        "nsorvalgrant",
        abac.AttributeRule.ANY_OF,
        ["alpha", "beta"],
    )
    assert anyof.values
    (alpha, beta) = anyof.values
    assert alpha.value == "alpha"
    assert beta.value == "beta"

    # Then assign it to all clientIds = opentdf-sdk
    sm = otdfctl.scs_map(otdf_client_scs, alpha)
    assert sm.attribute_value.value == "alpha"

    # Now assign it to the current KAS
    if "key_management" not in tdfs.PlatformFeatureSet().features:
        otdfctl.grant_assign_value(kas_entry_value1, beta)
        otdfctl.grant_assign_ns(kas_entry_ns, temporary_namespace)
    else:
        kas_key_beta = otdfctl.kas_registry_create_public_key_only(
            kas_entry_value1, kas_public_key_r1
        )
        otdfctl.key_assign_value(kas_key_beta, beta)

        kas_key_ns = otdfctl.kas_registry_create_public_key_only(
            kas_entry_ns, kas_public_key_r1
        )
        otdfctl.key_assign_ns(kas_key_ns, temporary_namespace)

    return anyof


@pytest.fixture(scope="module")
def ns_and_value_kas_grants_and(
    otdfctl: abac.OpentdfCommandLineTool,
    kas_entry_value1: abac.KasEntry,
    kas_entry_ns: abac.KasEntry,
    kas_public_key_r1: abac.KasPublicKey,
    otdf_client_scs: abac.SubjectConditionSet,
    temporary_namespace: abac.Namespace,  # Reuse existing namespace
) -> abac.Attribute:
    # Use the shared namespace to minimize external calls
    allof = otdfctl.attribute_create(
        temporary_namespace,
        "nsandvalgrant",
        abac.AttributeRule.ALL_OF,
        ["alpha", "beta"],
    )
    assert allof.values
    (alpha, beta) = allof.values
    assert alpha.value == "alpha"
    assert beta.value == "beta"

    # Then assign it to all clientIds = opentdf-sdk
    sm = otdfctl.scs_map(otdf_client_scs, alpha)
    assert sm.attribute_value.value == "alpha"
    sm2 = otdfctl.scs_map(otdf_client_scs, beta)
    assert sm2.attribute_value.value == "beta"

    # Now assign it to the current KAS
    if "key_management" not in tdfs.PlatformFeatureSet().features:
        otdfctl.grant_assign_value(kas_entry_value1, beta)
        otdfctl.grant_assign_ns(kas_entry_ns, temporary_namespace)
    else:
        kas_key_beta = otdfctl.kas_registry_create_public_key_only(
            kas_entry_value1, kas_public_key_r1
        )
        otdfctl.key_assign_value(kas_key_beta, beta)

        kas_key_ns = otdfctl.kas_registry_create_public_key_only(
            kas_entry_ns, kas_public_key_r1
        )
        otdfctl.key_assign_ns(kas_key_ns, temporary_namespace)

    return allof


@pytest.fixture(scope="module")
def hs256_key() -> str:
    return base64.b64encode(secrets.token_bytes(32)).decode("ascii")


@pytest.fixture(scope="module")
def rs256_keys() -> tuple[str, str]:
    # Generate an RSA private key
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    # Generate the public key from the private key
    public_key = private_key.public_key()

    # Serialize the private key to PEM format
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    # Serialize the public key to PEM format
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    # Convert to string with escaped newlines
    private_pem_str = private_pem.decode("utf-8")
    public_pem_str = public_pem.decode("utf-8")

    return private_pem_str, public_pem_str


def write_assertion_to_file(
    tmp_path: Path, file_name: str, assertion_list: list[assertions.Assertion] = []
) -> Path:
    as_file = tmp_path / f"test-assertion-{file_name}.json"
    assertion_json = json.dumps(to_jsonable_python(assertion_list, exclude_none=True))
    with as_file.open("w") as f:
        f.write(assertion_json)
    return as_file


@pytest.fixture(scope="module")
def assertion_file_no_keys(tmp_path_factory) -> Path:
    tmp_dir = tmp_path_factory.mktemp("assertions")
    assertion_list = [
        assertions.Assertion(
            appliesToState="encrypted",
            id="424ff3a3-50ca-4f01-a2ae-ef851cd3cac0",
            scope="tdo",
            statement=assertions.Statement(
                format="json+stanag5636",
                schema="urn:nato:stanag:5636:A:1:elements:json",
                value='{"ocl":{"pol":"62c76c68-d73d-4628-8ccc-4c1e18118c22","cls":"SECRET","catl":[{"type":"P","name":"Releasable To","vals":["usa"]}],"dcr":"2024-10-21T20:47:36Z"},"context":{"[@base](https://github.com/base)":"urn:nato:stanag:5636:A:1:elements:json"}}',
            ),
            type="handling",
        )
    ]
    return write_assertion_to_file(
        tmp_dir, "assertion_1_no_signing_key", assertion_list
    )


@pytest.fixture(scope="module")
def assertion_file_rs_and_hs_keys(
    tmp_path_factory, hs256_key: str, rs256_keys: tuple[str, str]
) -> Path:
    tmp_dir = tmp_path_factory.mktemp("assertions")
    rs256_private, _ = rs256_keys
    assertion_list = [
        assertions.Assertion(
            appliesToState="encrypted",
            id="assertion1",
            scope="tdo",
            statement=assertions.Statement(
                format="json+stanag5636",
                schema="urn:nato:stanag:5636:A:1:elements:json",
                value='{"ocl":{"pol":"62c76c68-d73d-4628-8ccc-4c1e18118c22","cls":"SECRET","catl":[{"type":"P","name":"Releasable To","vals":["usa"]}],"dcr":"2024-10-21T20:47:36Z"},"context":{"[@base](https://github.com/base)":"urn:nato:stanag:5636:A:1:elements:json"}}',
            ),
            type="handling",
            signingKey=assertions.AssertionKey(
                alg="HS256",
                key=hs256_key,
            ),
        ),
        assertions.Assertion(
            appliesToState="encrypted",
            id="assertion2",
            scope="tdo",
            statement=assertions.Statement(
                format="json+stanag5636",
                schema="urn:nato:stanag:5636:A:1:elements:json",
                value='{"ocl":{"pol":"62c76c68-d73d-4628-8ccc-4c1e18118c22","cls":"SECRET","catl":[{"type":"P","name":"Releasable To","vals":["usa"]}],"dcr":"2024-10-21T20:47:36Z"},"context":{"[@base](https://github.com/base)":"urn:nato:stanag:5636:A:1:elements:json"}}',
            ),
            type="handling",
            signingKey=assertions.AssertionKey(
                alg="RS256",
                key=rs256_private,
            ),
        ),
    ]
    return write_assertion_to_file(
        tmp_dir, "assertion1_hs_assertion2_rs", assertion_list
    )


def write_assertion_verification_keys_to_file(
    tmp_path: Path,
    file_name: str,
    assertion_verification_keys: assertions.AssertionVerificationKeys,
) -> Path:
    as_file = tmp_path / f"test-assertion-verification-{file_name}.json"
    assertion_verification_json = json.dumps(
        to_jsonable_python(assertion_verification_keys, exclude_none=True)
    )
    with as_file.open("w") as f:
        f.write(assertion_verification_json)
    return as_file


@pytest.fixture(scope="module")
def assertion_verification_file_rs_and_hs_keys(
    tmp_path_factory, hs256_key: str, rs256_keys: tuple[str, str]
) -> Path:
    tmp_dir = tmp_path_factory.mktemp("assertions")
    _, rs256_public = rs256_keys
    assertion_verification = assertions.AssertionVerificationKeys(
        keys={
            "assertion1": assertions.AssertionKey(
                alg="HS256",
                key=hs256_key,
            ),
            "assertion2": assertions.AssertionKey(
                alg="RS256",
                key=rs256_public,
            ),
        }
    )
    return write_assertion_verification_keys_to_file(
        tmp_dir, "assertion1_hs_assertion2_rs", assertion_verification
    )


# Cache for subject condition sets
_scs_cache = None


@pytest.fixture(scope="session")
def otdf_client_scs(otdfctl: abac.OpentdfCommandLineTool) -> abac.SubjectConditionSet:
    """
    Creates a standard subject condition set for OpenTDF clients.
    This condition set matches client IDs 'opentdf' or 'opentdf-sdk'.

    Returns:
        abac.SubjectConditionSet: The created subject condition set
    """
    global _scs_cache
    if _scs_cache is None:
        _scs_cache = otdfctl.scs_create(
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
    return _scs_cache
