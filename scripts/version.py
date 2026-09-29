"""Manage synchronized versions and immutable tags; remote pushes belong to CI."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tomllib

if __package__:
    from . import repository_release as shared
else:
    import repository_release as shared

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILES = ("pyproject.toml", "upstream.lock.json")
PATTERN = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")


parse = shared.parse


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, encoding="utf-8", timeout=120).strip()


def project_version(text: str) -> str:
    value = tomllib.loads(text)["project"]["version"]
    parse(value)
    return value


def current() -> str:
    version = project_version((ROOT / VERSION_FILES[0]).read_text(encoding="utf-8"))
    mirror = json.loads((ROOT / VERSION_FILES[1]).read_text(encoding="utf-8"))["package_version"]
    if mirror != version:
        raise ValueError("pyproject.toml and upstream.lock.json package_version must agree")
    return version


change_kind = shared.change_kind
bump = shared.bump


def write_version(version: str, *, dry_run: bool = False) -> dict:
    old = current()
    change_kind(old, version)
    paths = [ROOT / name for name in VERSION_FILES]
    originals = [p.read_text(encoding="utf-8") for p in paths]
    # Limit replacement to the project table, not unrelated tool versions.
    project = re.sub(
        r'(\[project\]\n[\s\S]*?^version = )"[^"]+"',
        rf'\g<1>"{version}"',
        originals[0],
        count=1,
        flags=re.M,
    )
    package, count = re.subn(r'"package_version": "[^"\n]+"', f'"package_version": "{version}"', originals[1])
    if project_version(project) != version or count != 1:
        raise ValueError("Version files do not have the supported assignment format")
    if not dry_run:
        try:
            for path, content in zip(paths, (project, package)):
                path.write_text(content, encoding="utf-8")
        except OSError:
            for path, content in zip(paths, originals):
                path.write_text(content, encoding="utf-8")
            raise
    return {"previous": old, "version": version, "tag": f"v{version}", "dry_run": dry_run}


def check_pr(base_ref: str) -> str:
    version = current()
    base = project_version(git("show", f"{git('merge-base', base_ref, 'HEAD')}:pyproject.toml"))
    if version != base:
        raise ValueError(
            "PRs must not change versions; CI bumps patches after merge. Select minor/major directly on trunk."
        )
    return version


def tag_commit(tag: str) -> str | None:
    # Enumerate exact refs to distinguish absence from an invalid/corrupt existing tag.
    if f"refs/tags/{tag}" not in git("for-each-ref", "--format=%(refname)", "refs/tags").splitlines():
        return None
    return git("rev-parse", f"refs/tags/{tag}^{{commit}}")


def create_tag(*, dry_run: bool = False) -> str:
    version = current()
    tag = f"v{version}"
    commit = tag_commit(tag)
    if commit and commit != git("rev-parse", "HEAD"):
        raise ValueError(f"Immutable tag {tag} already belongs to another commit")
    if git("status", "--porcelain"):
        raise ValueError("Working tree must be clean before tagging")
    if not commit and not dry_run:
        git("tag", "-a", tag, "-m", f"codebase-agent-setup {tag}")
    return tag


plan = shared.plan


def ci_plan(merged: bool) -> dict:
    version = current()
    parents = git("rev-list", "--parents", "-n", "1", "HEAD").split()[1:]
    previous = project_version(git("show", "HEAD^1:pyproject.toml")) if parents else None
    result = plan(
        previous,
        version,
        merged=merged or len(parents) > 1,
        tagged=tag_commit(f"v{version}") == git("rev-parse", "HEAD"),
    )
    result["schema_version"] = 1
    result["source_commit"] = git("rev-parse", "HEAD")
    result["tag"] = f"v{result['version']}"
    return result


def emit(result: dict, *, github_output: bool = False) -> None:
    print(json.dumps(result, sort_keys=True))
    if github_output and (output := os.getenv("GITHUB_OUTPUT")):
        with Path(output).open("a", encoding="utf-8") as stream:
            for key, value in result.items():
                if isinstance(value, bool):
                    value = str(value).lower()
                if "\n" in str(value) or "\r" in str(value):
                    raise ValueError("Multiline CI output is not supported")
                stream.write(f"{key}={value}\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check")
    item = sub.add_parser("current")
    group = item.add_mutually_exclusive_group()
    group.add_argument("--plain", action="store_true")
    group.add_argument("--json", action="store_true")
    for command in ("patch", "minor", "major", "set", "tag"):
        item = sub.add_parser(command)
        item.add_argument("--dry-run", action="store_true")
        if command == "set":
            item.add_argument("version")
    item = sub.add_parser("check-pr")
    item.add_argument("--base-ref", required=True)
    item = sub.add_parser("classify-ci")
    item.add_argument("--merged", action="store_true")
    item.add_argument("--github-output", action="store_true")
    item = sub.add_parser("classify-release")
    item.add_argument("--tag", required=True)
    item.add_argument("--github-output", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            print(current())
        elif args.command == "current":
            print(current() if args.plain else json.dumps({"version": current()}))
        elif args.command == "check-pr":
            print(check_pr(args.base_ref))
        elif args.command == "tag":
            print(create_tag(dry_run=args.dry_run))
        elif args.command == "classify-ci":
            emit(ci_plan(args.merged), github_output=args.github_output)
        elif args.command == "classify-release":
            version = current()
            if args.tag != f"v{version}" or tag_commit(args.tag) != git("rev-parse", "HEAD"):
                raise ValueError("Release tag, commit and version must agree")
            emit(
                {
                    "schema_version": 1,
                    "version": version,
                    "tag": args.tag,
                    "source_commit": git("rev-parse", "HEAD"),
                    "publish": False,
                },
                github_output=args.github_output,
            )
        else:
            target = args.version if args.command == "set" else bump(current(), args.command)
            emit(write_version(target, dry_run=args.dry_run))
        return 0
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as exc:
        print(f"Version error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
