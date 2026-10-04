"""Optional external Aider maps. No Aider imports in the CAS environment.

This is a scope snapshot adapter, not the knowledge layer/delta resolver.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from . import redact

CACHE = ".ai_cache/repo-map"
SCHEMA = "cas-aider-map-1"


def digest(value):
    return hashlib.sha256(value).hexdigest()


def git(repo, *args):
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True)
    return result.stdout


def safe_path(repo, relative):
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or "\\" in relative:
        raise ValueError("Paths must be repository-relative without traversal")
    target = repo / path
    if any(parent.is_symlink() for parent in (target, *target.parents)):
        raise ValueError(f"Symlink paths are not supported: {relative}")
    if not target.resolve().is_relative_to(repo):
        raise ValueError("Path escapes repository")
    return target


def inventory(repo, scopes):
    roots = [Path(scope) for scope in scopes]
    for scope in scopes:
        if not safe_path(repo, scope).exists():
            raise ValueError(f"Missing scope: {scope}")
    names = git(repo, "ls-files", "-z", "--cached", "--others", "--exclude-standard").split(b"\0")
    files = {}
    for raw in names:
        if not raw:
            continue
        name = raw.decode("utf-8")
        if name.startswith((".ai_cache/", ".cbsetup/", ".ai_migration_backup/")):
            continue
        path = Path(name)
        if not any(root == Path(".") or path == root or root in path.parents for root in roots):
            continue
        target = safe_path(repo, name)
        if not target.is_file():
            continue  # Deleted tracked files are absent from this complete snapshot.
        data = target.read_bytes()
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if b"\0" not in data:
            files[name] = digest(data)
    return dict(sorted(files.items()))


def write(path, data, *, replace=True):
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        raise ValueError("Refusing symlink destination")
    path.parent.mkdir(parents=True, exist_ok=True)
    if not replace:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        return
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def private_cache(repo):
    target = safe_path(repo, CACHE)
    if git(repo, "ls-files", "--", CACHE).strip():
        raise ValueError("Map cache is already tracked; untrack it manually before proceeding")
    # Local Git exclusion (shared by linked worktrees): no tracked .gitignore edits or index mutation.
    exclude = Path(git(repo, "rev-parse", "--git-path", "info/exclude").decode().strip())
    if not exclude.is_absolute():
        exclude = repo / exclude
    if exclude.is_symlink() or any(parent.is_symlink() for parent in exclude.parents):
        raise ValueError("Refusing symlink Git exclude file")
    rule = f"/{CACHE}/"
    old = exclude.read_bytes() if exclude.exists() else b""
    if rule not in old.decode("utf-8").splitlines():
        exclude.parent.mkdir(parents=True, exist_ok=True)
        with exclude.open("ab") as handle:
            handle.write(("\n" + rule + "\n").encode())
    checked = subprocess.run(["git", "-C", str(repo), "check-ignore", "-q", "--", f"{CACHE}/current.json"])
    if checked.returncode:
        raise ValueError("Git rules override the cache exclusion; fix them before proceeding")
    return target


def validate(data):
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise ValueError("Unsupported map schema")
    if not isinstance(data.get("map"), str) or data.get("map_sha256") != digest(data["map"].encode()):
        raise ValueError("Map integrity mismatch")
    if not isinstance(data.get("files"), dict) or not isinstance(data.get("scopes"), list):
        raise ValueError("Invalid map scope/inventory")
    if not data["scopes"] or not all(isinstance(scope, str) for scope in data["scopes"]):
        raise ValueError("Invalid map scopes")
    if not all(isinstance(name, str) and isinstance(value, str) for name, value in data["files"].items()):
        raise ValueError("Invalid file inventory")
    allowed = {
        "schema",
        "producer",
        "producer_version",
        "budget_estimated_tokens",
        "scopes",
        "files",
        "commit",
        "map",
        "map_sha256",
        "redactions",
    }
    if set(data) != allowed or data.get("producer") != "aider":
        raise ValueError("Invalid map metadata")
    if not isinstance(data.get("producer_version"), str) or not data["producer_version"]:
        raise ValueError("Invalid producer version")
    if type(data.get("budget_estimated_tokens")) is not int or data["budget_estimated_tokens"] <= 0:
        raise ValueError("Invalid map budget")
    if not isinstance(data.get("redactions"), list) or not all(
        isinstance(item, dict)
        and set(item) == {"location", "reason"}
        and all(isinstance(value, str) for value in item.values())
        for item in data["redactions"]
    ):
        raise ValueError("Invalid redaction records")
    return data


def read(repo):
    return validate(json.loads(safe_path(repo, f"{CACHE}/current.json").read_text(encoding="utf-8")))


def current(repo, data):
    return inventory(repo, data["scopes"]) == data["files"]


def build(repo, python, scopes, budget, dry_run=False):
    files = inventory(repo, scopes)
    if not files:
        raise ValueError("No UTF-8 source files in the selected scope")
    if dry_run:
        return {"dry_run": True, "files": len(files), "scopes": scopes, "python": python}
    python = shutil.which(python) or str(Path(python).resolve())
    version_result = subprocess.run(
        [python, str(Path(__file__).with_name("aider_worker.py")), "--version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    if version_result.returncode:
        raise ValueError("Install aider-chat in the selected --python environment: " + version_result.stderr[-1000:])
    version = version_result.stdout.strip()
    cache = private_cache(repo)
    if (cache / "current.json").is_file():
        previous = read(repo)
        if (
            previous["files"] == files
            and previous["scopes"] == scopes
            and previous.get("producer_version") == version
            and previous.get("budget_estimated_tokens") == budget
        ):
            return {"path": str(cache / "current.json"), "files": len(files), "reused": True}
    with tempfile.TemporaryDirectory(prefix="cas-aider-") as temporary:
        scratch = Path(temporary)
        source = scratch / "source"
        source.mkdir()
        for name, expected in files.items():
            data = safe_path(repo, name).read_bytes()
            if digest(data) != expected:
                raise ValueError("Source changed during capture; retry")
            destination = source / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        request = scratch / "request.json"
        request.write_text(json.dumps({"root": str(source), "files": list(files), "budget": budget}), encoding="utf-8")
        # Only basic process/runtime environment: no API credentials or Aider settings.
        env = {
            key: value
            for key, value in os.environ.items()
            if key.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "LANG", "LC_ALL", "LD_LIBRARY_PATH"}
        }
        env.update(HOME=str(scratch), USERPROFILE=str(scratch), PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
        worker = Path(__file__).with_name("aider_worker.py")
        result = subprocess.run(
            [python, str(worker), str(request)],
            cwd=scratch,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=600,
        )
        if result.returncode:
            raise ValueError(
                "External Aider failed; install aider-chat in the selected Python environment. " + result.stderr[-2000:]
            )
        output = json.loads(result.stdout)
        if output["version"] != version:
            raise ValueError("Aider version changed during generation")
        cleaned, removals = redact.text(output["map"], "map.txt")
        if inventory(repo, scopes) != files:
            raise ValueError("Source changed during generation; map not saved")
        data = {
            "schema": SCHEMA,
            "producer": "aider",
            "producer_version": output["version"],
            "budget_estimated_tokens": budget,
            "scopes": scopes,
            "files": files,
            "commit": git(repo, "rev-parse", "HEAD").decode().strip(),
            "map": cleaned,
            "map_sha256": digest(cleaned.encode()),
            "redactions": [item._asdict() for item in removals],
        }
        key = digest(json.dumps(data, sort_keys=True).encode())
        write(cache / f"{key}.json", data)
        write(cache / "current.json", data)
    return {"path": str(cache / "current.json"), "files": len(files), "producer_version": data["producer_version"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "show", "status", "export", "restore"))
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--python", default=sys.executable, help="Python in the isolated Aider environment")
    parser.add_argument("--path", action="append", help="Repository-relative scope; repeatable; default .")
    parser.add_argument("--budget", type=int, default=4096, help="Approximate token budget (UTF-8 bytes/4)")
    parser.add_argument("--out", type=Path, help="Export destination; must not already exist")
    parser.add_argument("--from", dest="source", type=Path, help="Snapshot to restore")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        repo = args.repo.resolve()
        root = Path(git(repo, "rev-parse", "--show-toplevel").decode().strip()).resolve()
        if root != repo:
            raise ValueError("--repo must name the Git repository root")
        if args.budget <= 0:
            raise ValueError("--budget must be positive")
        if args.action == "build":
            result = build(repo, args.python, args.path or ["."], args.budget, args.dry_run)
        elif args.action == "restore":
            if not args.source:
                raise ValueError("restore requires --from")
            data = validate(json.loads(args.source.read_text(encoding="utf-8")))
            if not current(repo, data):
                raise ValueError("Snapshot does not match this checkout's scoped source; rebuild instead")
            cleaned, removals = redact.text(data["map"], "map.txt")
            data["map"] = cleaned
            data["map_sha256"] = digest(cleaned.encode())
            data["redactions"] = data.get("redactions", []) + [item._asdict() for item in removals]
            if not args.dry_run:
                write(private_cache(repo) / "current.json", data)
            result = {"restored": not args.dry_run, "current": True}
        else:
            data = read(repo)
            fresh = current(repo, data)
            if args.action == "status":
                result = {
                    "current": fresh,
                    "producer_version": data.get("producer_version"),
                    "files": len(data["files"]),
                }
            elif args.action == "show":
                if not fresh:
                    raise ValueError("Map is stale; rebuild before showing it to an agent")
                print(data["map"])
                return 0
            else:
                if not args.out:
                    raise ValueError("export requires --out")
                if args.out.resolve().is_relative_to(repo):
                    raise ValueError("Export outside the repository; review before sharing")
                if not fresh:
                    raise ValueError("Map is stale; rebuild before exporting")
                cleaned, removals = redact.text(data["map"], "map.txt")
                data["map"] = cleaned
                data["map_sha256"] = digest(cleaned.encode())
                data["redactions"] = data.get("redactions", []) + [item._asdict() for item in removals]
                if not args.dry_run:
                    write(args.out, data, replace=False)
                result = {"exported": not args.dry_run, "redactions": data["redactions"], "review_required": True}
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
