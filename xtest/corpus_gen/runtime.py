"""Shared generator plumbing: paths, writer commands, env and platform setup.

Only setup_platform() talks to the platform.
"""

import os
from pathlib import Path

import abac
import corpus_kas
from corpus_gen.variants import KAS_URL
from otdfctl import OpentdfCommandLineTool

XTEST = Path(__file__).resolve().parent.parent
KM1 = KAS_URL["km1"]
KM2 = KAS_URL["km2"]

CLI = {
    "go": "sdk/go/dist/main/cli.sh",
    "java": "sdk/java/dist/main/cli.sh",
    "js": "sdk/js/dist/main/cli.sh",
}


class PathEscapeError(ValueError):
    """A path read from a file or subprocess lies outside its expected root."""


def tmp_root() -> Path:
    """XT_TMP_DIR (relative values are under xtest/), else xtest/tmp."""
    default = str(XTEST / "tmp")  # NOSONAR: xtest's own git-ignored scratch dir
    return XTEST / os.environ.get("XT_TMP_DIR", default)


def scratch_dir() -> Path:
    """Generator scratch: <tmp_root>/corpus_gen."""
    return (tmp_root() / "corpus_gen").resolve()


def inside(root: Path, path: str | Path, what: str = "path") -> Path:
    """The resolved path, which must lie within root; else PathEscapeError."""
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise PathEscapeError(f"{what} {str(path)!r} escapes {root}")
    return resolved


def writer_cmd(sdk: str) -> list[str]:
    """The writer command for an xtest SDK name, run from xtest/."""
    if sdk == "go":
        return ["go", "-C", "corpus_gen/writers/go", "run", "."]
    if sdk == "java":
        home = os.environ.get("JAVA_HOME")
        java = str(Path(home) / "bin" / "java") if home else "java"
        return [
            java,
            "-cp",
            "sdk/java/dist/main/cmdline.jar",
            "corpus_gen/writers/java/Writer.java",
        ]
    if sdk == "js":
        return ["node", "corpus_gen/writers/js/writer.mjs"]
    raise ValueError(f"no writer for {sdk!r}")


def load_env() -> dict[str, str]:
    """The process env plus test.env defaults (CLIENTID, PLATFORMURL, ...)."""
    env = dict(os.environ)
    for line in (XTEST / "test.env").read_text().splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        k, v = line.split("=", 1)
        env.setdefault(k, os.path.expandvars(v.strip()))
        os.environ.setdefault(k, env[k])
    return env


def _client_scs(otdfctl: OpentdfCommandLineTool) -> abac.SubjectConditionSet:
    # The condition set fixtures/obligations.py:otdf_client_scs creates.
    return otdfctl.scs_create(
        [
            abac.SubjectSet(
                condition_groups=[
                    abac.ConditionGroup(
                        boolean_operator=abac.ConditionBooleanTypeEnum.OR,
                        conditions=[
                            abac.Condition(
                                subject_external_selector_value=".clientId",
                                operator=abac.SubjectMappingOperatorEnum.IN,
                                subject_external_values=[
                                    "opentdf",
                                    "opentdf-sdk",
                                    "opentdf-dpop",
                                ],
                            )
                        ],
                    )
                ]
            )
        ]
    )


def setup_platform(attributes: bool = True) -> None:
    """Import the corpus keys into km1/km2 and, optionally, the corpus attributes."""
    otdfctl = OpentdfCommandLineTool("sdk/go/dist/main/otdfctl.sh")
    km1 = otdfctl.kas_registry_create_if_not_present(KM1)
    km2 = otdfctl.kas_registry_create_if_not_present(KM2)
    keys = corpus_kas.ensure_corpus_keys(otdfctl, km1, km2, os.environ["OT_ROOT_KEY"])
    if attributes:
        corpus_kas.ensure_corpus_attributes(otdfctl, _client_scs(otdfctl), keys)
