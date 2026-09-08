"""Render platform configuration and harness environment for an IdP provider.

Three modes:

* ``--base BASE --out OUT`` patches a full platform YAML: the provider's
  overlay (issuer, audience, DPoP enforcement, policy groups claim and
  extension, entity-resolution mode) is merged into BASE and written to OUT.
* ``--fragment OUT`` writes only the overlay keys, for callers that already
  have a config-generation step and merge with
  ``yq -i '. *= load("OUT")' opentdf.yaml``.
* ``--env`` prints ``export`` lines the xtest harness and SDK CLIs read to
  talk to this provider: client credentials, the token endpoint when the
  provider declares one, and the subject-condition selector/values the
  attribute fixtures use.

Usage: ``uv run python -m idp.platform_config <provider> ...``
"""

import argparse
import shlex
import sys
from pathlib import Path
from typing import Any

import yaml

from idp.provider import IdpProvider, load_provider


def _load_ready(provider_name: str) -> IdpProvider:
    resolved = load_provider(provider_name)
    if not resolved.ready:
        raise SystemExit(
            f"provider {provider_name!r} has unresolved environment secrets: "
            f"{', '.join(resolved.missing_secrets)}"
        )
    return resolved.provider


def overlay_fragment(provider: IdpProvider) -> dict[str, Any]:
    """The platform config keys a provider needs, and nothing else."""
    auth: dict[str, Any] = {
        "issuer": provider.issuer,
        "audience": provider.audience,
        "dpop": {"enforce": provider.platform_overlay.dpop_enforce},
    }
    policy: dict[str, Any] = {}
    if provider.platform_overlay.casbin_extension:
        policy["extension"] = provider.platform_overlay.casbin_extension
    if provider.platform_overlay.casbin_groups_claim:
        policy["groups_claim"] = provider.platform_overlay.casbin_groups_claim
    if policy:
        auth["policy"] = policy
    return {
        "server": {"auth": auth},
        "services": {"entityresolution": {"mode": provider.ers.mode}},
    }


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def render_overlay(provider_name: str, base_path: Path) -> dict[str, Any]:
    provider = _load_ready(provider_name)
    config: dict[str, Any] = yaml.safe_load(base_path.read_text()) or {}
    return _deep_merge(config, overlay_fragment(provider))


def harness_env(provider: IdpProvider) -> dict[str, str]:
    """Environment the xtest harness and SDK CLIs need for this provider.

    ``XT_SUBJECT_SELECTOR`` / ``XT_SUBJECT_VALUES`` are read by the shared
    subject-condition fixture (``fixtures/obligations.py``); ``CLIENTID`` /
    ``CLIENTSECRET`` and ``TOKENENDPOINT`` by the SDK CLI wrappers.
    """
    env = {
        "CLIENTID": provider.client_id,
        "CLIENTSECRET": provider.client_secret,
        "XT_SUBJECT_SELECTOR": provider.subject_condition.selector,
        "XT_SUBJECT_VALUES": ",".join(provider.subject_condition.values),
    }
    if provider.token_endpoint:
        env["TOKENENDPOINT"] = provider.token_endpoint
    return env


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render platform config / harness env for an IdP provider."
    )
    parser.add_argument("provider", help="provider name (idp/providers/<name>.yaml)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--fragment",
        type=Path,
        metavar="OUT",
        help="write only the overlay keys as YAML (merge with yq '. *= load(...)')",
    )
    mode.add_argument(
        "--env",
        action="store_true",
        help="print `export` lines for the harness and SDK CLIs",
    )
    parser.add_argument("--base", type=Path, help="base platform YAML to patch")
    parser.add_argument("--out", type=Path, help="output path for the rendered YAML")
    args = parser.parse_args(argv)

    if args.env:
        provider = _load_ready(args.provider)
        for key, value in harness_env(provider).items():
            print(f"export {key}={shlex.quote(value)}")
        return 0

    if args.fragment is not None:
        provider = _load_ready(args.provider)
        args.fragment.parent.mkdir(parents=True, exist_ok=True)
        args.fragment.write_text(
            yaml.safe_dump(overlay_fragment(provider), sort_keys=False)
        )
        print(f"wrote {args.fragment} (issuer={provider.issuer})", file=sys.stderr)
        return 0

    if args.base is None or args.out is None:
        parser.error(
            "--base and --out are required unless --fragment or --env is given"
        )
    config = render_overlay(args.provider, args.base)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(yaml.safe_dump(config, sort_keys=False))
    auth = config["server"]["auth"]
    print(f"wrote {args.out} (issuer={auth['issuer']}, audience={auth['audience']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
