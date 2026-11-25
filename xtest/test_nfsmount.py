"""An SDK CLI decrypts a TDF read through the NFS mount (DSPX-5543).

Full-file mode, so every byte is there: the CLI sees an ordinary local file.
"""

import filecmp
from pathlib import Path

import pytest

import rangeserve
import tdfs
from abac import Attribute
from audit_logs import AuditLogAsserter
from fixtures.encryption import EncryptFactory
from fixtures.nfs_mount import Mounter

pytestmark = pytest.mark.core


def test_decrypt_through_nfs_mount(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    pt_file: Path,
    in_focus: set[tdfs.SDK],
    attribute_default_rsa: Attribute,
    encrypted_tdf: EncryptFactory,
    nfs_mount: Mounter,
    audit_logs: AuditLogAsserter,
):
    if encrypt_sdk != decrypt_sdk:
        pytest.skip("the mount is a decrypt-side concern; one cell per SDK")
    if decrypt_sdk not in in_focus:
        pytest.skip("Not in focus")
    ct_file = encrypted_tdf(encrypt_sdk, attr_values=attribute_default_rsa.value_fqns)
    manifest = tdfs.manifest(ct_file)
    kao = manifest.encryptionInformation.keyAccess[0]
    path, log = nfs_mount(rangeserve.FullFile(ct_file))
    rt_file = encrypted_tdf.rt_file(ct_file, decrypt_sdk, variant="nfs")
    mark = audit_logs.mark("before_decrypt")
    decrypt_sdk.decrypt(path, rt_file, "ztdf")
    audit_logs.assert_rewrap_success(
        policy_uuid=manifest.encryptionInformation.policy_object.uuid,
        key_id=kao.kid,
        since_mark=mark,
    )
    assert filecmp.cmp(pt_file, rt_file)
    assert any(r.status == 206 for r in log), f"no reads through the mount: {log}"
