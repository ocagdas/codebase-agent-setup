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
from . import install_transaction, templates

# Where this installer records what it manages. Never inside a directory another tool owns.
LEDGER = install_transaction.STATE + "/install.json"
# Seeded once, then repository-owned: only explicit override replaces it; never managed.
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
# Root-relative installed copies, not the reusable templates under project/.
# State/backups remain private even when guidance is intentionally shared.
LOCAL_EXCLUSIONS = (
    "/AI_CONTEXT.md",
    "/AGENTS.md",
    "/CLAUDE.md",
    "/GEMINI.md",
    "/ai_workflow/",
    "/.cbsetup/",
    "/.github/copilot-instructions.md",
    "/.cursor/rules/engineering.mdc",
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
    template_path = getattr(args, "template", None)
    source_template = templates.snapshot(template_path, target=target) if template_path is not None else None
    behaviour = getattr(args, "behaviour", None)
    legacy_replace = getattr(args, "replace_guide", False)
    if legacy_replace and (source_template is None or getattr(args, "adopt", False)):
        raise RuntimeError("--replace-guide requires --template and cannot be combined with --adopt")
    override = behaviour == "override"
    preserve = behaviour == "preserve"
    replace_guide = override or legacy_replace
    if override and getattr(args, "adopt", False):
        raise RuntimeError("--behaviour override cannot be combined with --adopt")
    install_transaction.recover(target, apply=args.apply)
    upgrade = behaviour == "upgrade" or (behaviour is None and getattr(args, "upgrade", False))
    if getattr(args, "remove_obsolete", False) and not upgrade:
        raise RuntimeError("--remove-obsolete requires upgrade behaviour (--behaviour upgrade / --upgrade)")
    overrides = {"agent": {"integrations": args.integration}} if args.integration else {}
    effective = resolve(target, getattr(args, "user_config", None), overrides)["settings"]
    integrations = list(dict.fromkeys(effective["agent"]["integrations"]))
    with tempfile.TemporaryDirectory(prefix="cbsetup_stage_") as temp:
        stage = Path(temp) / "project"
        stage.mkdir()
        if source_template is not None:
            for relative, content in source_template.files.items():
                dest = stage / relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(content)
        else:
            for source in files(ROOT / "project"):
                relative = source.relative_to(ROOT / "project")
                dest = stage / relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, dest)
        # Repository-owned files are kept unless replacement was explicitly requested.
        keep_existing = sorted(
            relative
            for relative in INSTALL_ONCE
            if (target / relative).is_file() and not (target / relative).is_symlink() and not replace_guide
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
        if upgrade and not ledger and behaviour is None:
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
                    if dest.is_file() and (override or (relative == GUIDE and replace_guide)):
                        replacements.append(relative)
                    elif upgrade and dest.is_file() and previous_hash and digest(dest) == previous_hash:
                        replacements.append(relative)
                    elif (upgrade or preserve) and dest.is_file():
                        # Authored files remain authoritative; report every retained difference.
                        preserved.append(relative)
                    else:
                        conflicts.append(relative)
        ignore_target = target / ".gitignore"
        if ignore_target.is_symlink() or (ignore_target.exists() and not ignore_target.is_file()):
            conflicts.append(".gitignore (not a regular file)")
        if conflicts:
            raise RuntimeError("No target writes made. Resolve these collisions:\n" + "\n".join(sorted(set(conflicts))))
        local_only = not getattr(args, "track_guidance", False)
        existing_ignore = ignore_target.read_text(encoding="utf-8") if ignore_target.exists() else ""
        exclusions = EXCLUSIONS + (LOCAL_EXCLUSIONS if local_only else ("/.cbsetup/",))
        missing_ignore = [line for line in exclusions if line not in existing_ignore.splitlines()]
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
            "behaviour": behaviour or ("upgrade" if upgrade else "preserve"),
            "template": str(source_template.root) if source_template else None,
            "template_fingerprint": source_template.fingerprint if source_template else None,
            "replace_guide": replace_guide,
            "local_only": local_only,
            "gitignore_additions": missing_ignore,
            "privacy_warning": "Ignore rules do not untrack existing files, erase Git history, or prevent "
            "cloud tools from reading files. Never put credentials in guidance. "
            "--track-guidance does not remove existing ignore rules.",
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
        if override or legacy_replace:
            backup_files = replacements if override else ([GUIDE] if GUIDE in writes else [])
            for relative in backup_files:
                if not (target / relative).is_file():
                    continue
                original = stage / ".overridden" / relative
                original.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target / relative, original)
                writes[(backup / relative).relative_to(target).as_posix()] = original
        if missing_ignore:
            staged_ignore = stage / ".install-ignore"
            staged_ignore.write_text(
                existing_ignore.rstrip("\n") + "\n" + "\n".join(missing_ignore) + "\n", encoding="utf-8"
            )
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
        if source_template is not None:
            templates.verify(source_template)
        install_transaction.apply_writes(target, writes, expected=observed)
        print(
            "Installed the agent guide. Fill in ai_workflow/project_guide.md and set handover.path "
            "before implementation."
        )


def add_arguments(parser):
    parser.add_argument("repo", type=Path)
    parser.add_argument("--integration", action="append", choices=["codex", "cursor-agent", "copilot"])
    parser.add_argument("--user-config", type=Path)
    parser.add_argument("--template", type=Path, help="Install from a validated editable template directory")
    add_behaviour_arguments(parser)
    parser.add_argument(
        "--track-guidance",
        action="store_true",
        help="Opt into sharing installed guidance: do not add its local-only .gitignore rules. "
        "Install state/backups/local settings stay ignored; existing rules and tracked files are not untracked",
    )
    parser.add_argument(
        "--remove-obsolete",
        action="store_true",
        help="With upgrade behaviour, archive and delete managed files the payload no longer ships; "
        "locally edited ones are always kept and reported",
    )
    add_write_arguments(parser)
    parser.add_argument(
        "--adopt",
        action="store_true",
        help="Move authored AGENTS.md/CLAUDE.md/GEMINI.md/Copilot/Cursor entry text into "
        "ai_workflow/project_guide.md for review, back up the originals and install the standard pointers",
    )
    return parser


def add_write_arguments(parser):
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", dest="apply", action="store_false", help="Validate and preview; write nothing")
    group.add_argument("--apply", dest="apply", action="store_true", help=argparse.SUPPRESS)
    parser.set_defaults(apply=True)


def add_behaviour_arguments(parser):
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--behaviour",
        choices=("preserve", "upgrade", "override"),
        default="upgrade",
        help="preserve: add missing files; upgrade (default): update unchanged managed files; "
        "override: replace supported files, including the guide, with backups",
    )
    group.add_argument("--upgrade", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--replace-guide", action="store_true", help=argparse.SUPPRESS)


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
