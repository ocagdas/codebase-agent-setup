"""List CAS integration paths, distinguishing official discovery from CAS manuals."""

import argparse
import json

from .resources import RESOURCE_ROOT


def catalog():
    return json.loads((RESOURCE_ROOT / "project/ai_workflow/tool_registry.json").read_text(encoding="utf-8"))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="cbsetup tools", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    listing = sub.add_parser("list", help="Supported integration files, not installed-tool detection")
    listing.add_argument("--json", action="store_true")
    show = sub.add_parser("show", help="Exact paths and official documentation for one tool")
    show.add_argument("tool", choices=sorted(catalog()["tools"]))
    show.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    data = catalog()
    result = {
        "schema_version": data["schema_version"],
        "qualification": "Instruction-file integration; live client compliance not established",
        "manual_ownership": "User maintained; preserved even during override; ignored by default",
        "tools": data["tools"] if args.command == "list" else {args.tool: data["tools"][args.tool]},
    }
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        for tool, entry in result["tools"].items():
            print(f"{tool}: {entry['entry_file']} -> {entry['manual_file']}")
            if args.command == "show":
                print("Official patterns: " + ", ".join(entry["official_patterns"]))
                print("Documentation: " + entry["source"])
        print(result["qualification"])
        print(result["manual_ownership"])
    return 0
