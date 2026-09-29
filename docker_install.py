#!/usr/bin/env python3
"""Run installation using the CLI built into this image, independent of host setup preferences."""

import os
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from codebase_agent_setup import toolchains


def main():
    record = Path(__file__).resolve().parent / "toolchain.json"
    selection = toolchains.resolve_selection(record_file=record)
    if toolchains.is_override(selection):
        environment = toolchains.environment_path({"tooling": {"env_dir": None}}, selection)
        specify = str(toolchains.cli_in(environment))
    else:
        specify = shutil.which("specify")
    if not specify:
        raise SystemExit("The image does not contain its selected Specify CLI")
    os.execv(
        sys.executable,
        [
            sys.executable,
            str(toolchains.ROOT / "install.py"),
            "--toolchain-record",
            str(record),
            "--specify",
            specify,
            *sys.argv[1:],
        ],
    )


if __name__ == "__main__":
    main()
