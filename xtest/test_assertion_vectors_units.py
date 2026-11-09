"""Offline checks of the DSPX-5520 shared assertion conformance vectors.

No platform, no SDK, no subprocess. The Go, Java, and JS SDKs vendor
``vectors/assertions-phase0.json`` byte-for-byte and run every vector, so a
wrong expectation here becomes a wrong requirement in three repositories.
This module checks that the committed file is exactly what the generator
produces, that it carries the spec Section 4.4 anchor hashes, that its shape
is what the SDK harnesses expect, and that the reference reader in
``assertions.py`` gives every vector its expected result, run the way an SDK
harness runs it.
"""

import base64
import json
import re
from typing import Any

import pytest
import rfc8785

import assertions
from vectors import generate_assertion_vectors as generator

RAW = generator.OUTPUT.read_bytes()
DOC: dict[str, Any] = json.loads(RAW)
VECTORS: list[dict[str, Any]] = DOC["vectors"]

#: Spec 4.4 worked examples: the vector that must carry each anchor hash.
ANCHORS = {
    "assertion-worked-example-string-value": (
        "456d05d6a3f48a14aeee20c8d5f0429d07e5be3f1695fcec2dbc755cd9d64495"
    ),
    "assertion-worked-example-unmodelled-extension": (
        "a7347ff1c718c0ee7e88558de64389d5e7194990eb6c78662d0bcd9cfb19c7ba"
    ),
    "assertion-worked-example-acp240-object-value": (
        "46853cb52912fd76f3ff90df3936158ee220b8e5973c5d02bb6e50f468596fba"
    ),
}


def test_committed_vectors_are_generated():
    assert RAW == generator.render(generator.build()), (
        "vectors/assertions-phase0.json is stale or hand-edited; regenerate with "
        "`uv run python -m vectors.generate_assertion_vectors` from xtest/"
    )


def test_spec_anchor_hashes():
    by_name = {v["name"]: v for v in VECTORS}
    for name, anchor in ANCHORS.items():
        assert by_name[name]["expect"] == {"assertionHash": anchor}, name


def test_rfc8785_samples():
    """The JCS library reproduces the RFC 8785 Section 3.2 examples."""
    sample = assertions.loads_strict(generator.RFC8785_SAMPLE)
    assert rfc8785.dumps(sample).decode() == generator.RFC8785_SAMPLE_CANONICAL
    canonical = rfc8785.dumps(assertions.loads_strict(generator.RFC8785_SORT_SAMPLE))
    assert list(json.loads(canonical)) == generator.RFC8785_SORTED_NAMES


@pytest.mark.parametrize(
    "name, modelled, expected",
    [
        ("ID", "id", True),
        ("iD", "id", True),
        ("id", "id", False),
        ("\u017fcope", "scope", True),
        ("appliesTo\u017ftate", "appliesToState", True),
        ("\u0131d", "id", False),
        ("\u0130d", "id", False),
        ("\ufb06atement", "statement", False),
        ("ids", "id", False),
    ],
)
def test_case_variant_rule(name: str, modelled: str, expected: bool):
    assert assertions.is_case_variant(name, modelled) is expected


KINDS = {
    "assertion": ({"assertionHash"}, {"reason"}),
    "manifest": ({"ok"}, {"reason"}),
    "binding": ({"bindingForm"}, {"reason"}),
    "verify": ({"ok"}, {"reason"}),
}


def test_vector_file_shape():
    assert RAW.isascii() and RAW.endswith(b"}\n")
    assert DOC["format"] == "opentdf-assertion-vectors/1"
    assert DOC["source"] == (
        "opentdf/tests xtest/vectors/assertions-phase0.json (DSPX-5520)"
    )
    assert list(DOC) == [
        "format",
        "source",
        "description",
        "modelledNames",
        "caseVariantExceptions",
        "keys",
        "vectors",
    ]
    for name, key in DOC["keys"].items():
        # The material reflects the key's form; alg may be deliberately bad.
        assert isinstance(key["alg"], str), name
        assert set(key) in ({"alg", "publicKeyPem"}, {"alg", "secretBase64"}), name
    names = [v["name"] for v in VECTORS]
    assert len(names) == len(set(names))
    for v in VECTORS:
        name = v["name"]
        assert re.fullmatch(r"[a-z0-9]+(-[a-zA-Z0-9]+)*", name), name
        assert name.startswith(f"{v['kind']}-"), name
        assert v["status"] in ("required", "proposed"), name
        assert v["note"] and "\n" not in v["note"], name
        assert ("input" in v) != ("inputBase64" in v), name
        fields = {"name", "kind", "status", "note", "expect"}
        fields.add("input" if "input" in v else "inputBase64")
        if v["kind"] == "verify":
            fields |= {"selectedKey", "keySource", "aggregateHashBase64", "legacy"}
            assert v["selectedKey"] in DOC["keys"], name
            assert v["keySource"] in ("configured", "payload"), name
            assert isinstance(v["legacy"], bool), name
            base64.b64decode(v["aggregateHashBase64"], validate=True)
        assert set(v) == fields, name
        success, failure = KINDS[v["kind"]]
        assert set(v["expect"]) in (success, failure), name
        if "reason" in v["expect"]:
            assert v["expect"]["reason"] in assertions.REASONS, name
        elif v["kind"] == "assertion":
            assert re.fullmatch(r"[0-9a-f]{64}", v["expect"]["assertionHash"]), name
        else:
            assert list(v["expect"].values()) in ([True], ["jws"]), name
        # Only the spec's Proposed statement typing is informational.
        if v["status"] == "proposed":
            assert v["expect"] == {"reason": "invalid-statement"}, name


def test_modelled_names_table():
    """The file's case-variant table is the reference reader's (spec 3.2)."""
    assert DOC["modelledNames"] == {
        level: list(names) for level, names in assertions.MODELLED_NAMES.items()
    }
    assert DOC["caseVariantExceptions"] == {
        level: list(names)
        for level, names in assertions.CASE_VARIANT_EXCEPTIONS.items()
    }


def _key(vector: dict[str, Any]) -> assertions.VerificationKey:
    """The selected key: configured keys go through key preparation."""
    spec = DOC["keys"][vector["selectedKey"]]
    secret = base64.b64decode(spec["secretBase64"]) if "secretBase64" in spec else None
    if vector["keySource"] == "payload":
        assert secret is not None
        return assertions.VerificationKey("HS256", secret)
    return assertions.configured_key(
        spec["alg"], public_key_pem=spec.get("publicKeyPem"), secret=secret
    )


def _input(vector: dict[str, Any]) -> bytes:
    if "input" in vector:
        return vector["input"].encode("utf-8")
    return base64.b64decode(vector["inputBase64"], validate=True)


def run_vector(vector: dict[str, Any]) -> dict[str, Any]:
    """What an SDK harness does with one vector, against the reference reader."""
    raw = _input(vector)
    try:
        match vector["kind"]:
            case "assertion":
                a = assertions.parse_assertion(raw)
                assertions.assertion_id(a)
                if vector["status"] == "proposed":
                    assertions.check_statement(a)
                return {"assertionHash": assertions.assertion_hash(a)}
            case "manifest":
                assertions.parse_manifest(raw)
                return {"ok": True}
            case "binding":
                return {
                    "bindingForm": assertions.binding_form(
                        assertions.parse_assertion(raw)
                    )
                }
            case "verify":
                key = _key(vector)
                assertions.verify_assertion_binding(
                    assertions.parse_assertion(raw),
                    key,
                    base64.b64decode(vector["aggregateHashBase64"]),
                    vector["legacy"],
                )
                return {"ok": True}
            case kind:
                raise AssertionError(f"unknown kind {kind!r}")
    except assertions.AssertionFailure as e:
        return {"reason": e.reason}


@pytest.mark.parametrize("vector", VECTORS, ids=[v["name"] for v in VECTORS])
def test_reference_reader(vector: dict[str, Any]):
    assert run_vector(vector) == vector["expect"]


@pytest.mark.parametrize(
    "vector",
    [v for v in VECTORS if v["kind"] in ("binding", "verify")],
    ids=lambda v: v["name"],
)
def test_binding_and_verify_inputs_pass_parsing(vector: dict[str, Any]):
    """Each binding and verify vector fails, if at all, only at its own step."""
    a = assertions.parse_assertion(_input(vector))
    assert assertions.assertion_id(a)
    if vector["kind"] == "verify" and vector["expect"].get("reason") not in (
        "invalid-binding",
        "unsupported-binding",
    ):
        assert assertions.binding_form(a) == "jws"
