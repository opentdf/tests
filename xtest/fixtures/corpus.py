"""Fixtures that load the corpus KAS keys and attributes into km1/km2."""

import pytest

import abac
import corpus_kas as ck
import tdfs
from otdfctl import OpentdfCommandLineTool


@pytest.fixture(scope="module")
def corpus_kas(
    otdfctl: OpentdfCommandLineTool,
    kas_entry_km1: abac.KasEntry,
    kas_entry_km2: abac.KasEntry,
    otdf_client_scs: abac.SubjectConditionSet,
    root_key: str,
) -> dict[str, abac.KasKey]:
    """Import the corpus keys and create the corpus attributes; returns keys by kid."""
    tdfs.get_platform_features().skip_if_unsupported("key_management")
    keys = ck.ensure_corpus_keys(otdfctl, kas_entry_km1, kas_entry_km2, root_key)
    ck.ensure_corpus_attributes(otdfctl, otdf_client_scs, keys)
    return keys
