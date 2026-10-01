"""The single cbsetup command surface; static wheels and editable checkouts share this entry point."""

import importlib.metadata
import json
import importlib
import sys

from .resources import PACKAGE_ROOT as ROOT, RESOURCE_ROOT

COMMANDS = {
    "template": ("templates", "Create an editable baseline for single or fleet installation"),
    "install": ("install", "Seed or upgrade a repository's tool-neutral agent guide"),
    "capsule": ("capsule", "Capture, inspect and replay a setup; always redacted"),
    "fleet": ("fleet", "Status and mass apply across many repositories"),
    "handover": ("project.ai_workflow.tools.validate_handover", "Locate and validate a repository's handover document"),
    "configure": ("project.ai_workflow.tools.settings", "Inspect and change settings"),
    "knowledge": ("project.ai_workflow.tools.knowledge", "Build, share and query a repository index"),
    "bootstrap": ("project.ai_workflow.tools.repo_bootstrap", "Optional local inventories"),
}
USAGE = "\n".join(
    ["Usage: codebase-agent-setup <command> [arguments]", "       codebase-agent-setup --version", "", "Commands:"]
    + [f"  {name:<10} {help}" for name, (_, help) in COMMANDS.items()]
    + ["", "Run codebase-agent-setup <command> --help for a command's options."]
)


def main(argv=None):
    args = sys.argv[1:] if argv is None else list(argv)
    if args == ["--version"]:
        distribution = importlib.metadata.distribution("codebase-agent-setup")
        origin = json.loads(distribution.read_text("direct_url.json") or "{}")
        print(
            json.dumps(
                {
                    "version": distribution.version,
                    "install_mode": "editable" if origin.get("dir_info", {}).get("editable") else "static",
                    "code_path": str(ROOT),
                    "resource_path": str(RESOURCE_ROOT),
                },
                indent=2,
            )
        )
        return 0
    if not args or args[0] in ("-h", "--help"):
        print(USAGE)
        return 0
    if args[0] not in COMMANDS:
        print("Unknown command: " + args[0], file=sys.stderr)
        print(USAGE, file=sys.stderr)
        return 2
    module = importlib.import_module("." + COMMANDS[args[0]][0], __package__)
    return module.main(args[1:])
