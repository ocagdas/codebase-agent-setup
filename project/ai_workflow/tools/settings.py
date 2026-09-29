#!/usr/bin/env python3
"""Versioned personal/project settings; no third-party runtime dependencies."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid
from urllib.parse import urlsplit

DEFAULTS = {
    "tooling": {"mode": "venv", "env_dir": None, "conda_name": "codebase-agent-setup"},
    "speckit": {"ref": None},
    "agent": {"integrations": ["codex"]},
    "knowledge": {"mode": "auto", "base_refs": None, "backend": "off"},
    "cgc": {"executable": "cgc", "data_dir": None},
    "sourcegraph": {"url": None, "repository": None, "token_env": "SOURCEGRAPH_TOKEN"},
}
MODES = {"source": "disabled", "index": "required", "auto": "auto"}


class SettingsError(ValueError):
    pass


def read(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise SettingsError(f"Cannot read settings {path}: {error}") from error
    if not isinstance(data, dict):
        raise SettingsError(f"{path}: expected an object")
    return data


def user_file():
    if os.name == "nt":
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming"))
    elif sys.platform == "darwin":
        root = Path.home() / "Library/Application Support"
    else:
        root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    path = root / "codebase-agent-setup/config.json"
    legacy = root / "repo-pilot/config.json"  # name before the codebase-agent-setup rename
    return legacy if not path.exists() and legacy.exists() else path


def canonical_remote(remote):
    if "://" in remote:
        parsed = urlsplit(remote)
        host, path = parsed.hostname, parsed.path
        if not host:
            return None
        try:
            port = parsed.port
        except ValueError:
            return None
        defaults = {"ssh": 22, "https": 443, "http": 80, "git": 9418}
        if port is not None and port != defaults.get(parsed.scheme):
            host += ":" + str(port)
    else:
        match = re.fullmatch(r"(?:[^@/:]+@)?([^/:]+):(.+)", remote)
        if not match:
            return None
        host, path = match.groups()
    return host.lower() + "/" + path.strip("/").removesuffix(".git")


def identity(repo, shared):
    explicit = shared.get("repository_id")
    if explicit:
        return explicit
    if repo:
        try:
            proc = subprocess.run(
                ["git", "-C", str(repo), "remote", "get-url", "origin"],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
        except FileNotFoundError:
            return None
        remote = canonical_remote(proc.stdout.strip()) if proc.returncode == 0 else None
        if remote:
            return "remote:" + hashlib.sha256(remote.encode("utf-8")).hexdigest()
    return None


def validate_document(data, scope):
    allowed = {"schema_version", "settings"}
    if scope == "user":
        allowed.add("projects")
    if scope == "project":
        allowed.add("repository_id")
    extra = set(data) - allowed
    if extra:
        raise SettingsError(f"{scope}: unsupported keys {sorted(extra)}")
    if data.get("schema_version") != "1.0":
        raise SettingsError(f'{scope}: schema_version must be "1.0"')
    if "repository_id" in data and (not isinstance(data["repository_id"], str) or not data["repository_id"].strip()):
        raise SettingsError("repository_id must be a nonempty string")
    validate_settings(data.get("settings", {}))
    projects = data.get("projects", {})
    if not isinstance(projects, dict):
        raise SettingsError("projects must be an object keyed by repository identity")
    for key, settings in projects.items():
        if not key.strip():
            raise SettingsError("Empty project identity")
        validate_settings(settings)


def validate_settings(settings):
    if not isinstance(settings, dict):
        raise SettingsError("settings must be an object")
    for section, values in settings.items():
        if section not in DEFAULTS or not isinstance(values, dict):
            raise SettingsError(f"Unsupported settings section: {section}")
        for key, value in values.items():
            if key not in DEFAULTS[section]:
                raise SettingsError(f"Unsupported setting: {section}.{key}")
            # Null is an explicit reset to the distribution default.
            if value is None:
                continue
            valid = True
            if key == "backend":
                valid = value in ("off", "cgc", "sourcegraph")
            elif section in ("cgc", "sourcegraph"):
                valid = isinstance(value, str) and bool(value.strip())
                if valid and key == "url":
                    parsed = urlsplit(value)
                    valid = (
                        parsed.scheme == "https"
                        and bool(parsed.hostname)
                        and not parsed.username
                        and not parsed.password
                        and not parsed.query
                        and not parsed.fragment
                    )
                if valid and key == "token_env":
                    valid = bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value))
            elif key == "mode":
                valid = isinstance(value, str) and value in (
                    MODES if section == "knowledge" else ("venv", "native", "conda")
                )
            elif key == "ref":
                valid = isinstance(value, str) and bool(
                    re.fullmatch(r"(?:[0-9a-f]{40}|v?[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?)", value)
                )
            elif key == "env_dir":
                valid = isinstance(value, str) and bool(value.strip())
            elif key == "conda_name":
                valid = isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", value)
            elif key in ("integrations", "base_refs"):
                valid = isinstance(value, list) and all(isinstance(x, str) and x.strip() for x in value)
                if valid and key == "integrations":
                    valid = bool(value) and all(x in ("codex", "cursor-agent", "copilot") for x in value)
            if not valid:
                raise SettingsError(f"Invalid value for {section}.{key}")


def resolve(repo=None, user_config=None, overrides=None, legacy=None):
    repo = Path(repo).resolve() if repo else None
    project_path = repo / "ai_workflow/settings.json" if repo else None
    local_path = repo / "ai_workflow/settings.local.json" if repo else None
    user_path = Path(user_config).resolve() if user_config else user_file()
    documents = {}
    for scope, path in [("user", user_path), ("project", project_path), ("local", local_path)]:
        data = read(path) if path and path.exists() else {"schema_version": "1.0"}
        validate_document(data, scope)
        documents[scope] = data
    repository_id = identity(repo, documents["project"])
    effective = copy.deepcopy(DEFAULTS)
    origins = {f"{section}.{key}": "distribution" for section, values in DEFAULTS.items() for key in values}

    def overlay(values, origin, directory):
        validate_settings(values)
        for section, entries in values.items():
            for key, value in entries.items():
                value = copy.deepcopy(DEFAULTS[section][key] if value is None else value)
                if key in ("env_dir", "data_dir") and value is not None:
                    path = Path(value).expanduser()
                    value = str((directory / path).resolve())
                effective[section][key] = value
                origins[f"{section}.{key}"] = origin

    overlay(documents["user"].get("settings", {}), str(user_path), user_path.parent)
    # Existing bootstrap preferences enter at shared-project precedence.
    legacy_path = repo / "ai_workflow/bootstrap.json" if repo else None
    if legacy is None and legacy_path and legacy_path.is_file():
        legacy = read(legacy_path)
    if legacy:
        preferences = {}
        mode = legacy.get("semantic_index", {}).get("mode")
        if mode is not None:
            inverse = {v: k for k, v in MODES.items()}
            if mode not in inverse:
                raise SettingsError("Invalid legacy semantic mode")
            preferences["mode"] = inverse[mode]
        refs = legacy.get("branch_selection", {}).get("base_ref_candidates")
        if refs is not None:
            preferences["base_refs"] = refs
        overlay({"knowledge": preferences}, str(legacy_path or "legacy bootstrap"), repo or Path.cwd())
    overlay(
        documents["project"].get("settings", {}), str(project_path), project_path.parent if project_path else Path.cwd()
    )
    overlay(
        documents["user"].get("projects", {}).get(repository_id, {}),
        f"{user_path}#projects/{repository_id}",
        user_path.parent,
    )
    overlay(documents["local"].get("settings", {}), str(local_path), local_path.parent if local_path else Path.cwd())
    overlay(overrides or {}, "invocation", Path.cwd())
    encoded = json.dumps(effective, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "schema_version": "1.0",
        "repository_id": repository_id,
        "settings": effective,
        "origins": origins,
        "fingerprint": hashlib.sha256(encoded).hexdigest(),
    }


def bootstrap_config(config, repo, user_config=None, overrides=None):
    resolved = resolve(repo, user_config, overrides, legacy=config)
    result = copy.deepcopy(config)
    result["optional_knowledge"] = {key: resolved["settings"][key] for key in ("knowledge", "cgc", "sourcegraph")}
    result["semantic_index"]["mode"] = MODES[resolved["settings"]["knowledge"]["mode"]]
    refs = resolved["settings"]["knowledge"]["base_refs"]
    if refs is not None:
        result["branch_selection"]["base_ref_candidates"] = refs
    return result


def ignore_local(repo):
    path = repo / ".gitignore"
    if path.is_symlink():
        raise SettingsError("Refusing to modify symlink .gitignore")
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    rule = "/ai_workflow/settings.local.json"
    if rule not in text.splitlines():
        path.write_text(text + ("\n" if text and not text.endswith("\n") else "") + rule + "\n", encoding="utf-8")


def configure(repo, apply=False):
    """Opt in without copying legacy settings or replacing authored files."""
    repo = Path(repo).resolve()
    if not repo.is_dir():
        raise SettingsError("Project directory must exist")
    target = repo / "ai_workflow/settings.json"
    if target.exists() or target.is_symlink():
        raise SettingsError("settings.json already exists; inspect and edit it explicitly")
    if target.parent.is_symlink() or (repo / ".gitignore").is_symlink():
        raise SettingsError("Refusing configuration through a symlink")
    data = {"schema_version": "1.0", "repository_id": identity(repo, {}) or "uuid:" + str(uuid.uuid4()), "settings": {}}
    result = {
        "apply": apply,
        "create": str(target),
        "content": data,
        "append_ignore": "/ai_workflow/settings.local.json",
        "legacy_files": "preserved; loaded at shared-project precedence",
    }
    if apply:
        # Check ignore file readability/type before creating the settings file.
        ignore = repo / ".gitignore"
        if ignore.exists():
            ignore.read_text(encoding="utf-8")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(data, indent=2) + "\n")
        ignore_local(repo)
    return result


def cli_overrides(items):
    result = {}
    for item in items:
        try:
            key, raw = item.split("=", 1)
            section, field = key.split(".")
            result.setdefault(section, {})[field] = json.loads(raw)
        except ValueError as error:
            raise SettingsError("--set requires section.key=JSON_VALUE") from error
    validate_settings(result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=["inspect", "configure", "migrate"],
        help="inspect settings or configure project files (migrate is a deprecated alias)",
    )
    parser.add_argument("--repo")
    parser.add_argument("--user-config")
    parser.add_argument("--set", action="append", default=[])
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command in ("configure", "migrate"):
            if not args.repo or args.set or args.user_config:
                raise SettingsError("configure requires --repo and does not accept overrides")
            if args.command == "migrate":
                print("migrate is deprecated; use configure instead.", file=sys.stderr)
            result = configure(args.repo, args.apply)
        else:
            if args.apply:
                raise SettingsError("--apply is only valid for configure")
            result = resolve(args.repo, args.user_config, cli_overrides(args.set))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (SettingsError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
