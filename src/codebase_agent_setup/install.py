#!/usr/bin/env python3
"""Stage official Spec Kit and engineering additions; protect existing files."""

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
from . import toolchains, install_transaction


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def files(root):
    return [
        p
        for p in root.rglob("*")
        if p.is_file() and ".git" not in p.relative_to(root).parts and "__pycache__" not in p.parts
    ]


def install(args):
    toolchains.check_export_path(getattr(args, "export_record", None))
    target = args.repo.resolve()
    install_transaction.recover(target, apply=args.apply)
    if getattr(args, "export_record", None) and not args.apply:
        raise RuntimeError("--export-record requires --apply")
    overrides = {"agent": {"integrations": args.integration}} if args.integration else {}
    if getattr(args, "speckit_ref", None):
        overrides["speckit"] = {"ref": args.speckit_ref}
    effective = resolve(target, getattr(args, "user_config", None), overrides)["settings"]
    integrations = list(dict.fromkeys(effective["agent"]["integrations"]))
    selection = toolchains.resolve_selection(effective["speckit"]["ref"], getattr(args, "toolchain_record", None))
    specify = toolchains.discover_cli(effective, selection, args.specify)
    with tempfile.TemporaryDirectory(prefix="engineering_stage_") as temp:
        stage, compatibility = toolchains.stage_package(specify, integrations, selection, temp)
        for source in files(ROOT / "project"):
            dest = stage / source.relative_to(ROOT / "project")
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
        incoming = {p.relative_to(stage).as_posix(): p for p in files(stage)}
        legacy = json.loads((ROOT / "legacy_v6_files.json").read_text(encoding="utf-8"))
        retirement = []
        conflicts = []
        # Carry the planning snapshot into the transaction; editors do not acquire our lock.
        observed = {
            name: install_transaction.digest(install_transaction.checked_path(target, name))
            for name in set(incoming)
            | (set(legacy) if args.migrate_v6 else set())
            | {".gitignore", ".specify/engineering-install.json"}
        }
        ledger_path = target / ".specify/engineering-install.json"
        ledger = {}
        if ledger_path.exists():
            if ledger_path.is_symlink() or not ledger_path.is_file():
                raise RuntimeError("Invalid installation ledger; no target writes made")
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
            if (
                not isinstance(ledger, dict)
                or ledger.get("schema_version") != "1.0"
                or not isinstance(ledger.get("files"), dict)
                or any(
                    not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
                    for value in ledger["files"].values()
                )
            ):
                raise RuntimeError("Invalid installation ledger; no target writes made")
        if getattr(args, "upgrade", False) and not ledger:
            raise RuntimeError(
                "Upgrade needs an installation ledger from this installer; preserve/merge older installations manually"
            )
        replacements = []
        preserved = []
        if args.migrate_v6:
            for relative, expected in legacy.items():
                path = target / relative
                if path.exists():
                    if path.is_symlink() or not path.is_file() or digest(path) != expected:
                        conflicts.append(relative + " (modified legacy file; map custom values manually)")
                    else:
                        retirement.append(relative)
        for relative, source in incoming.items():
            dest = target / relative
            if any(parent.is_symlink() for parent in [dest, *dest.parents] if parent != Path("/")):
                conflicts.append(relative + " (symlink in destination)")
            elif dest.exists() and relative not in retirement:
                if not dest.is_file() or digest(dest) != digest(source):
                    previous_hash = ledger.get("files", {}).get(relative)
                    if (
                        getattr(args, "upgrade", False)
                        and dest.is_file()
                        and previous_hash
                        and digest(dest) == previous_hash
                    ):
                        replacements.append(relative)
                    elif getattr(args, "upgrade", False) and dest.is_file():
                        # Authored files remain authoritative; report every retained difference.
                        preserved.append(relative)
                    else:
                        conflicts.append(relative)
        ignore_target = target / ".gitignore"
        if ignore_target.is_symlink() or (ignore_target.exists() and not ignore_target.is_file()):
            conflicts.append(".gitignore (not a regular file)")
        if conflicts:
            raise RuntimeError("No target writes made. Resolve these collisions:\n" + "\n".join(sorted(set(conflicts))))
        plan = {
            "target": str(target),
            "integrations": integrations,
            "files_to_install": len(incoming),
            "legacy_files_to_archive": len(retirement),
            "apply": args.apply,
            "toolchain": selection,
            "compatibility": compatibility,
            "upgrade": getattr(args, "upgrade", False),
            "replace_unmodified": replacements,
            "preserve_authored": preserved,
            "retain_obsolete": sorted(set(ledger.get("files", {})) - set(incoming)),
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
            if relative not in preserved and (relative in retirement or observed[relative] != digest(source))
        }
        for relative in retirement:
            archived = stage / ".retired" / relative
            archived.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target / relative, archived)
            writes[(backup / relative).relative_to(target).as_posix()] = archived
            if relative not in incoming:
                writes[relative] = None
        ignore = target / ".gitignore"
        existing = ignore.read_text(encoding="utf-8") if ignore.exists() else ""
        exclusions = [
            "/.specify/engineering-install.lock",
            "/.specify/engineering-transaction/",
            "/.specify/engineering-retired-*/",
            ".ai_cache/",
            ".codegraphcontext/",
            ".ai_migration_backup/",
            "/ai_workflow/settings.local.json",
        ]
        missing = [line for line in exclusions if line not in existing.splitlines()]
        if missing:
            staged_ignore = stage / ".install-ignore"
            staged_ignore.write_text(existing.rstrip("\n") + "\n" + "\n".join(missing) + "\n", encoding="utf-8")
            writes[".gitignore"] = staged_ignore
        manifest_files = dict(ledger.get("files", {}))
        manifest_files.update(
            {relative: digest(source) for relative, source in incoming.items() if relative not in preserved}
        )
        staged_ledger = stage / ".install-ledger"
        toolchains.write_record(
            staged_ledger,
            {
                "schema_version": "1.0",
                "toolchain": selection,
                "compatibility": compatibility,
                "files": manifest_files,
                "preserved_authored": preserved,
            },
        )
        writes[".specify/engineering-install.json"] = staged_ledger
        install_transaction.apply_writes(target, writes, expected=observed)
        if getattr(args, "export_record", None):
            toolchains.write_record(args.export_record, {**selection, "compatibility": compatibility})
        print(
            "Installed official Spec Kit plus engineering customisations. Configure project commands before implementation."
        )


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", type=Path)
    parser.add_argument("--integration", action="append", choices=["codex", "cursor-agent", "copilot"])
    parser.add_argument("--user-config", type=Path)
    parser.add_argument("--specify", default=None)
    parser.add_argument("--speckit-ref", help="Official release or full commit")
    parser.add_argument("--toolchain-record", type=Path, help="Import exact toolchain source")
    parser.add_argument("--export-record", type=Path, help="Export checked toolchain record after apply")
    parser.add_argument(
        "--upgrade",
        action="store_true",
        help="Preview/apply updates only to unchanged managed files; preserve authored differences",
    )
    parser.add_argument("--apply", action="store_true", help="Apply the validated staging plan")
    parser.add_argument("--migrate-v6", action="store_true", help="Archive only recognised unchanged v6 template files")
    args = parser.parse_args(argv)
    try:
        install(args)
        return 0
    except (RuntimeError, OSError, ValueError) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
