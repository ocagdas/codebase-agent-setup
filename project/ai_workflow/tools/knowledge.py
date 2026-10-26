#!/usr/bin/env python3
"""Optional Codebase Index Kit bridge; indexing and caches belong to the external tool."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys


def delegate(command, arguments, settings=None):
    executable = shutil.which("cbkit")
    if not executable:
        print(
            "Codebase Index Kit is not installed/on PATH. Install the reviewed companion project into a tool "
            "environment and expose its cbkit executable. CAS never downloads it automatically.",
            file=sys.stderr,
        )
        return 2
    try:
        probe = subprocess.run(
            [executable, "--capabilities"], capture_output=True, text=True, encoding="utf-8", timeout=10
        )
        capabilities = json.loads(probe.stdout)
        if (
            probe.returncode != 0
            or not isinstance(capabilities, dict)
            or type(capabilities.get("contract_version")) is not int
            or capabilities["contract_version"] != 1
            or command not in capabilities.get("commands", [])
            or (settings is not None and capabilities.get("settings_stdin") is not True)
        ):
            raise ValueError("incompatible CLI contract")
        options = {}
        if settings is not None:
            arguments = ["--settings-stdin", *arguments]
            options = {
                "input": json.dumps({"schema_version": 1, "knowledge": settings}),
                "text": True,
                "encoding": "utf-8",
            }
        # Argument vector, never a shell string; output and exit status belong to the tool.
        return subprocess.run([executable, command, *arguments], **options).returncode
    except (OSError, ValueError, TypeError, subprocess.TimeoutExpired) as error:
        print(f"Cannot use Codebase Index Kit: {error}", file=sys.stderr)
        return 2


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        prog="cbsetup knowledge",
        description="Optional Codebase Index Kit: status, build, query, push, pull. Legacy CAS settings are resolved here.",
    )
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--user-config", type=Path)
    parser.add_argument(
        "--config", type=Path, help="Use native Codebase Index Kit configuration instead of CAS settings"
    )
    if args in (["--help"], ["-h"]):
        parser.print_help()
        parser.exit()
    # Bridge flags may occur before/after the verb; query arguments after -- stay literal.
    separator = args.index("--") if "--" in args else len(args)
    bridge, unknown = parser.parse_known_args(args[:separator])
    forwarded = [*unknown, *args[separator:]]
    if bridge.config is not None:
        return delegate("knowledge", ["--repo", str(bridge.repo), "--config", str(bridge.config), *forwarded])
    try:
        if __package__:
            from .settings import resolve, SettingsError
        else:
            from settings import resolve, SettingsError
        effective = resolve(bridge.repo, bridge.user_config)["settings"]["knowledge"]
    except (SettingsError, OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    return delegate("knowledge", ["--repo", str(bridge.repo), *forwarded], effective)


if __name__ == "__main__":
    raise SystemExit(main())
