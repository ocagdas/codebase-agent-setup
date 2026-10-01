"""Operate on many repositories at once.

A fleet file lists the repositories one person or team maintains, each with the
publication policy that governs how freely a tool may act on it. `status` answers
"is every repository still in the state I think it is" in one call; `apply` brings
them all up to the current payload without ever touching a repository whose policy
says a human does that.

The file is JSON, not YAML, because this tool has no runtime dependencies and the
standard library does not read YAML.
"""

import argparse
import contextlib
import io
import json
from pathlib import Path
from typing import NamedTuple

from . import install

SCHEMA_VERSION = "1.0"
DEFAULT_NAME = "fleet.json"
# How freely automation may act on a repository. "owner-only" means a human performs
# publication there, so mass operations skip it unless explicitly included.
POLICIES = ("open", "owner-only")
UNFILLED = "<!-- cbsetup:unfilled -->"


class FleetError(ValueError):
    pass


class Entry(NamedTuple):
    path: Path
    publication: str

    @property
    def name(self):
        return self.path.name


class Options(NamedTuple):
    apply: bool = False
    upgrade: bool = False
    include_owner_only: bool = False
    user_config: Path = None


def load(path):
    path = Path(path)
    if not path.is_file():
        raise FleetError(
            f"No fleet file at {path}. Create a {DEFAULT_NAME} listing your repositories, for example:\n"
            '{"schema_version": "1.0", "repositories": [{"path": "~/code/app", "publication": "owner-only"}]}'
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise FleetError(f"{path} is not valid JSON: {error}") from error
    if not isinstance(data, dict) or not isinstance(data.get("repositories"), list):
        raise FleetError(f"{path} must be an object with a 'repositories' list")
    version = str(data.get("schema_version", ""))
    if version.split(".")[0] > SCHEMA_VERSION.split(".")[0]:
        raise FleetError(
            f"{path} uses fleet schema {version}, which is newer than this tool understands ({SCHEMA_VERSION})"
        )
    entries, seen = [], set()
    for item in data["repositories"]:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise FleetError(f"{path}: every repository needs a 'path' string")
        policy = item.get("publication", "open")
        if policy not in POLICIES:
            raise FleetError(f"{path}: unknown publication policy {policy!r}; use one of {', '.join(POLICIES)}")
        # Relative paths follow the file that declares them, so a fleet file is portable.
        resolved = Path(item["path"]).expanduser()
        resolved = (resolved if resolved.is_absolute() else path.parent / resolved).resolve()
        if resolved in seen:
            raise FleetError(f"{path}: {resolved} is listed twice")
        seen.add(resolved)
        entries.append(Entry(resolved, policy))
    return entries


def ledger_of(repo):
    try:
        return install.read_ledger(repo / install.LEDGER)
    except (RuntimeError, OSError, ValueError):
        return {}


def status(entries):
    rows = []
    for entry in entries:
        row = {
            "repository": entry.name,
            "path": str(entry.path),
            "publication": entry.publication,
            "exists": entry.path.is_dir(),
            "installed": False,
            "managed": 0,
            "drift": [],
            "missing": [],
            "guide_filled": False,
        }
        if row["exists"]:
            ledger = ledger_of(entry.path)
            managed = ledger.get("files", {})
            row["installed"] = bool(managed)
            row["managed"] = len(managed)
            for relative, recorded in sorted(managed.items()):
                path = entry.path / relative
                if not path.exists():
                    row["missing"].append(relative)
                elif not path.is_file() or install.digest(path) != recorded:
                    row["drift"].append(relative)
            guide = entry.path / install.GUIDE
            row["guide_filled"] = guide.is_file() and UNFILLED not in guide.read_text(encoding="utf-8")
        rows.append(row)
    return rows


def apply(entries, options):
    result = {
        "apply": options.apply,
        "upgrade": options.upgrade,
        "repositories": [],
        "skipped_owner_only": [],
        "skipped_missing": [],
        "failed": [],
    }
    for entry in entries:
        if entry.publication == "owner-only" and not options.include_owner_only:
            result["skipped_owner_only"].append(entry.name)
            continue
        if not entry.path.is_dir():
            result["skipped_missing"].append(entry.name)
            continue
        args = argparse.Namespace(
            repo=entry.path,
            integration=None,
            user_config=options.user_config,
            upgrade=options.upgrade,
            apply=options.apply,
            adopt=False,
            remove_obsolete=False,
        )
        captured = io.StringIO()
        try:
            with contextlib.redirect_stdout(captured):
                install.install(args)
        except (RuntimeError, OSError, ValueError) as error:
            # One repository's collision must not abandon the rest of the fleet.
            result["failed"].append({"repository": entry.name, "error": str(error)})
            continue
        plan, _ = json.JSONDecoder().raw_decode(captured.getvalue())
        result["repositories"].append({"repository": entry.name, **plan})
    return result


def table(rows):
    """A fixed-width table, because this is the one command meant to be read at a glance."""
    headers = ("repository", "policy", "managed", "drift", "missing", "guide")
    body = [
        (
            row["repository"],
            row["publication"],
            "-" if not row["exists"] else ("not installed" if not row["installed"] else str(row["managed"])),
            str(len(row["drift"])) if row["drift"] else "-",
            str(len(row["missing"])) if row["missing"] else "-",
            "filled" if row["guide_filled"] else "UNFILLED",
        )
        if row["exists"]
        else (row["repository"], row["publication"], "MISSING", "-", "-", "-")
        for row in rows
    ]
    widths = [max(len(headers[i]), *(len(line[i]) for line in body)) if body else len(headers[i]) for i in range(6)]
    lines = ["  ".join(header.ljust(widths[i]) for i, header in enumerate(headers))]
    lines.append("  ".join("-" * width for width in widths))
    lines.extend("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(line)) for line in body)
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="cbsetup fleet", description=__doc__.splitlines()[0])
    parser.add_argument("--file", type=Path, default=Path(DEFAULT_NAME), help=f"Fleet file (default {DEFAULT_NAME})")
    parser.add_argument("--user-config", type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    look = sub.add_parser("status", help="One row per repository: managed files, drift, guide state")
    look.add_argument("--json", action="store_true", help="Machine-readable output instead of the table")
    act = sub.add_parser("apply", help="Install or upgrade the managed guide across the fleet")
    act.add_argument("--apply", action="store_true", help="Write the changes")
    act.add_argument(
        "--upgrade", action="store_true", help="Refresh unmodified managed files, preserving authored ones"
    )
    act.add_argument(
        "--include-owner-only",
        action="store_true",
        help="Also act on repositories whose publication policy reserves changes for a human",
    )
    args = parser.parse_args(argv)
    try:
        entries = load(args.file)
        if args.command == "status":
            rows = status(entries)
            print(json.dumps(rows, indent=2) if args.json else table(rows))
            return 0
        result = apply(
            entries,
            Options(
                apply=args.apply,
                upgrade=args.upgrade,
                include_owner_only=args.include_owner_only,
                user_config=args.user_config,
            ),
        )
        print(json.dumps(result, indent=2))
        return 1 if result["failed"] else 0
    except (FleetError, OSError) as error:
        parser.exit(1, str(error) + "\n")
