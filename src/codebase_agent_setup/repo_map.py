"""Compatibility entry point; Codebase Index Kit owns repository-map generation and transfer."""

import argparse
import sys

from .project.ai_workflow.tools.knowledge import delegate


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args in (["--help"], ["-h"]):
        parser = argparse.ArgumentParser(
            prog="cbsetup repo-map",
            description="Optional Codebase Index Kit bridge: build, status, show, export, restore. "
            "Install Codebase Index Kit separately; run cbkit repo-map --help for engine options.",
        )
        parser.print_help()
        return 0
    return delegate("repo-map", args)
