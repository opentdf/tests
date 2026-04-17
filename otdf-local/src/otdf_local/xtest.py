"""XTest orchestration commands for local replay and CI."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Annotated, Literal

import typer
from pydantic import BaseModel, Field, ValidationError

from otdf_local.ci import _emit_github_output
from otdf_local.config.ports import Ports
from otdf_local.config.settings import Settings, get_settings
from otdf_local.health.waits import WaitTimeoutError, wait_for_health, wait_for_port
from otdf_local.services import get_docker_service, get_kas_manager, get_platform_service, get_provisioner
from otdf_local.utils.console import print_error, print_info, print_success, print_warning, status_spinner
from otdf_local.utils.yaml import dump_yaml, get_nested, load_yaml, save_yaml

xtest_app = typer.Typer(
    name="xtest",
    help="Resolve, summarize, and run xtest jobs locally or in CI.",
    no_args_is_help=True,
)

SdkName = Literal["go", "java", "js"]
FocusSdk = Literal["all", "go", "java", "js"]
OtdfctlSource = Literal["auto", "standalone", "platform"]
PhaseName = Literal["legacy", "standard", "abac"]

REPO_URLS = {
    "platform": "https://github.com/opentdf/platform.git",
    "go": "https://github.com/opentdf/otdfctl.git",
    "java": "https://github.com/opentdf/java-sdk.git",
    "js": "https://github.com/opentdf/web-sdk.git",
}


class ResolvedVersion(BaseModel):
    """Resolved SDK or platform version."""

    sdk: str
    alias: str
    tag: str
    sha: str = ""
    head: bool = False
    pr: str | None = None
    release: str | None = None
    source: str | None = None
    env: str | None = None
    err: str | None = None


class XTestRefs(BaseModel):
    """User-facing refs that were requested."""

    platform: str
    go: str
    js: str
    java: str


class XTestOptions(BaseModel):
    """Execution options for one xtest job."""

    encrypt_sdk: SdkName
    focus_sdk: FocusSdk = "all"
    otdfctl_source: OtdfctlSource = "auto"
    phases: list[PhaseName] = Field(default_factory=lambda: ["legacy", "standard", "abac"])
    include_helper_tests: bool = False
    include_otdf_local_integration: bool = False


class XTestResolved(BaseModel):
    """Resolved concrete versions under test."""

    platform: list[ResolvedVersion]
    go: list[ResolvedVersion]
    js: list[ResolvedVersion]
    java: list[ResolvedVersion]


class XTestRunConfig(BaseModel):
    """Replayable xtest run configuration."""

    schema_version: int = 1
    kind: str = "otdf-local.xtest.run"
    refs: XTestRefs
    options: XTestOptions
    resolved: XTestResolved

    @property
    def platform(self) -> ResolvedVersion:
        """Return the single platform version for this run."""
        if len(self.resolved.platform) != 1:
            raise ValueError("xtest run config requires exactly one resolved platform version")
        return self.resolved.platform[0]

    def go_heads_json(self) -> str:
        """Return Go head tags as JSON for pytest env."""
        return json.dumps([row.tag for row in self.resolved.go if row.head])


class WorkspacePaths(BaseModel):
    """Relevant workspace paths for the runner."""

    repo_root: Path
    xtest_root: Path
    otdf_local_root: Path
    otdf_sdk_mgr_root: Path
    run_root: Path


def _workspace() -> WorkspacePaths:
    settings = get_settings()
    repo_root = settings.xtest_root.parent
    otdf_local_root = repo_root / "otdf-local"
    otdf_sdk_mgr_root = repo_root / "otdf-sdk-mgr"
    run_root = settings.xtest_root / "tmp" / "xtest-runner"
    run_root.mkdir(parents=True, exist_ok=True)
    return WorkspacePaths(
        repo_root=repo_root,
        xtest_root=settings.xtest_root,
        otdf_local_root=otdf_local_root,
        otdf_sdk_mgr_root=otdf_sdk_mgr_root,
        run_root=run_root,
    )


def _sanitize_name(value: str) -> str:
    return "".join(c if c.isalnum() or c in {"-", "_", "."} else "-" for c in value)


def _run(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        cmd,
        cwd=cwd,
        env={**os.environ, **(env or {})},
        text=True,
        capture_output=capture,
    )
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode,
            cmd,
            output=result.stdout,
            stderr=result.stderr,
        )
    return result


def _resolve_versions(
    sdk_mgr_root: Path,
    sdk: str,
    refs: str,
    *,
    go_source: OtdfctlSource,
) -> list[ResolvedVersion]:
    tokens = [part for part in refs.split() if part]
    if not tokens:
        raise ValueError(f"No refs provided for {sdk}")
    env = {"OTDFCTL_SOURCE": "platform"} if sdk == "go" and go_source == "platform" else None
    result = _run(
        ["uv", "run", "--project", str(sdk_mgr_root), "otdf-sdk-mgr", "versions", "resolve", sdk, *tokens],
        cwd=sdk_mgr_root,
        env=env,
        capture=True,
    )
    data = json.loads(result.stdout)
    resolved = [ResolvedVersion.model_validate(row) for row in data]
    errors = [row for row in resolved if row.err]
    if errors:
        raise ValueError(
            f"Version resolution failed for {sdk}: "
            + "; ".join(f"{row.alias}: {row.err}" for row in errors)
        )
    return resolved


def _build_run_config(
    workspace: WorkspacePaths,
    *,
    platform_ref: str,
    go_ref: str,
    js_ref: str,
    java_ref: str,
    encrypt_sdk: SdkName,
    focus_sdk: FocusSdk,
    otdfctl_source: OtdfctlSource,
    include_helper_tests: bool,
    include_otdf_local_integration: bool,
    phases: list[PhaseName] | None = None,
) -> XTestRunConfig:
    resolved = XTestResolved(
        platform=_resolve_versions(workspace.otdf_sdk_mgr_root, "platform", platform_ref, go_source=otdfctl_source),
        go=_resolve_versions(workspace.otdf_sdk_mgr_root, "go", go_ref, go_source=otdfctl_source),
        js=_resolve_versions(workspace.otdf_sdk_mgr_root, "js", js_ref, go_source=otdfctl_source),
        java=_resolve_versions(workspace.otdf_sdk_mgr_root, "java", java_ref, go_source=otdfctl_source),
    )
    if len(resolved.platform) != 1:
        raise ValueError("platform-ref must resolve to exactly one platform version for a single xtest run")
    return XTestRunConfig(
        refs=XTestRefs(platform=platform_ref, go=go_ref, js=js_ref, java=java_ref),
        options=XTestOptions(
            encrypt_sdk=encrypt_sdk,
            focus_sdk=focus_sdk,
            otdfctl_source=otdfctl_source,
            phases=phases or ["legacy", "standard", "abac"],
            include_helper_tests=include_helper_tests,
            include_otdf_local_integration=include_otdf_local_integration,
        ),
        resolved=resolved,
    )


def _config_to_dict(config: XTestRunConfig) -> dict[str, object]:
    return config.model_dump(mode="json", exclude_none=True)


def _summary_markdown(config: XTestRunConfig) -> str:
    yaml_text = dump_yaml(_config_to_dict(config)).rstrip()
    platform = config.platform
    job_name = f"{config.options.encrypt_sdk}/{platform.tag}"
    return (
        f"### Local Repro: `{job_name}`\n"
        f"<details>\n"
        f"<summary>Replay with <code>otdf-local xtest run --config ...</code></summary>\n\n"
        "```yaml\n"
        f"{yaml_text}\n"
        "```\n\n"
        "```bash\n"
        "cat > xtest-repro.yaml <<'EOF'\n"
        f"{yaml_text}\n"
        "EOF\n"
        "uv run --project otdf-local otdf-local xtest run --config xtest-repro.yaml\n"
        "```\n"
        "</details>\n"
    )


def _write_summary(config: XTestRunConfig) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        print_warning("GITHUB_STEP_SUMMARY is not set; skipping summary output")
        return
    with open(path, "a") as handle:
        handle.write(_summary_markdown(config))


def _write_config(path: Path, config: XTestRunConfig) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    save_yaml(path, _config_to_dict(config))


def _load_config(path: Path) -> XTestRunConfig:
    try:
        return XTestRunConfig.model_validate(load_yaml(path))
    except ValidationError as exc:
        raise ValueError(f"Invalid xtest config {path}: {exc}") from exc


def _git_worktree_checkout(repo_url: str, bare_repo: Path, worktree: Path, sha: str) -> Path:
    bare_repo.parent.mkdir(parents=True, exist_ok=True)
    if not bare_repo.exists():
        _run(["git", "clone", "--bare", repo_url, str(bare_repo)])
    else:
        _run(["git", f"--git-dir={bare_repo}", "fetch", "--all", "--tags"])
    if worktree.exists():
        current = _run(["git", "-C", str(worktree), "rev-parse", "HEAD"], capture=True)
        if current.stdout.strip() == sha:
            return worktree
        _run(["git", f"--git-dir={bare_repo}", "worktree", "remove", "--force", str(worktree)])
        shutil.rmtree(worktree, ignore_errors=True)
    _run(["git", f"--git-dir={bare_repo}", "worktree", "add", "--detach", str(worktree), sha])
    return worktree


def _checkout_platform(workspace: WorkspacePaths, config: XTestRunConfig) -> Path:
    platform = config.platform
    slug = _sanitize_name(f"{platform.tag}-{platform.sha[:7] or 'local'}")
    bare_repo = workspace.run_root / "repos" / "platform.git"
    worktree = workspace.run_root / "platform" / slug
    print_info(f"Checking out platform {platform.tag} ({platform.sha[:7]})")
    return _git_worktree_checkout(REPO_URLS["platform"], bare_repo, worktree, platform.sha)


def _resolved_otdfctl_source(config: XTestRunConfig, platform_dir: Path) -> Literal["standalone", "platform"]:
    requested = config.options.otdfctl_source
    if requested == "platform":
        return "platform"
    if requested == "standalone":
        return "standalone"
    embedded = platform_dir / "otdfctl" / "go.mod"
    return "platform" if embedded.is_file() else "standalone"


def _clean_sdk_state(workspace: WorkspacePaths) -> None:
    print_info("Cleaning xtest SDK dist/src state")
    _run(
        ["uv", "run", "--project", str(workspace.otdf_sdk_mgr_root), "otdf-sdk-mgr", "clean"],
        cwd=workspace.otdf_sdk_mgr_root,
    )
    for env_file in (_sdk_root(workspace, "java")).glob("*.env"):
        env_file.unlink(missing_ok=True)


def _install_artifact_version(workspace: WorkspacePaths, sdk: str, version: ResolvedVersion) -> bool:
    if version.head or not version.release:
        return False
    cmd = [
        "uv",
        "run",
        "--project",
        str(workspace.otdf_sdk_mgr_root),
        "otdf-sdk-mgr",
        "install",
        "artifact",
        "--sdk",
        sdk,
        "--version",
        version.release,
        "--dist-name",
        version.tag,
    ]
    if version.source:
        cmd.extend(["--source", version.source])
    try:
        _run(cmd, cwd=workspace.otdf_sdk_mgr_root)
        return True
    except subprocess.CalledProcessError as exc:
        print_warning(f"Artifact install failed for {sdk} {version.tag}; falling back to source build")
        if exc.stderr:
            print_warning(exc.stderr.strip().splitlines()[-1])
        return False


def _sdk_root(workspace: WorkspacePaths, sdk: str) -> Path:
    return workspace.xtest_root / "sdk" / sdk


def _checkout_source_version(
    workspace: WorkspacePaths,
    sdk: str,
    version: ResolvedVersion,
    *,
    platform_dir: Path,
    platform_sha: str,
) -> None:
    sdk_root = _sdk_root(workspace, sdk)
    src_dir = sdk_root / "src" / version.tag
    if sdk == "go" and version.source == "platform":
        if version.sha == platform_sha and (platform_dir / "otdfctl").is_dir():
            src_dir.parent.mkdir(parents=True, exist_ok=True)
            src_dir.unlink(missing_ok=True)
            src_dir.symlink_to(platform_dir / "otdfctl", target_is_directory=True)
            return
        bare_repo = workspace.run_root / "repos" / "platform.git"
        platform_src = workspace.run_root / "sdk-platform" / _sanitize_name(f"{version.tag}-{version.sha[:7]}")
        _git_worktree_checkout(REPO_URLS["platform"], bare_repo, platform_src, version.sha)
        src_dir.parent.mkdir(parents=True, exist_ok=True)
        src_dir.unlink(missing_ok=True)
        src_dir.symlink_to(platform_src / "otdfctl", target_is_directory=True)
        return

    bare_name = f"{sdk}.git"
    bare_repo = sdk_root / "src" / bare_name
    _git_worktree_checkout(REPO_URLS[sdk], bare_repo, src_dir, version.sha)


def _prepare_java_env_files(config: XTestRunConfig, workspace: WorkspacePaths, platform_sha: str) -> None:
    java_root = _sdk_root(workspace, "java")
    for version in config.resolved.java:
        env_path = java_root / f"{version.tag}.env"
        if version.head and config.platform.head and config.options.focus_sdk in {"go", "java"}:
            env_path.write_text(f"PLATFORM_BRANCH={platform_sha}\n")
            continue
        if version.env:
            env_path.write_text(f"{version.env}\n")


def _build_source_sdks(
    workspace: WorkspacePaths,
    config: XTestRunConfig,
    *,
    platform_dir: Path,
    otdfctl_source: Literal["standalone", "platform"],
) -> None:
    needs_build: dict[str, list[ResolvedVersion]] = {"go": [], "java": [], "js": []}
    for sdk in ("go", "java", "js"):
        versions = getattr(config.resolved, sdk)
        for version in versions:
            if not _install_artifact_version(workspace, sdk, version):
                needs_build[sdk].append(version)

    if not any(needs_build.values()):
        return

    for sdk, versions in needs_build.items():
        for version in versions:
            print_info(f"Checking out {sdk} source for {version.tag} ({version.sha[:7]})")
            _checkout_source_version(
                workspace,
                sdk,
                version,
                platform_dir=platform_dir,
                platform_sha=config.platform.sha,
            )

    if needs_build["java"]:
        _run(
            ["uv", "run", "--project", str(workspace.otdf_sdk_mgr_root), "otdf-sdk-mgr", "java-fixup"],
            cwd=workspace.otdf_sdk_mgr_root,
        )
        _prepare_java_env_files(config, workspace, config.platform.sha)

    if (
        needs_build["go"]
        and any(version.head for version in needs_build["go"])
        and otdfctl_source != "platform"
        and config.options.focus_sdk == "go"
        and config.platform.head
    ):
        heads = json.dumps([version.tag for version in needs_build["go"] if version.head])
        _run(
            [
                "uv",
                "run",
                "--project",
                str(workspace.otdf_sdk_mgr_root),
                "otdf-sdk-mgr",
                "go-fixup",
                "--platform-dir",
                str(platform_dir),
                "--heads",
                heads,
                str(_sdk_root(workspace, "go") / "src"),
            ],
            cwd=workspace.otdf_sdk_mgr_root,
        )

    for sdk, versions in needs_build.items():
        if not versions:
            continue
        print_info(f"Building {sdk} SDK CLI(s)")
        _run(["make"], cwd=_sdk_root(workspace, sdk))


def _platform_version(platform_dir: Path, fallback: str) -> str:
    try:
        result = _run(["go", "run", "./service", "version"], cwd=platform_dir, capture=True)
        version = result.stdout.strip() or result.stderr.strip()
        return version or fallback
    except subprocess.CalledProcessError:
        return fallback


def _supports_multikas(platform_tag: str, platform_version: str) -> bool:
    if platform_tag == "main":
        return True
    raw = platform_version.lstrip("v")
    parts = raw.split(".")
    if len(parts) < 2:
        return False
    try:
        major = int(parts[0])
        minor = int(parts[1])
    except ValueError:
        return False
    return major > 0 or minor > 4


def _key_management_supported(settings: Settings) -> bool:
    config = load_yaml(settings.platform_config)
    return get_nested(config, "services.kas.preview.key_management") in {True, False}


def _root_key(settings: Settings) -> str:
    config = load_yaml(settings.platform_config)
    value = get_nested(config, "services.kas.root_key")
    if isinstance(value, str) and value:
        return value
    raise ValueError(f"No services.kas.root_key found in {settings.platform_config}")


def _prepare_test_results_dir(workspace: WorkspacePaths) -> Path:
    results_dir = workspace.xtest_root / "test-results"
    shutil.rmtree(results_dir, ignore_errors=True)
    results_dir.mkdir(parents=True, exist_ok=True)
    return results_dir


def _pytest_env(
    workspace: WorkspacePaths,
    settings: Settings,
    config: XTestRunConfig,
    *,
    platform_tag: str,
    platform_version: str,
    root_key: str,
    kas_logs: dict[str, str] | None = None,
) -> dict[str, str]:
    env = {
        "PLATFORMURL": settings.platform_url,
        "PLATFORM_DIR": str(settings.platform_dir.resolve()),
        "PLATFORM_TAG": platform_tag,
        "PLATFORM_VERSION": platform_version,
        "SCHEMA_FILE": str((workspace.xtest_root / "manifest.schema.json").resolve()),
        "OT_ROOT_KEY": root_key,
        "PLATFORM_LOG_FILE": str((settings.logs_dir / "platform.log").resolve()),
        "OTDFCTL_HEADS": config.go_heads_json(),
    }
    if kas_logs:
        env.update(kas_logs)
    return env


def _run_pytest(workspace: WorkspacePaths, args: list[str], env: dict[str, str]) -> None:
    cmd = ["uv", "run", "pytest", *args]
    _run(cmd, cwd=workspace.xtest_root, env=env)


def _start_environment(settings: Settings) -> None:
    docker = get_docker_service(settings)
    platform = get_platform_service(settings)
    provisioner = get_provisioner(settings)

    print_info("Starting Docker services")
    if not docker.start():
        raise RuntimeError("Failed to start Docker services")

    with status_spinner("Waiting for Keycloak..."):
        wait_for_health(
            f"http://localhost:{Ports.KEYCLOAK}/auth/realms/master",
            timeout=120,
            service_name="Keycloak",
        )
    wait_for_port(Ports.POSTGRES, "localhost", timeout=60, service_name="PostgreSQL")
    if not provisioner.provision_keycloak():
        raise RuntimeError("Keycloak provisioning failed")

    print_info("Starting platform")
    if not platform.start():
        raise RuntimeError("Failed to start platform")
    with status_spinner("Waiting for platform..."):
        wait_for_health(
            f"http://localhost:{Ports.PLATFORM}/healthz",
            timeout=120,
            service_name="Platform",
        )
    fixtures = provisioner.provision_fixtures()
    if not fixtures:
        raise RuntimeError(f"Fixture provisioning failed: {fixtures.error_message}")


def _start_kas(settings: Settings) -> dict[str, str]:
    logs: dict[str, str] = {}
    manager = get_kas_manager(settings)
    print_info("Starting KAS instances")
    failed = []
    for name in Ports.all_kas_names():
        kas = manager.get(name)
        if kas is None or not kas.start():
            failed.append(name)
    if failed:
        raise RuntimeError(f"Failed to start KAS instances: {', '.join(failed)}")
    for name in Ports.all_kas_names():
        wait_for_health(
            f"http://localhost:{Ports.get_kas_port(name)}/healthz",
            timeout=60,
            service_name=f"KAS {name}",
        )
        logs[f"KAS_{name.upper()}_LOG_FILE"] = str(settings.get_kas_log_path(name).resolve())
    return logs


def _stop_environment(settings: Settings) -> None:
    try:
        get_kas_manager(settings).stop_all()
    finally:
        try:
            get_platform_service(settings).stop()
        finally:
            get_docker_service(settings).stop()


def _run_requested_phases(
    workspace: WorkspacePaths,
    settings: Settings,
    config: XTestRunConfig,
    *,
    platform_tag: str,
    platform_version: str,
    root_key: str,
    multikas_supported: bool,
) -> None:
    results_dir = _prepare_test_results_dir(workspace)
    base_env = _pytest_env(
        workspace,
        settings,
        config,
        platform_tag=platform_tag,
        platform_version=platform_version,
        root_key=root_key,
    )

    if config.options.include_helper_tests:
        _run_pytest(
            workspace,
            [
                "--html",
                str(results_dir / f"helper-{config.options.focus_sdk}-{platform_tag}.html"),
                "--self-contained-html",
                "--sdks-encrypt",
                config.options.encrypt_sdk,
                "test_self.py",
                "test_audit_logs.py",
            ],
            base_env,
        )

    if config.options.include_otdf_local_integration:
        _run(
            [
                "uv",
                "run",
                "--project",
                str(workspace.otdf_local_root),
                "pytest",
                "--maxfail=1",
                "--disable-warnings",
                "-v",
                "--tb=short",
                "-m",
                "integration",
            ],
            cwd=workspace.otdf_local_root,
            env={"OTDF_LOCAL_PLATFORM_DIR": str(settings.platform_dir.resolve())},
        )

    common = [
        "-ra",
        "-v",
        "--sdks-encrypt",
        config.options.encrypt_sdk,
        "--focus",
        config.options.focus_sdk,
    ]

    if "legacy" in config.options.phases:
        _run_pytest(
            workspace,
            [
                "-n",
                "auto",
                "--dist",
                "worksteal",
                "--html",
                str(results_dir / f"legacy-{config.options.focus_sdk}-{platform_tag}.html"),
                "--self-contained-html",
                *common,
                "test_legacy.py",
            ],
            base_env,
        )

    if "standard" in config.options.phases:
        _run_pytest(
            workspace,
            [
                "-n",
                "auto",
                "--dist",
                "loadscope",
                "--html",
                str(results_dir / f"standard-{config.options.focus_sdk}-{platform_tag}.html"),
                "--self-contained-html",
                *common,
                "test_tdfs.py",
                "test_policytypes.py",
            ],
            base_env,
        )

    if "abac" in config.options.phases:
        if not multikas_supported:
            print_warning(f"Skipping ABAC phase: platform {platform_version} does not support multikas")
            return
        kas_logs = _start_kas(settings)
        abac_env = _pytest_env(
            workspace,
            settings,
            config,
            platform_tag=platform_tag,
            platform_version=platform_version,
            root_key=root_key,
            kas_logs=kas_logs,
        )
        _run_pytest(
            workspace,
            [
                "-n",
                "auto",
                "--dist",
                "loadscope",
                "--html",
                str(results_dir / f"attributes-{config.options.focus_sdk}-{platform_tag}.html"),
                "--self-contained-html",
                "--audit-log-dir",
                str(results_dir / "audit-logs"),
                *common,
                "test_abac.py",
            ],
            abac_env,
        )


@xtest_app.command("plan")
def plan_run(
    platform_ref: Annotated[str, typer.Option(help="Platform ref under test (single ref)")],
    encrypt_sdk: Annotated[SdkName, typer.Option(help="SDK used for encrypt side of xtest matrix")],
    output: Annotated[Path | None, typer.Option(help="Write config YAML to this path")] = None,
    go_ref: Annotated[str, typer.Option(help="Go/otdfctl refs to resolve")] = "main",
    js_ref: Annotated[str, typer.Option(help="JS SDK refs to resolve")] = "main",
    java_ref: Annotated[str, typer.Option(help="Java SDK refs to resolve")] = "main",
    focus_sdk: Annotated[FocusSdk, typer.Option(help="Focus filter for pytest")] = "all",
    otdfctl_source: Annotated[OtdfctlSource, typer.Option(help="Go SDK source resolution mode")] = "auto",
    include_helper_tests: Annotated[
        bool,
        typer.Option("--include-helper-tests", help="Include helper-library pytest validation"),
    ] = False,
    include_otdf_local_integration: Annotated[
        bool,
        typer.Option("--include-otdf-local-integration", help="Include otdf-local integration tests"),
    ] = False,
    write_summary: Annotated[
        bool,
        typer.Option("--write-summary", help="Append the replay config to GITHUB_STEP_SUMMARY"),
    ] = False,
) -> None:
    """Resolve refs and write a replayable xtest config."""
    workspace = _workspace()
    config = _build_run_config(
        workspace,
        platform_ref=platform_ref,
        go_ref=go_ref,
        js_ref=js_ref,
        java_ref=java_ref,
        encrypt_sdk=encrypt_sdk,
        focus_sdk=focus_sdk,
        otdfctl_source=otdfctl_source,
        include_helper_tests=include_helper_tests,
        include_otdf_local_integration=include_otdf_local_integration,
    )

    if output:
        _write_config(output, config)
        print_success(f"Wrote xtest config to {output}")
        _emit_github_output("config-path", str(output))
    else:
        print(dump_yaml(_config_to_dict(config)).rstrip())

    _emit_github_output("platform-tag", config.platform.tag)
    _emit_github_output("platform-sha", config.platform.sha)
    _emit_github_output("encrypt-sdk", config.options.encrypt_sdk)

    if write_summary:
        _write_summary(config)


@xtest_app.command("run")
def run_xtest(
    config_path: Annotated[
        Path | None,
        typer.Option("--config", help="Replay config generated by `otdf-local xtest plan`"),
    ] = None,
    platform_ref: Annotated[str | None, typer.Option(help="Platform ref under test")] = None,
    encrypt_sdk: Annotated[SdkName | None, typer.Option(help="SDK used for encrypt side")] = None,
    go_ref: Annotated[str, typer.Option(help="Go/otdfctl refs to resolve")] = "main",
    js_ref: Annotated[str, typer.Option(help="JS SDK refs to resolve")] = "main",
    java_ref: Annotated[str, typer.Option(help="Java SDK refs to resolve")] = "main",
    focus_sdk: Annotated[FocusSdk, typer.Option(help="Focus filter for pytest")] = "all",
    otdfctl_source: Annotated[OtdfctlSource, typer.Option(help="Go SDK source resolution mode")] = "auto",
    include_helper_tests: Annotated[
        bool,
        typer.Option("--include-helper-tests", help="Include helper-library pytest validation"),
    ] = False,
    include_otdf_local_integration: Annotated[
        bool,
        typer.Option("--include-otdf-local-integration", help="Include otdf-local integration tests"),
    ] = False,
) -> None:
    """Run the same xtest orchestration locally that CI uses."""
    workspace = _workspace()
    if config_path:
        config = _load_config(config_path)
    else:
        if not platform_ref or not encrypt_sdk:
            raise typer.BadParameter("either --config or both --platform-ref and --encrypt-sdk are required")
        config = _build_run_config(
            workspace,
            platform_ref=platform_ref,
            go_ref=go_ref,
            js_ref=js_ref,
            java_ref=java_ref,
            encrypt_sdk=encrypt_sdk,
            focus_sdk=focus_sdk,
            otdfctl_source=otdfctl_source,
            include_helper_tests=include_helper_tests,
            include_otdf_local_integration=include_otdf_local_integration,
        )

    platform_dir = _checkout_platform(workspace, config)
    settings = Settings(xtest_root=workspace.xtest_root, platform_dir=platform_dir)
    settings.ensure_directories()
    source_mode = _resolved_otdfctl_source(config, platform_dir)

    print_info(
        f"Running xtest for encrypt SDK {config.options.encrypt_sdk} against platform {config.platform.tag}"
    )

    try:
        _clean_sdk_state(workspace)
        _build_source_sdks(workspace, config, platform_dir=platform_dir, otdfctl_source=source_mode)
        _start_environment(settings)

        platform_version = _platform_version(platform_dir, config.platform.tag)
        root_key = _root_key(settings)
        multikas_supported = _supports_multikas(config.platform.tag, platform_version)
        km_supported = _key_management_supported(settings)
        print_info(f"Platform version: {platform_version}")
        print_info(f"otdfctl source mode: {source_mode}")
        print_info(f"Multi-KAS support: {'enabled' if multikas_supported else 'disabled'}")
        print_info(f"Key-management config field present: {'yes' if km_supported else 'no'}")

        _run_requested_phases(
            workspace,
            settings,
            config,
            platform_tag=config.platform.tag,
            platform_version=platform_version,
            root_key=root_key,
            multikas_supported=multikas_supported,
        )
    except (RuntimeError, ValueError, subprocess.CalledProcessError, WaitTimeoutError) as exc:
        print_error(str(exc))
        raise typer.Exit(1) from exc
    finally:
        _stop_environment(settings)

    print_success("xtest run completed successfully")
