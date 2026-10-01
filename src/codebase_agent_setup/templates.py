"""Export editable agent templates and validate their target-relative payload."""

import argparse
import ast
import hashlib
import json
from pathlib import Path, PurePosixPath
import tempfile
from typing import NamedTuple

from .resources import RESOURCE_ROOT
from . import redact

MANIFEST = "template.json"
SCHEMA_VERSION = "1.0"


class TemplateError(ValueError):
    pass


class Snapshot(NamedTuple):
    root: Path
    files: dict
    fingerprint: str


def checked_root(path):
    path = Path(path).absolute()
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise TemplateError(f"Template paths must not contain symlinks: {path}")
    return path.resolve()


def payload():
    root = RESOURCE_ROOT / "project"
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and not p.name.startswith("test_")
    }


def fingerprint(files, manifest):
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}
    return hashlib.sha256(manifest + json.dumps(hashes, sort_keys=True).encode("utf-8")).hexdigest()


def snapshot(directory, *, target=None):
    root = checked_root(directory)
    if not root.is_dir():
        raise TemplateError(f"No template directory at {root}")
    if target is not None:
        destination = Path(target).resolve()
        if root.is_relative_to(destination) or destination.is_relative_to(root):
            raise TemplateError("Template and target directories must not overlap")
    manifest_path = root / MANIFEST
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise TemplateError(f"Template requires a regular {MANIFEST}")
    raw = manifest_path.read_bytes()
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeError) as error:
        raise TemplateError(f"Invalid {MANIFEST}: {error}") from error
    if (
        not isinstance(data, dict)
        or set(data) != {"schema_version", "files"}
        or data["schema_version"] != SCHEMA_VERSION
        or not isinstance(data["files"], list)
        or any(not isinstance(name, str) for name in data["files"])
    ):
        raise TemplateError("Unsupported template manifest; expected schema_version 1.0 and a files list")
    names = data["files"]
    allowed = set(payload())
    if len(set(name.casefold() for name in names)) != len(names):
        raise TemplateError("Duplicate or case-aliased template paths")
    for name in names:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or "\\" in name or path.as_posix() != name or name not in allowed:
            raise TemplateError(f"Unsupported template path: {name}")
    if set(names) != allowed:
        raise TemplateError("Template must list the complete supported payload; create a fresh template")
    found = set()
    directories = {parent.as_posix() for name in names for parent in PurePosixPath(name).parents if str(parent) != "."}
    for path in root.rglob("*"):
        if path.is_symlink():
            raise TemplateError(f"Template must not contain symlinks: {path.relative_to(root)}")
        if path.is_dir():
            if path.relative_to(root).as_posix() not in directories:
                raise TemplateError("Template contains an unsupported directory")
        else:
            if not path.is_file():
                raise TemplateError("Template contains a non-regular file")
            found.add(path.relative_to(root).as_posix())
    if found != set(names) | {MANIFEST}:
        raise TemplateError("Template contains missing or unlisted files; local state and credentials are not allowed")
    files = {}
    for name in names:
        content = (root / name).read_bytes()
        try:
            text = content.decode("utf-8")
            if "\0" in text:
                raise ValueError("NUL byte")
            if redact.scrub_value(text)[1] is not None:
                raise ValueError("credential-shaped content; keep credentials outside templates")
            if name.endswith(".json"):
                json.loads(text)
            if name.endswith(".py"):
                ast.parse(text, filename=name)
        except (ValueError, UnicodeError, SyntaxError) as error:
            raise TemplateError(f"Invalid template content in {name}: {error}") from error
        files[name] = content
    return Snapshot(root, files, fingerprint(files, raw))


def verify(source):
    if snapshot(source.root).fingerprint != source.fingerprint:
        raise TemplateError("Template changed after installation planning; preview again")


def create(directory, *, apply=True):
    target = checked_root(directory)
    source = (RESOURCE_ROOT / "project").resolve()
    if target.is_relative_to(source) or source.is_relative_to(target):
        raise TemplateError("Template output must not overlap the packaged payload")
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise TemplateError("Template output must be a new or empty directory; nothing overwritten")
    contents = payload()
    report = {"directory": str(target), "apply": apply, "files": sorted(contents), "manifest": MANIFEST}
    if not apply:
        return report
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cbsetup_template_", dir=target.parent) as temporary:
        staged = Path(temporary) / "template"
        staged.mkdir()
        for name, content in contents.items():
            path = staged / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        (staged / MANIFEST).write_text(
            json.dumps({"schema_version": SCHEMA_VERSION, "files": sorted(contents)}, indent=2) + "\n",
            encoding="utf-8",
        )
        snapshot(staged)
        # rmdir refuses if somebody filled the previously empty destination while staging.
        checked_root(target)
        if target.exists():
            target.rmdir()
        staged.rename(target)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(prog="cbsetup template", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    make = sub.add_parser("create", help="Export the built-in baseline for local editing")
    make.add_argument("directory", type=Path)
    from .install import add_write_arguments

    add_write_arguments(make)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(create(args.directory, apply=args.apply), indent=2))
        return 0
    except (TemplateError, OSError) as error:
        parser.exit(1, str(error) + "\n")
