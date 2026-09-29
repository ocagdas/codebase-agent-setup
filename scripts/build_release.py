"""Build, validate and smoke-test release artifacts without publishing anything."""

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import tarfile
import tomllib
import zipfile

if __package__:
    from . import version as versioning
else:
    import version as versioning

ROOT = Path(__file__).resolve().parents[1]


if __package__:
    from .repository_provenance import write_provenance, verify_provenance
else:
    from repository_provenance import write_provenance, verify_provenance


def verify_manifest(directory):
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("Artifact directory must be a real directory")
    paths = list(directory.iterdir())
    if any(p.is_symlink() or not p.is_file() for p in paths):
        raise ValueError("Artifact entries must be regular files")
    manifest = directory / "SHA256SUMS"
    entries = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        if (
            Path(name).name != name
            or name in entries
            or "\\" in name
            or ":" in name
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
        ):
            raise ValueError("Invalid checksum manifest entry")
        entries[name] = digest
    artifacts = {p.name for p in directory.glob("*.whl")} | {p.name for p in directory.glob("*.tar.gz")}
    if len(artifacts) != 2 or set(entries) != artifacts | {"provenance.json"}:
        raise ValueError("Expected exactly one wheel and one source distribution in manifest")
    if len(list(directory.glob("*.whl"))) != 1 or len(list(directory.glob("*.tar.gz"))) != 1:
        raise ValueError("Release artifact types are incomplete")
    if {p.name for p in paths} != artifacts | {"SHA256SUMS", "provenance.json"}:
        raise ValueError("Unexpected files in release artifact set")
    for name, expected in entries.items():
        if hashlib.sha256((directory / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Checksum mismatch: {name}")
    value = json.loads((directory / "provenance.json").read_text(encoding="utf-8"))
    verify_provenance(value, {name: entries[name] for name in artifacts})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".quality/release")
    kind = parser.add_mutually_exclusive_group()
    kind.add_argument("--tag", help="Build from a clean, exact annotated vVERSION tag")
    kind.add_argument("--candidate", action="store_true", help="Build a development snapshot without release claims")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if args.verify_only:
        verify_manifest(output)
        return 0
    if not args.tag and not args.candidate:
        raise ValueError("Select --candidate or --tag; builds never imply publication")
    commit = versioning.git("rev-parse", "HEAD")
    dirty = bool(versioning.git("status", "--porcelain"))
    if args.tag and (
        dirty
        or versioning.tag_commit(args.tag) != commit
        or versioning.git("cat-file", "-t", f"refs/tags/{args.tag}") != "tag"
    ):
        raise ValueError("Release builds require a clean checkout of the exact annotated tag")
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    pin = json.loads((ROOT / "upstream.lock.json").read_text(encoding="utf-8"))
    if pin["package_version"] != version or (args.tag and args.tag != "v" + version):
        raise ValueError("Tag and package version files must agree")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Artifact output must be empty; choose a new directory or remove old artifacts explicitly")
    output.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, "-m", "build", "--outdir", str(output)], cwd=ROOT, check=True, timeout=600)
    wheels = list(output.glob("*.whl"))
    sources = list(output.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sources) != 1:
        raise ValueError("Build must produce exactly one wheel and one source distribution")
    subprocess.run(
        [sys.executable, "-m", "twine", "check", "--strict", str(wheels[0]), str(sources[0])], check=True, timeout=120
    )
    with zipfile.ZipFile(wheels[0]) as archive:
        names = archive.namelist()
        if not any(name.endswith("/licenses/LICENSE") for name in names) or not any(
            name.endswith("/licenses/NOTICE.md") for name in names
        ):
            raise ValueError("Wheel is missing licensing notices")
        if not any(name.endswith("/tools/knowledge_state.py") for name in names):
            raise ValueError("Wheel is missing required consumer payload")
    with tarfile.open(sources[0], "r:gz") as archive:
        names = {"/".join(name.split("/")[1:]) for name in archive.getnames()}
        required = {
            "docs/index.md",
            "docs/architecture.md",
            "docs/user/installation-modes.md",
            "docs/development/knowledge-design.md",
            "REPOSITORY_STRUCTURE.md",
            "TODO.md",
            "scripts/version.py",
            "repository-standard.json",
            "standards/repository/v1/bundle.json",
            "standards/repository/v1/contract.json",
            "scripts/check_repository_standard.py",
            "scripts/verify_quality_evidence.py",
            "scripts/publish_version.py",
            ".github/workflows/version.yml",
        }
        if not required <= names:
            raise ValueError("Source distribution is missing maintenance guides or helpers")
    with tempfile.TemporaryDirectory(prefix="codebase-agent-setup-release-") as temporary:
        environment = Path(temporary) / "environment"
        subprocess.run([sys.executable, "-m", "venv", str(environment)], check=True, timeout=120)
        binary = environment / ("Scripts" if os.name == "nt" else "bin")
        python = binary / ("python.exe" if os.name == "nt" else "python")
        subprocess.run([str(python), "-m", "pip", "install", "--no-deps", str(wheels[0])], check=True, timeout=120)
        launcher = binary / ("codebase-agent-setup.exe" if os.name == "nt" else "codebase-agent-setup")
        result = subprocess.run(
            [str(launcher), "--version"], cwd=temporary, check=True, capture_output=True, text=True, encoding="utf-8"
        )
        if json.loads(result.stdout)["version"] != version:
            raise ValueError("Installed wheel version does not match release")
        subprocess.run(
            [str(launcher), "configure", "inspect", "--user-config", str(Path(temporary) / "absent.json")],
            cwd=temporary,
            check=True,
            capture_output=True,
            timeout=60,
        )
    write_provenance(output, version=version, commit=commit, tag=args.tag, dirty=dirty)
    manifest = "".join(
        hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.name + "\n"
        for path in sorted(wheels + sources + [output / "provenance.json"])
    )
    (output / "SHA256SUMS").write_text(manifest, encoding="utf-8")
    verify_manifest(output)
    print(f"Validated release artifacts in {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
