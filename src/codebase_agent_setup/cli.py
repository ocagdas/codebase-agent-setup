"""Installed codebase-agent-setup command; static wheels and editable checkouts share this entry point."""

import importlib.metadata
import json
import importlib
import sys

from .resources import PACKAGE_ROOT as ROOT, RESOURCE_ROOT

COMMANDS = {
    "install": "install",
    "configure": "project.ai_workflow.tools.settings",
    "knowledge": "project.ai_workflow.tools.knowledge_backend",
    "bootstrap": "project.ai_workflow.tools.repo_bootstrap",
}


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
        print(
            "Usage: codebase-agent-setup {install,configure,knowledge,bootstrap} [arguments]\n"
            "       codebase-agent-setup --version\nUse codebase-agent-setup COMMAND --help for command options."
        )
        return 0
    if args[0] not in COMMANDS:
        print("Unknown command: " + args[0], file=sys.stderr)
        return 2
    name = COMMANDS[args[0]]
    module = importlib.import_module("." + name, __package__)
    return module.main(args[1:])
