#!/usr/bin/env python3
"""Prepare machine tooling separately from project installation."""

import argparse
import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import sys
import sysconfig
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from codebase_agent_setup import toolchains
from codebase_agent_setup.project.ai_workflow.tools.settings import resolve

ROOT = Path(__file__).resolve().parent


def native_user_install():
    return sys.prefix == sys.base_prefix and not os.environ.get("CONDA_PREFIX")


def native_scripts_directory():
    if native_user_install():
        return Path(sysconfig.get_path("scripts", scheme=sysconfig.get_preferred_scheme("user")))
    return Path(sysconfig.get_path("scripts"))


def commands(mode, env_dir, conda_name):
    requirements = str(ROOT / "requirements.txt")
    if mode == "native":
        pip = [sys.executable, "-m", "pip", "install"]
        if native_user_install():
            pip.append("--user")
        return [pip + ["-r", requirements]]
    if mode == "venv":
        python = env_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if env_dir.exists() and not (env_dir / "pyvenv.cfg").is_file():
            raise ValueError("Existing environment path is not a venv: " + str(env_dir))
        return [[sys.executable, "-m", "venv", str(env_dir)], [str(python), "-m", "pip", "install", "-r", requirements]]
    if not conda_name or conda_name.startswith("-") or any(c in conda_name for c in "/\\ "):
        raise ValueError("Use a simple Conda environment name")
    conda = os.environ.get("CONDA_EXE") or shutil.which("conda") or "conda"
    return [[conda, "env", "create", "--name", conda_name, "--file", str(ROOT / "environment.yml")]]


def package_command(mode, env_dir, conda_name, install_mode="static", extras="minimal"):
    """Install this distribution into the same interpreter as its companion tools."""
    if mode == "conda":
        conda = os.environ.get("CONDA_EXE") or shutil.which("conda") or "conda"
        command = [conda, "run", "-n", conda_name, "python", "-m", "pip", "install"]
    elif mode == "venv":
        command = [str(toolchains.python_in(env_dir)), "-m", "pip", "install"]
    else:
        command = [sys.executable, "-m", "pip", "install"]
        if native_user_install():
            command.append("--user")
    if install_mode == "editable":
        command.append("--editable")
    target = str(ROOT) + (f"[{extras}]" if extras != "minimal" else "")
    return command + [target]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["native", "venv", "conda"], default=None)
    parser.add_argument("--env-dir", type=Path, default=None)
    parser.add_argument(
        "--conda-name", default=None, help="Conda environment name (resolved default: codebase-agent-setup)"
    )
    parser.add_argument("--repo", type=Path, help="Optional project scope for settings")
    parser.add_argument("--user-config", type=Path)
    parser.add_argument("--speckit-ref", help="Official release tag or full commit; overrides settings")
    parser.add_argument("--toolchain-record", type=Path, help="Import an exact source record")
    parser.add_argument("--export-record", type=Path, help="Export source and compatibility evidence after apply")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--install-mode",
        choices=["static", "editable"],
        default="static",
        help="Static snapshot (default) or source-linked editable installation",
    )
    modes.add_argument("--editable", dest="install_mode", action="store_const", const="editable")
    modes.add_argument("--static", dest="install_mode", action="store_const", const="static")
    parser.add_argument(
        "--extras",
        choices=["minimal", "cgc", "sourcegraph", "all"],
        default="minimal",
        help="Optional local dependencies; installing does not enable a backend",
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if sys.version_info < (3, 11):
        parser.error("Python 3.11 or newer is required")
    try:
        toolchains.check_export_path(args.export_record)
        explicit = {
            key: str(value) if isinstance(value, Path) else value
            for key, value in {"mode": args.mode, "env_dir": args.env_dir, "conda_name": args.conda_name}.items()
            if value is not None
        }
        overrides = {"tooling": explicit}
        if args.speckit_ref:
            overrides["speckit"] = {"ref": args.speckit_ref}
        settings = resolve(args.repo, args.user_config, overrides)["settings"]
        effective = settings["tooling"]
        selection = toolchains.resolve_selection(settings["speckit"]["ref"], args.toolchain_record)
        args.mode = effective["mode"]
        # Native overrides get their own companion environment, never replace
        # the active interpreter's installed Spec Kit.
        install_mode = "venv" if toolchains.is_override(selection) and args.mode == "native" else args.mode
        args.conda_name = toolchains.conda_environment(settings, selection)
        args.env_dir = toolchains.environment_path(settings, selection)
        if install_mode == "conda" and toolchains.is_override(selection):
            conda = os.environ.get("CONDA_EXE") or shutil.which("conda") or "conda"
            plan = [
                [
                    conda,
                    "create",
                    "--name",
                    args.conda_name,
                    "--yes",
                    "--override-channels",
                    "-c",
                    "conda-forge",
                    "python=3.12",
                    "pip",
                    "git",
                ],
                [
                    conda,
                    "run",
                    "-n",
                    args.conda_name,
                    "python",
                    "-m",
                    "pip",
                    "install",
                    toolchains.requirement(selection),
                ],
            ]
        else:
            plan = commands(install_mode, args.env_dir, args.conda_name)
            if toolchains.is_override(selection):
                plan[-1] = [
                    str(toolchains.python_in(args.env_dir)),
                    "-m",
                    "pip",
                    "install",
                    toolchains.requirement(selection),
                ]
        plan.append(package_command(install_mode, args.env_dir, args.conda_name, args.install_mode, args.extras))
        record_path = args.env_dir / ".codebase-agent-setup-toolchain.json"
        if install_mode == "venv" and args.env_dir.exists():
            if record_path.is_file():
                existing = toolchains.validate_record(json.loads(record_path.read_text(encoding="utf-8")))
                if existing["upstream_commit"] != selection["upstream_commit"]:
                    raise ValueError("Environment is owned by another toolchain; choose a different --env-dir")
            elif toolchains.is_override(selection):
                raise ValueError(
                    "Override environment already exists without an ownership record; choose a different --env-dir"
                )
        print(
            json.dumps(
                {
                    "mode": args.mode,
                    "effective_install_mode": install_mode,
                    "commands": plan,
                    "toolchain": selection,
                    "environment": str(args.env_dir) if install_mode == "venv" else args.conda_name,
                    "install_mode": args.install_mode,
                    "extras": args.extras,
                    "apply": args.apply,
                },
                indent=2,
            ),
            flush=True,
        )
        if not args.apply:
            if args.export_record:
                raise ValueError(
                    "--export-record requires --apply; preview output already includes the resolved source"
                )
            return
        if args.mode != "conda" and not shutil.which("git"):
            raise ValueError("Install Git and put it on PATH before installing the official source requirement")
        setup_lock = None
        if install_mode == "venv":
            args.env_dir.parent.mkdir(parents=True, exist_ok=True)
            setup_lock = args.env_dir.parent / (args.env_dir.name + ".setup.lock")
            try:
                with setup_lock.open("x", encoding="utf-8") as handle:
                    handle.write(str(os.getpid()))
            except FileExistsError:
                raise ValueError("Another setup owns this environment; check " + str(setup_lock))
        try:
            for index, command in enumerate(plan):
                toolchains.run(command, cwd=ROOT, capture=False)
                if install_mode == "venv" and index == 0:
                    toolchains.write_record(record_path, {**selection, "compatibility": {"status": "pending"}})
            if install_mode == "venv":
                specify = str(toolchains.cli_in(args.env_dir))
            elif install_mode == "conda":
                conda = os.environ.get("CONDA_EXE") or shutil.which("conda") or "conda"
                prefix = Path(
                    toolchains.run(
                        [conda, "run", "-n", args.conda_name, "python", "-c", "import sys; print(sys.prefix)"]
                    )
                )
                specify = str(toolchains.cli_in(prefix))
                record_path = prefix / ".codebase-agent-setup-toolchain.json"
            else:
                scripts = native_scripts_directory()
                specify = str(scripts / ("specify.exe" if os.name == "nt" else "specify"))
                record_path = ROOT / ".toolchains/records" / (selection["upstream_commit"] + ".json")
            with tempfile.TemporaryDirectory(prefix="toolchain-check-") as temp:
                _, compatibility = toolchains.stage_package(specify, settings["agent"]["integrations"], selection, temp)
            record = {**selection, "compatibility": compatibility}
            toolchains.write_record(record_path, record)
            if args.export_record:
                toolchains.write_record(args.export_record, record)
            print("Resolved toolchain record: " + str(record_path))
            print("Compatibility: " + compatibility["classification"])
        finally:
            if setup_lock:
                setup_lock.unlink(missing_ok=True)
        print("codebase-agent-setup installed (" + args.install_mode + ", " + args.extras + ").")
        print(
            "Use codebase-agent-setup --version and codebase-agent-setup install /path/to/project --apply in the selected environment."
        )
        if install_mode == "venv":
            print(
                "Launcher: "
                + str(
                    args.env_dir
                    / ("Scripts/codebase-agent-setup.exe" if os.name == "nt" else "bin/codebase-agent-setup")
                )
            )
        if args.install_mode == "editable":
            print(
                "Keep this source checkout in place. Source/payload changes apply on the next launcher run; dependency changes need setup again."
            )
        if args.mode == "conda":
            print("Activate the environment in your current shell:")
            print("  conda activate " + shlex.quote(args.conda_name))
            print("Then use python and specify normally; pass --specify specify to install.py.")
            print(
                "Setup cannot activate its parent shell. If activation fails, see the Conda shell setup in INSTALLATION.md."
            )
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
