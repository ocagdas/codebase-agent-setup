"""Capture, inspect and replay the ungittable half of an agent setup.

A capsule is a manifest plus the files it describes. The manifest is the source of
truth: it carries provenance, a digest per file and the list of secrets that were
removed, so a capsule can be reviewed, diffed and partially applied instead of being
an opaque archive somebody has to trust.

Paths are never carried literally across machines. Each entry names the *tool* it
belongs to, and the target path is recomputed on the receiving host. That is why an
arbitrary --include is marked host_specific: CAS can relocate what it knows about,
and nothing else.
"""

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from typing import NamedTuple
import zipfile

from . import redact

SCHEMA_VERSION = "1.0"
MANIFEST = "manifest.json"
FILES = "files"


class CapsuleError(ValueError):
    pass


class ToolPath(NamedTuple):
    """A tool directory CAS knows how to find on any supported host."""

    tool: str
    relative: str  # Relative to the user's home directory on POSIX hosts.
    windows: str  # Relative to %APPDATA% (or its default) on Windows.
    names: tuple  # The files inside it a capsule carries.


# CAS's own knowledge of the tools it manages, not user configuration. Adding a tool
# here is what makes its settings portable between a Mac, a Linux box and Windows.
TOOL_PATHS = (
    ToolPath("claude", ".claude", "Claude", ("settings.json", "CLAUDE.md")),
    ToolPath("codex", ".codex", "Codex", ("config.toml", "AGENTS.md")),
    ToolPath("cursor", ".cursor", "Cursor", ("mcp.json",)),
    ToolPath("gemini", ".gemini", "Gemini", ("settings.json",)),
)
USER_CONFIG = ToolPath("cbsetup", ".config/codebase-agent-setup", "codebase-agent-setup", ("config.json",))
# Repository files that are deliberately never committed but are needed again on a clone.
REPO_FILES = ("ai_workflow/settings.local.json", ".cbsetup/install.json")


class Request(NamedTuple):
    home: Path
    repos: tuple = ()
    out: Path = None  # A .zip path; the default format.
    out_dir: Path = None  # A plain folder, for inspection, rsync and git.
    include: tuple = ()
    exclude: tuple = ()


class Target(NamedTuple):
    home: Path
    repo: Path = None
    apply: bool = False
    overwrite: bool = False
    force_host: bool = False


class Reported(NamedTuple):
    entry: str
    removal: redact.Removal


class Result(NamedTuple):
    location: Path
    entries: list
    redactions: list


def host_class():
    if os.name == "nt":
        return "windows"
    return "darwin" if sys.platform == "darwin" else "linux"


def digest_bytes(data):
    return hashlib.sha256(data).hexdigest()


def tool_root(spec, home, *, windows=None):
    """Where this tool keeps its files on the given host, recomputed rather than carried."""
    if windows if windows is not None else os.name == "nt":
        appdata = os.environ.get("APPDATA") if Path(home).resolve() == Path.home().resolve() else None
        return Path(appdata or Path(home) / "AppData/Roaming") / spec.windows
    return Path(home) / spec.relative


def refuse_sweep(path, home):
    """A whole-home capture is never allowed, not even behind a flag."""
    raw = Path(path)
    if any(character in str(raw) for character in "*?[") or str(raw) in ("~", "~/"):
        raise CapsuleError(f"Refusing a glob or home shorthand in --include: {raw}. Name individual files.")
    resolved = raw.expanduser()
    resolved = resolved if resolved.is_absolute() else (Path.cwd() / resolved)
    resolved = resolved.resolve()
    for boundary in (Path(home).resolve(), Path.home().resolve(), Path(resolved.anchor)):
        if resolved == boundary:
            raise CapsuleError(
                f"Refusing to capture {resolved} as a whole. A capsule carries named files, never a directory sweep."
            )
    return resolved


def capture(path, name, origin, *, host_specific, target_hint):
    """Read, redact and describe one file. Returns (entry, text, removals)."""
    text, removals = redact.text_bytes(Path(path).read_bytes(), name)
    entry = {
        "path": name,
        "origin": origin,
        "source": str(path),
        "target_hint": target_hint,
        "sha256": digest_bytes(text.encode("utf-8")),
        "redactions": [{"location": r.location, "reason": r.reason} for r in removals],
        "host_specific": host_specific,
        "mode": "file",
    }
    return entry, text, removals


def collect(request):
    """Walk the three capture layers into (entries, contents, redactions)."""
    excluded = {Path(p).expanduser().resolve() for p in request.exclude}
    entries, contents, reported = [], {}, []

    def add(path, name, origin, *, host_specific=False, target_hint=None):
        path = Path(path)
        if not path.is_file() or path.is_symlink() or path.resolve() in excluded:
            return
        entry, text, removals = capture(path, name, origin, host_specific=host_specific, target_hint=target_hint)
        entries.append(entry)
        contents[name] = text
        reported.extend(Reported(name, removal) for removal in removals)

    root = tool_root(USER_CONFIG, request.home)
    for filename in USER_CONFIG.names:
        add(root / filename, f"user-config/{filename}", "user-config", target_hint=filename)
    for spec in TOOL_PATHS:
        root = tool_root(spec, request.home)
        for filename in spec.names:
            add(root / filename, f"tool-global/{spec.tool}/{filename}", "tool-global", target_hint=filename)
    for repo in request.repos:
        repo = Path(repo).resolve()
        for relative in REPO_FILES:
            add(repo / relative, f"repo/{repo.name}/{relative}", "repo", target_hint=relative)
    for path in request.include:
        resolved = refuse_sweep(path, request.home)
        if not resolved.is_file():
            raise CapsuleError(f"--include {resolved} is not a file")
        # CAS cannot relocate a path it does not know, so it travels marked.
        add(resolved, f"include/{resolved.name}", "include", host_specific=True, target_hint=resolved.name)
    if not entries:
        return entries, contents, reported
    return entries, contents, reported


def manifest_for(entries):
    return {
        "schema_version": SCHEMA_VERSION,
        "created": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "host_class": host_class(),
        "entries": entries,
    }


def create(request):
    if request.out and request.out_dir:
        raise CapsuleError("Choose one of --out (zip) or --out-dir (folder)")
    entries, contents, reported = collect(request)
    if not entries:
        raise CapsuleError("There is nothing to capture: no known tool files, user config or repository state found")
    manifest = manifest_for(sorted(entries, key=lambda entry: entry["path"]))
    rendered = json.dumps(manifest, indent=2) + "\n"
    if request.out_dir:
        location = Path(request.out_dir)
        if location.exists() and any(location.iterdir()):
            raise CapsuleError(f"{location} is not empty; choose an empty directory")
        (location / FILES).mkdir(parents=True, exist_ok=True)
        (location / MANIFEST).write_text(rendered, encoding="utf-8")
        for name, text in contents.items():
            path = location / FILES / name
            path.parent.mkdir(parents=True, exist_ok=True)
            # Match the hashed bytes and ZIP representation on every host; text
            # writes otherwise translate LF to CRLF on Windows.
            path.write_bytes(text.encode("utf-8"))
    else:
        location = Path(request.out or "cbsetup-capsule.zip")
        if location.exists():
            raise CapsuleError(f"{location} already exists; capsules are never overwritten in place")
        location.parent.mkdir(parents=True, exist_ok=True)
        # Deflated zip via the standard library: no tar, no subprocess, same on every host.
        with zipfile.ZipFile(location, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(MANIFEST, rendered)
            for name, text in contents.items():
                archive.writestr(f"{FILES}/{name}", text)
    return Result(location, manifest["entries"], reported)


def read_manifest(location):
    location = Path(location)
    if location.is_dir():
        raw = (location / MANIFEST).read_text(encoding="utf-8")
    elif zipfile.is_zipfile(location):
        with zipfile.ZipFile(location) as archive:
            raw = archive.read(MANIFEST).decode("utf-8")
    else:
        raise CapsuleError(f"{location} is neither a capsule folder nor a zip archive")
    try:
        manifest = json.loads(raw)
    except ValueError as error:
        raise CapsuleError(f"{location} has an unreadable manifest") from error
    if not isinstance(manifest, dict) or not isinstance(manifest.get("entries"), list):
        raise CapsuleError(f"{location} has an invalid manifest")
    version = str(manifest.get("schema_version", ""))
    if version.split(".")[0] > SCHEMA_VERSION.split(".")[0]:
        raise CapsuleError(
            f"{location} uses capsule schema {version}, which is newer than this tool understands ({SCHEMA_VERSION}); "
            "upgrade codebase-agent-setup"
        )
    return manifest


def read_file(location, name):
    location = Path(location)
    if location.is_dir():
        return (location / FILES / name).read_bytes()
    with zipfile.ZipFile(location) as archive:
        return archive.read(f"{FILES}/{name}")


def show(location):
    manifest = read_manifest(location)
    return {
        "location": str(location),
        "schema_version": manifest.get("schema_version"),
        "created": manifest.get("created"),
        "host_class": manifest.get("host_class"),
        "entries": [
            {
                "path": entry["path"],
                "origin": entry["origin"],
                "host_specific": entry.get("host_specific", False),
                "redactions": len(entry.get("redactions", [])),
            }
            for entry in manifest["entries"]
        ],
        "redactions": [
            {"entry": entry["path"], **removal}
            for entry in manifest["entries"]
            for removal in entry.get("redactions", [])
        ],
    }


def destination(entry, target):
    """Recompute where this entry belongs on this host; None when there is no target for it."""
    hint = entry.get("target_hint") or Path(entry["path"]).name
    relative = Path(hint)
    if relative.is_absolute() or ".." in relative.parts:
        raise CapsuleError(f"Capsule entry {entry['path']} names an unsafe target: {hint}")
    origin = entry["origin"]
    if origin == "user-config":
        return tool_root(USER_CONFIG, target.home) / relative
    if origin == "tool-global":
        tool = entry["path"].split("/")[1]
        spec = next((candidate for candidate in TOOL_PATHS if candidate.tool == tool), None)
        if spec is None:
            raise CapsuleError(f"Capsule entry {entry['path']} names a tool this version does not know: {tool}")
        return tool_root(spec, target.home) / relative
    if origin == "repo":
        return None if target.repo is None else Path(target.repo) / relative
    return Path(target.home) / relative  # An arbitrary include lands under home, by name.


def apply(location, target):
    manifest = read_manifest(location)
    foreign = manifest.get("host_class") != host_class()
    writes, replaced, skipped_host, skipped_target, restore = [], [], [], [], []
    staged = {}
    for entry in manifest["entries"]:
        if entry.get("host_specific") and foreign and not target.force_host:
            skipped_host.append(entry["path"])
            continue
        path = destination(entry, target)
        if path is None:
            skipped_target.append(entry["path"])
            continue
        data = read_file(location, entry["path"])
        if digest_bytes(data) != entry["sha256"]:
            raise CapsuleError(f"Capsule file {entry['path']} does not match its manifest digest; refusing to apply")
        if path.is_symlink():
            raise CapsuleError(f"Refusing to write through a symlink: {path}")
        if path.exists():
            if not path.is_file():
                raise CapsuleError(f"{path} exists and is not a regular file")
            if digest_bytes(path.read_bytes()) == entry["sha256"]:
                continue  # Already exactly this content.
            if not target.overwrite:
                raise CapsuleError(
                    f"{path} already exists with different content. Re-run with --overwrite to replace it, "
                    "or apply into a clean checkout."
                )
            replaced.append(str(path))
        else:
            writes.append(str(path))
        staged[path] = data
        restore.extend({"entry": entry["path"], **removal} for removal in entry.get("redactions", []))
    plan = {
        "capsule": str(location),
        "apply": target.apply,
        "home": str(target.home),
        "repo": None if target.repo is None else str(target.repo),
        "writes": writes,
        "replaced": replaced,
        "skipped_host_specific": skipped_host,
        "skipped_no_target": skipped_target,
        "restore_by_hand": restore,
    }
    if not target.apply:
        return plan
    # Everything is validated before the first byte lands.
    for path, data in staged.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(data)
            shutil.move(str(temporary), str(path))
            temporary = None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return plan


def report_redactions(removals, *, action):
    """Print every secret that was removed. This is never silent and never optional."""
    if not removals:
        print(f"No secrets were found to redact during {action}.")
        return
    print(f"\nRedacted {len(removals)} secret value(s) during {action}. Restore these yourself:")
    for item in removals:
        entry = item["entry"] if isinstance(item, dict) else item.entry
        location = item["location"] if isinstance(item, dict) else item.removal.location
        reason = item["reason"] if isinstance(item, dict) else item.removal.reason
        print(f"  {entry}: {location}  ({reason})")
    print("A capsule never carries credentials. Re-enter them by hand, or ask your agent to, after applying.")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="cbsetup capsule", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    make = sub.add_parser("create", help="Capture this machine's agent setup, always redacted")
    make.add_argument("--out", type=Path, help="Write a zip archive (the default format)")
    make.add_argument("--out-dir", type=Path, help="Write a plain folder instead, for inspection or rsync")
    make.add_argument("--repo", type=Path, action="append", default=[], help="Repository to capture; repeatable")
    make.add_argument("--include", type=Path, action="append", default=[], help="Extra file; never a directory")
    make.add_argument("--exclude", type=Path, action="append", default=[], help="File to leave out")

    look = sub.add_parser("show", help="Print a capsule's provenance and redactions without applying it")
    look.add_argument("capsule", type=Path)

    put = sub.add_parser("apply", help="Replay a capsule here; previews unless --apply is given")
    put.add_argument("capsule", type=Path)
    put.add_argument("--repo", type=Path, help="Repository to receive the repository layer")
    put.add_argument("--machine-only", action="store_true", help="Skip the repository layer entirely")
    put.add_argument("--apply", action="store_true", help="Write the files")
    put.add_argument("--overwrite", action="store_true", help="Replace files that exist with different content")
    put.add_argument("--force-host", action="store_true", help="Apply host-specific entries on a different host class")

    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            if not args.out and not args.out_dir:
                args.out = Path("cbsetup-capsule.zip")
            result = create(
                Request(
                    home=Path.home(),
                    repos=tuple(args.repo),
                    out=args.out,
                    out_dir=args.out_dir,
                    include=tuple(args.include),
                    exclude=tuple(args.exclude),
                )
            )
            print(json.dumps({"capsule": str(result.location), "entries": result.entries}, indent=2))
            report_redactions(result.redactions, action="capture")
        elif args.command == "show":
            print(json.dumps(show(args.capsule), indent=2))
        else:
            plan = apply(
                args.capsule,
                Target(
                    home=Path.home(),
                    repo=None if args.machine_only else args.repo,
                    apply=args.apply,
                    overwrite=args.overwrite,
                    force_host=args.force_host,
                ),
            )
            print(json.dumps(plan, indent=2))
            if args.apply:
                report_redactions(plan["restore_by_hand"], action="this capsule's capture")
    except (CapsuleError, redact.RedactionError, OSError) as error:
        parser.exit(1, str(error) + "\n")
    return 0
