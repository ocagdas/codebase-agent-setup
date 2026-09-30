#!/usr/bin/env python3
"""Check a handover document against the contract in ai_workflow/handover.md; stdlib only."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

try:
    from .settings import SettingsError, handover_location
except ImportError:
    from settings import SettingsError, handover_location

# Canonical section -> accepted heading prefixes (after removing a leading "N." number).
REQUIRED = {
    "State": ("state",),
    "Open issues": ("open issues", "known issues", "outstanding"),
    "Next actions": ("next actions", "next steps", "resuming work", "roadmap"),
}
RECOMMENDED = {
    "Tests and evidence": ("tests", "validation", "evidence"),
    "Risks": ("risks", "swot"),
}
AS_OF = re.compile(r"\bas of (\d{4}-\d{2}-\d{2})\b", re.IGNORECASE)
AS_OF_LINES = 10


def headings(text):
    found, fenced = [], False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
        elif not fenced and line.startswith("## "):
            found.append(re.sub(r"^\d+(\.\d+)*\.?\s+", "", line[3:].strip()).lower())
    return found


def validate(text):
    names = headings(text)

    def absent(sections):
        return [name for name, prefixes in sections.items() if not any(h.startswith(prefixes) for h in names)]

    match = next(filter(None, (AS_OF.search(line) for line in text.splitlines()[:AS_OF_LINES])), None)
    missing = absent(REQUIRED) + ([] if match else ["As of date"])
    return {
        "ok": not missing,
        "missing": missing,
        "warnings": absent(RECOMMENDED),
        "as_of": match.group(1) if match else None,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", help="Handover file; default: the configured handover.path")
    parser.add_argument("--repo", default=".", help="Repository used to resolve handover.path")
    parser.add_argument("--user-config")
    args = parser.parse_args(argv)
    try:
        path = Path(args.path) if args.path else Path(handover_location(args.repo, args.user_config)["path"])
    except (SettingsError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 2
    path = path.resolve()
    if path.is_file():
        result = validate(path.read_text(encoding="utf-8"))
    else:
        result = {"ok": False, "missing": ["file"], "warnings": [], "as_of": None}
    print(json.dumps({"path": str(path), **result}, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
