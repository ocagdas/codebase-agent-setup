#!/usr/bin/env python3
"""Install the tool-neutral agent guide into a repository; protect existing files."""

import argparse
import re
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import datetime

from .resources import RESOURCE_ROOT as ROOT
from .project.ai_workflow.tools.settings import resolve
from . import install_transaction

# Where this installer records what it manages. Never inside a directory another tool owns.
LEDGER = install_transaction.STATE + "/install.json"
# Seeded once, then owned by the repository: never replaced, never recorded as managed.
INSTALL_ONCE = frozenset({"ai_workflow/project_guide.md"})
GUIDE = "ai_workflow/project_guide.md"
# Tool entry files that --adopt migrates into the project guide.
POINTERS = ("AGENTS.md", "CLAUDE.md", "GEMINI.md", ".github/copilot-instructions.md", ".cursor/rules/engineering.mdc")
REFERENCE = re.compile(r"\]\(([^)\s#]+\.md)(?:#[^)]*)?\)|`([^`\s]+\.md)`")
EXCLUSIONS = (
    "/.cbsetup/install.lock",
    "/.cbsetup/transaction/",
    "/.cbsetup/retired-*/",
    ".ai_cache/",
    ".ai_migration_backup/",
    "/ai_workflow/settings.local.json",
)


def adopt(target, stage, incoming):
    """Append authored pointer text to the staged guide; return adopted paths and referenced guidance."""
    adopted, referenced = [], set()
    for relative in POINTERS:
        path = target / relative
        # Symlinks and non-files stay collisions for the normal conflict check.
        if relative not in incoming or path.is_symlink() or not path.is_file():
            continue
        if digest(path) == digest(incoming[relative]):
            continue
        text = path.read_text(encoding="utf-8")
        with (stage / GUIDE).open("a", encoding="utf-8") as guide:
            guide.write(f"\n## Imported from {relative} (review)\n\n{text.rstrip()}\n")
        adopted.append(relative)
        for match in REFERENCE.finditer(text):
            # Markdown links are relative to the file; backticked paths conventionally name repository paths.
            reference = (path.parent / match[1] if match[1] else target / match[2]).resolve()
            try:
                name = reference.relative_to(target).as_posix()
            except ValueError:
                continue
            if reference.is_file() and name not in POINTERS and name != "AI_CONTEXT.md":
                referenced.add(name)
    return adopted, sorted(referenced)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def files(root):
    return [
        p
        for p in root.rglob("*")
        if p.is_file() and ".git" not in p.relative_to(root).parts and "__pycache__" not in p.parts
    ]


def read_ledger(path):
    if not path.exists():
        return {}
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("Invalid installation ledger; no target writes made")
    ledger = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(ledger, dict)
        or ledger.get("schema_version") != "1.0"
        or not isinstance(ledger.get("files"), dict)
        or any(
            not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value) for value in ledger["files"].values()
        )
    ):
        raise RuntimeError("Invalid installation ledger; no target writes made")
    return ledger


def install(args):
    target = args.repo.resolve()
    install_transaction.recover(target, apply=args.apply)
    upgrade = getattr(args, "upgrade", False)
    if getattr(args, "remove_obsolete", False) and not upgrade:
        raise RuntimeError("--remove-obsolete requires --upgrade, which establishes what this installer manages")
    overrides = {"agent": {"integrations": args.integration}} if args.integration else {}
    effective = resolve(target, getattr(args, "user_config", None), overrides)["settings"]
    integrations = list(dict.fromkeys(effective["agent"]["integrations"]))
    with tempfile.TemporaryDirectory(prefix="cbsetup_stage_") as temp:
        stage = Path(temp) / "project"
        stage.mkdir()
        for source in files(ROOT / "project"):
            relative = source.relative_to(ROOT / "project")
            dest = stage / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
        # Install-once files belong to the repository after seeding; an existing copy is never replaced.
        keep_existing = sorted(
            relative
            for relative in INSTALL_ONCE
            if (target / relative).is_file() and not (target / relative).is_symlink()
        )
        for relative in keep_existing:
            (stage / relative).unlink()
        incoming = {p.relative_to(stage).as_posix(): p for p in files(stage)}
        adopted, referenced = [], []
        if getattr(args, "adopt", False):
            if GUIDE in keep_existing:
                raise RuntimeError(
                    f"No target writes made: {GUIDE} already exists; merge remaining entry files into it by hand"
                )
            adopted, referenced = adopt(target, stage, incoming)
        conflicts = []
        # Carry the planning snapshot into the transaction; editors do not acquire our lock.
        observed = {
            name: install_transaction.digest(install_transaction.checked_path(target, name))
            for name in set(incoming) | {".gitignore", LEDGER}
        }
        ledger = read_ledger(target / LEDGER)
        if upgrade and not ledger:
            raise RuntimeError(
                "Upgrade needs an installation ledger from this installer; preserve/merge older installations manually"
            )
        replacements = []
        preserved = []
        for relative, source in incoming.items():
            dest = target / relative
            if any(parent.is_symlink() for parent in [dest, *dest.parents] if parent != Path("/")):
                conflicts.append(relative + " (symlink in destination)")
            elif dest.exists() and relative not in adopted:
                if not dest.is_file() or digest(dest) != digest(source):
                    previous_hash = ledger.get("files", {}).get(relative)
                    if upgrade and dest.is_file() and previous_hash and digest(dest) == previous_hash:
                        replacements.append(relative)
                    elif upgrade and dest.is_file():
                        # Authored files remain authoritative; report every retained difference.
                        preserved.append(relative)
                    else:
                        conflicts.append(relative)
        ignore_target = target / ".gitignore"
        if ignore_target.is_symlink() or (ignore_target.exists() and not ignore_target.is_file()):
            conflicts.append(".gitignore (not a regular file)")
        if conflicts:
            raise RuntimeError("No target writes made. Resolve these collisions:\n" + "\n".join(sorted(set(conflicts))))
        # Managed files the payload no longer ships.
        dropped = set(ledger.get("files", {})) - set(incoming)
        removable, obsolete_modified = [], []
        for relative in sorted(dropped):
            path = target / relative
            if path.is_symlink() or (path.exists() and not path.is_file()):
                obsolete_modified.append(relative)
            elif not path.exists():
                removable.append(relative)  # Already gone; only the ledger entry remains.
            elif digest(path) == ledger["files"][relative]:
                removable.append(relative)
            else:
                obsolete_modified.append(relative)
        removals = removable if getattr(args, "remove_obsolete", False) else []
        for relative in removals:
            observed.setdefault(
                relative, install_transaction.digest(install_transaction.checked_path(target, relative))
            )
        plan = {
            "target": str(target),
            "integrations": integrations,
            "files_to_install": len(incoming),
            "apply": args.apply,
            "upgrade": upgrade,
            "keep_existing": keep_existing,
            "adopted": adopted,
            "referenced_guidance": referenced,
            "replace_unmodified": replacements,
            "preserve_authored": preserved,
            "retain_obsolete": sorted(dropped - set(removals)),
            "removed_obsolete": removals,
            "obsolete_modified": obsolete_modified,
        }
        print(json.dumps(plan, indent=2))
        if not args.apply:
            return
        target.mkdir(parents=True, exist_ok=True)
        backup = (
            target / ".ai_migration_backup" / datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        )
        writes = {
            relative: source
            for relative, source in incoming.items()
            if relative not in preserved and observed[relative] != digest(source)
        }
        for relative in removals:
            path = target / relative
            if path.is_file():
                archived = stage / ".obsolete" / relative
                archived.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, archived)
                writes[(backup / relative).relative_to(target).as_posix()] = archived
            writes[relative] = None
        for relative in adopted:
            original = stage / ".adopted" / relative
            original.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target / relative, original)
            writes[(backup / relative).relative_to(target).as_posix()] = original
        ignore = target / ".gitignore"
        existing = ignore.read_text(encoding="utf-8") if ignore.exists() else ""
        missing = [line for line in EXCLUSIONS if line not in existing.splitlines()]
        if missing:
            staged_ignore = stage / ".install-ignore"
            staged_ignore.write_text(existing.rstrip("\n") + "\n" + "\n".join(missing) + "\n", encoding="utf-8")
            writes[".gitignore"] = staged_ignore
        manifest_files = dict(ledger.get("files", {}))
        for relative in removals:
            manifest_files.pop(relative, None)
        manifest_files.update(
            {
                relative: digest(source)
                for relative, source in incoming.items()
                if relative not in preserved and relative not in INSTALL_ONCE
            }
        )
        staged_ledger = stage / ".install-ledger"
        install_transaction.write_json(
            staged_ledger,
            {
                "schema_version": "1.0",
                "files": manifest_files,
                "preserved_authored": preserved,
                "install_once": sorted(INSTALL_ONCE),
            },
        )
        writes[LEDGER] = staged_ledger
        install_transaction.apply_writes(target, writes, expected=observed)
        print(
            "Installed the agent guide. Fill in ai_workflow/project_guide.md and set handover.path "
            "before implementation."
        )


def add_arguments(parser):
    parser.add_argument("repo", type=Path)
    parser.add_argument("--integration", action="append", choices=["codex", "cursor-agent", "copilot"])
    parser.add_argument("--user-config", type=Path)
    parser.add_argument(
        "--upgrade",
        action="store_true",
        help="Preview/apply updates only to unchanged managed files; preserve authored differences",
    )
    parser.add_argument(
        "--remove-obsolete",
        action="store_true",
        help="With --upgrade, archive and delete managed files the payload no longer ships; "
        "locally edited ones are always kept and reported",
    )
    parser.add_argument("--apply", action="store_true", help="Apply the validated staging plan")
    parser.add_argument(
        "--adopt",
        action="store_true",
        help="Move authored AGENTS.md/CLAUDE.md/GEMINI.md/Copilot/Cursor entry text into "
        "ai_workflow/project_guide.md for review, back up the originals and install the standard pointers",
    )
    return parser


def main(argv=None):
    parser = add_arguments(argparse.ArgumentParser())
    args = parser.parse_args(argv)
    try:
        install(args)
        return 0
    except (RuntimeError, OSError, ValueError) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
