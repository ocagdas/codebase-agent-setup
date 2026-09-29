"""Resolve official Spec Kit versions and verify isolated local installations."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sysconfig
import tempfile
import tomllib

from .resources import RESOURCE_ROOT as ROOT

OFFICIAL = "https://github.com/github/spec-kit"
SHA = re.compile(r"^[0-9a-f]{40}$")
RELEASE = re.compile(r"^v?[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?$")


class ToolchainError(ValueError):
    pass


def command_timeout(kind="command"):
    variable = "CBSETUP_" + kind.upper() + "_TIMEOUT"
    legacy = "REPO_PILOT_" + kind.upper() + "_TIMEOUT"  # accepted from before the rename
    try:
        value = float(os.environ.get(variable, os.environ.get(legacy, "15" if kind == "probe" else "600")))
        if not 0 < value < float("inf"):
            raise ValueError()
        return value
    except ValueError as error:
        raise ToolchainError(f"{variable} must be a finite positive number of seconds") from error


def stop_process(process):
    """Stop the owned command and reap it for both deadlines and cancellation."""
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except ProcessLookupError:
        pass
    finally:
        # Do not wait for pipe EOF from a descendant that escaped the session.
        for stream in (process.stdout, process.stderr):
            if stream is not None:
                stream.close()
        process.wait()


def run(argv, cwd=None, *, probe=False, capture=True):
    timeout = command_timeout("probe" if probe else "command")
    with subprocess.Popen(
        [str(x) for x in argv],
        cwd=cwd,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        text=True,
        encoding="utf-8",
        errors="replace",
        start_new_session=os.name == "posix",
        env=dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8"),
    ) as process:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as error:
            stop_process(process)
            raise ToolchainError(f"Command timed out after {timeout:g}s: {argv[0]}") from error
        except BaseException:
            # Cancellation must finish cleanup before setup releases its environment lock.
            stop_process(process)
            raise
        if process.returncode:
            raise ToolchainError(f"Command failed ({argv[0]}): {stdout or ''}{stderr or ''}")
        return (stdout or "").strip()


def lock():
    return json.loads((ROOT / "upstream.lock.json").read_text(encoding="utf-8"))


def validate_ref(ref):
    if ref is not None and (not isinstance(ref, str) or not (SHA.fullmatch(ref) or RELEASE.fullmatch(ref))):
        raise ToolchainError("Spec Kit ref must be a release (v1.0.4) or full lowercase 40-character commit")


def validate_record(data):
    if not isinstance(data, dict) or data.get("schema_version") != "1.0":
        raise ToolchainError("Unsupported toolchain record schema")
    if data.get("upstream_repository") != OFFICIAL:
        raise ToolchainError("Toolchain records must refer to official github/spec-kit")
    if not isinstance(data.get("upstream_commit"), str) or not SHA.fullmatch(data["upstream_commit"]):
        raise ToolchainError("Invalid toolchain commit")
    if not isinstance(data.get("specify_cli_version"), str) or not RELEASE.fullmatch(data["specify_cli_version"]):
        raise ToolchainError("Invalid CLI version in record")
    if "requested_ref" not in data:
        raise ToolchainError("Toolchain record needs requested_ref (null is allowed)")
    validate_ref(data.get("requested_ref"))
    if not isinstance(data.get("package_version"), str):
        raise ToolchainError("Toolchain record needs a package version")
    return data


def resolve_selection(ref=None, record_file=None):
    """Default pin is offline; releases resolve to immutable official commits."""
    validate_ref(ref)
    pin = lock()
    if record_file:
        data = validate_record(json.loads(Path(record_file).read_text(encoding="utf-8")))
        # Import selects exact source. An explicit conflicting ref is an error.
        if ref and ref not in (
            data.get("requested_ref"),
            data["upstream_commit"],
            data["specify_cli_version"],
            "v" + data["specify_cli_version"],
        ):
            raise ToolchainError("Selected ref conflicts with imported toolchain record")
        if data["package_version"] != pin["package_version"]:
            raise ToolchainError("Toolchain record belongs to a different codebase-agent-setup package version")
        return {
            key: data[key]
            for key in (
                "schema_version",
                "requested_ref",
                "upstream_repository",
                "upstream_commit",
                "specify_cli_version",
                "package_version",
            )
        }
    if ref is None or ref in (pin["upstream_tag"], pin["upstream_commit"], pin["specify_cli_version"]):
        commit, version = pin["upstream_commit"], pin["specify_cli_version"]
    else:
        commit = ref
        if not SHA.fullmatch(ref):
            tag = ref if ref.startswith("v") else "v" + ref
            refs = {}
            for line in run(
                ["git", "ls-remote", "--tags", OFFICIAL + ".git", f"refs/tags/{tag}", f"refs/tags/{tag}^{{}}"]
            ).splitlines():
                sha, name = line.split()
                refs[name] = sha
            commit = refs.get(f"refs/tags/{tag}^{{}}") or refs.get(f"refs/tags/{tag}")
            if not commit:
                raise ToolchainError(f"Official release {tag} was not found")
        with tempfile.TemporaryDirectory(prefix="spec-kit-resolution-") as temp:
            run(["git", "init", "--quiet", temp])
            run(["git", "-C", temp, "fetch", "--quiet", "--depth", "1", OFFICIAL + ".git", commit])
            commit = run(["git", "-C", temp, "rev-parse", "FETCH_HEAD^{commit}"])
            metadata = tomllib.loads(run(["git", "-C", temp, "show", "FETCH_HEAD:pyproject.toml"]))
            version = metadata.get("project", {}).get("version")
            if not isinstance(version, str) or not RELEASE.fullmatch(version):
                raise ToolchainError("Cannot establish a supported CLI version from upstream pyproject.toml")
    return validate_record(
        {
            "schema_version": "1.0",
            "requested_ref": ref,
            "upstream_repository": OFFICIAL,
            "upstream_commit": commit,
            "specify_cli_version": version,
            "package_version": pin["package_version"],
        }
    )


def is_override(selection):
    return selection["upstream_commit"] != lock()["upstream_commit"]


def environment_path(settings, selection):
    base = Path(settings["tooling"]["env_dir"]) if settings["tooling"]["env_dir"] else ROOT / ".venv"
    if is_override(selection):
        # Full commit avoids collisions; caller-selected base remains untouched.
        return base.parent / (base.name + "-speckit-" + selection["upstream_commit"])
    return base


def conda_environment(settings, selection):
    name = settings["tooling"]["conda_name"]
    return name + ("-speckit-" + selection["upstream_commit"] if is_override(selection) else "")


def python_in(env):
    return Path(env) / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def cli_in(env):
    return Path(env) / ("Scripts/specify.exe" if os.name == "nt" else "bin/specify")


def discover_cli(settings, selection, explicit=None):
    """Find a compatible CLI without assuming the launcher lives in its checkout."""
    if explicit:
        candidate = shutil.which(explicit)
        if not candidate:
            raise ToolchainError("Specify executable not found: " + explicit)
        # Explicit choices are checked by stage_package; never substitute another CLI.
        return candidate
    configured = settings["tooling"]
    candidates = []
    local = cli_in(environment_path(settings, selection))
    if configured["env_dir"]:
        candidates.append(str(local))
    executable = "specify.exe" if os.name == "nt" else "specify"
    candidates.append(str(Path(sysconfig.get_path("scripts")) / executable))
    if configured["mode"] == "conda":
        conda = os.environ.get("CONDA_EXE") or shutil.which("conda")
        if conda:
            try:
                prefix = run(
                    [
                        conda,
                        "run",
                        "-n",
                        conda_environment(settings, selection),
                        "python",
                        "-c",
                        "import sys; print(sys.prefix)",
                    ],
                    probe=True,
                )
                candidates.append(str(cli_in(Path(prefix))))
            except ToolchainError:
                pass  # A matching active environment or PATH executable may still work.
    candidates.append(str(local))
    # The launcher prepends its own scripts directory. Enumerate PATH entries
    # so a mismatched companion does not hide a matching CLI later on PATH.
    candidates.extend(shutil.which("specify", path=directory) for directory in os.get_exec_path())
    failures = []
    for candidate in dict.fromkeys(path for path in candidates if path):
        if not Path(candidate).is_file():
            continue
        try:
            probe_cli(candidate, selection)
        except (ToolchainError, OSError, ValueError) as error:
            failures.append(str(error))
            continue
        return candidate
    detail = ("\n" + "\n".join(failures)) if failures else ""
    raise ToolchainError(
        "No matching Specify CLI found; run setup_tooling.py for the selected "
        "toolchain or pass --specify explicitly." + detail
    )


def requirement(selection):
    return f"specify-cli @ git+{OFFICIAL}.git@{selection['upstream_commit']}"


def check_export_path(path):
    if not path:
        return
    path = Path(path)
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ToolchainError("Refusing record export through a symlink")
    if path.exists():
        try:
            validate_record(json.loads(path.read_text(encoding="utf-8")))
        except (ValueError, OSError) as error:
            raise ToolchainError("Record export would replace a file that is not a toolchain record") from error


def write_record(path, data):
    path = Path(path)
    if path.is_symlink():
        raise ToolchainError("Refusing to replace a symlink toolchain record")
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(data, indent=2, sort_keys=True) + "\n"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(rendered)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def probe_cli(specify, selection):
    output = re.sub(r"\x1b\[[0-9;]*m", "", run([specify, "version"], ROOT, probe=True))
    expected = selection["specify_cli_version"]
    if not re.search(r"CLI Version\s+" + re.escape(expected) + r"(?![\w.])", output):
        raise ToolchainError(f"Selected Spec Kit {expected} does not match CLI {specify}")
    source_status = "version_only"
    # Verify pip VCS provenance in the actual executable's environment.
    binary = Path(specify).resolve()
    candidates = [binary.parent / ("python.exe" if os.name == "nt" else "python")]
    if os.name == "nt":
        candidates.append(binary.parent.parent / "python.exe")
    for python in candidates:
        if not python.is_file():
            continue
        metadata = json.loads(
            run(
                [
                    python,
                    "-c",
                    "import importlib.metadata as m,json; d=m.distribution('specify-cli'); "
                    "print(json.dumps({'version':d.version,'source':json.loads(d.read_text('direct_url.json') or '{}')}))",
                ],
                probe=True,
            )
        )
        source = metadata["source"]
        if (
            metadata["version"] == expected
            and source.get("url", "").removesuffix(".git") == OFFICIAL
            and source.get("vcs_info", {}).get("commit_id") == selection["upstream_commit"]
        ):
            source_status = "verified_commit"
        break
    if is_override(selection) and source_status != "verified_commit":
        raise ToolchainError(
            "Override CLI source commit could not be verified; run setup_tooling.py for the selected ref"
        )
    return source_status


def package_fingerprint():
    digest = hashlib.sha256()
    for directory in ("preset", "extension", "project"):
        for path in sorted((ROOT / directory).rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                digest.update(path.relative_to(ROOT).as_posix().encode("utf-8"))
                digest.update(path.read_bytes())
    return digest.hexdigest()


def stage_package(specify, integrations, selection, workspace):
    """Exercise public CLI capabilities and verify composed output in isolation."""
    stage = Path(workspace) / "project"
    source_status = probe_cli(specify, selection)
    packages = {}
    for name, manifest in [("extension", "extension.yml"), ("preset", "preset.yml")]:
        path = ROOT / name
        if is_override(selection):
            path = Path(workspace) / name
            shutil.copytree(ROOT / name, path)
            manifest_path = path / manifest
            original = manifest_path.read_text(encoding="utf-8")
            amended, count = re.subn(
                r"(?m)^(\s*speckit_version:)\s*==[^\s]+\s*$",
                lambda m: m[1] + " ==" + selection["specify_cli_version"],
                original,
            )
            if count != 1:
                raise ToolchainError("Cannot adapt staging compatibility declaration")
            manifest_path.write_text(amended, encoding="utf-8")
        packages[name] = path
    run(
        [
            specify,
            "init",
            stage,
            "--integration",
            integrations[0],
            "--script",
            "py",
            "--ignore-agent-tools",
            "--non-interactive",
        ],
        ROOT,
    )
    run([specify, "extension", "add", "--dev", packages["extension"]], stage)
    run([specify, "preset", "add", "--dev", packages["preset"]], stage)
    for integration in integrations[1:]:
        run([specify, "integration", "install", integration, "--script", "py", "--force"], stage)
    for integration in [*integrations[1:], integrations[0]]:
        run([specify, "integration", "use", integration], stage)
    folders = {"codex": ".agents", "copilot": ".github", "cursor-agent": ".cursor"}
    for integration in integrations:
        skill = stage / folders[integration] / "skills/speckit-implement/SKILL.md"
        if not skill.is_file():
            raise ToolchainError(f"Compatibility check failed: missing implementation skill for {integration}")
        text = skill.read_text(encoding="utf-8")
        if "Engineering integration" not in text or "Pre-Execution Checks" not in text:
            raise ToolchainError(f"Compatibility check failed: incomplete command composition for {integration}")
        report_skill = stage / folders[integration] / "skills/speckit-engineering-report/SKILL.md"
        if not report_skill.is_file():
            raise ToolchainError(f"Compatibility check failed: missing engineering report for {integration}")
    for template in ("spec-template.md", "plan-template.md", "tasks-template.md"):
        if not (stage / ".specify/templates" / template).is_file():
            raise ToolchainError(f"Compatibility check failed: missing {template}")
    evidence = {
        "status": "pass",
        "classification": "local_override_checked" if is_override(selection) else "distribution_default",
        "integrations": integrations,
        "source_verification": source_status,
        "package_fingerprint": package_fingerprint(),
        "checks": [
            "CLI version",
            "init",
            "extension",
            "preset",
            "integration activation",
            "command composition",
            "feature templates",
        ],
        "limits": "Staging checks, not live agent or project build validation",
    }
    return stage, evidence
