"""Bootstrap configuration contract, independent of consumer defaults."""

import json
from pathlib import Path, PureWindowsPath
import re
from typing import Any


class BootstrapError(RuntimeError):
    pass


def validate_config(config, path):
    """Validate the full bootstrap contract before computing or writing state."""

    def fail(field, message):
        raise BootstrapError(f"{path}: {field}: {message}")

    schema_path = Path(__file__).resolve().parent.parent / "bootstrap.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    def check(value, rule, field):
        kinds = rule["type"] if isinstance(rule["type"], list) else [rule["type"]]
        types = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}
        if not any(type(value) is types[kind] for kind in kinds):
            fail(field, "expected " + " or ".join(kinds))
        if isinstance(value, dict):
            extra = set(value) - set(rule.get("properties", {}))
            if extra:
                fail(field, f"unsupported settings: {sorted(extra)}")
            for key in rule.get("required", []):
                if key not in value:
                    fail(f"{field}.{key}", "required setting is missing")
            for key, child in rule.get("properties", {}).items():
                if key in value:
                    check(value[key], child, f"{field}.{key}")
        if isinstance(value, list):
            for index, child in enumerate(value):
                check(child, rule["items"], f"{field}[{index}]")

    check(config, schema, "bootstrap")
    if config["schema_version"] != "1.0":
        fail("schema_version", "unsupported schema (expected 1.0)")
    if config["semantic_index"]["mode"] not in ("disabled", "auto", "required"):
        fail("semantic_index.mode", "expected disabled, auto or required")
    for key in ("include_regex", "exclude_regex"):
        for pattern in config["branch_selection"][key]:
            try:
                re.compile(pattern)
            except re.error as error:
                fail("branch_selection." + key, str(error))
    paths = [("state_directory", config["state_directory"])]
    paths += [("layer_storage." + k, v) for k, v in config["layer_storage"].items() if k.endswith("_directory")]
    paths += [("analysis." + k, v) for k, v in config["analysis"].items()]
    paths += [("semantic_index.manifest_file", config["semantic_index"]["manifest_file"])]
    for field, value in paths:
        candidate = Path(value)
        if (
            not value
            or PureWindowsPath(value).drive
            or "\\" in value
            or candidate.is_absolute()
            or ".." in candidate.parts
            or value == "."
            or "\x00" in value
        ):
            fail(field, "expected a nonempty relative path without parent traversal")
    precedence = config["layer_storage"]["query_precedence"]
    if sorted(precedence) != ["base", "branch_overlay", "worktree_overlay"]:
        fail("layer_storage.query_precedence", "expected each of base, branch_overlay and worktree_overlay once")
    for key in ("base_remote_namespace", "matching_branch_remote_namespace"):
        try:
            config["semantic_index"][key].format(base_ref="base", commit="commit", branch="branch")
        except (KeyError, ValueError, IndexError, AttributeError) as error:
            fail("semantic_index." + key, f"invalid namespace template: {error}")
    validate_layout(config, fail)
    return config


def load_config(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as handle:
            return validate_config(json.load(handle), path)
    except json.JSONDecodeError as error:
        raise BootstrapError(f"{path}: invalid JSON: {error}") from error


def branch_layout(config, root=Path(".")):
    """Single definition of branch-local outputs and reserved filenames."""
    return {
        "state": root / "state.json",
        "candidate": root / "candidate_file_index.json",
        **{key: root / value for key, value in config["analysis"].items()},
        **{
            key: root / config["layer_storage"][key]
            for key in ("branch_overlay_directory", "worktree_overlay_directory")
        },
    }


def validate_layout(config, fail):
    def overlaps(a, b):
        return a == b or a.startswith(b + "/") or b.startswith(a + "/")

    layout = branch_layout(config)
    # Case-folding prevents a configuration portable on Linux from aliasing on Windows.
    items = [(key, value.as_posix().casefold()) for key, value in layout.items()]
    for index, (key, path) in enumerate(items):
        for other, destination in items[index + 1 :]:
            if overlaps(path, destination):
                fail(key, f"output path overlaps {other}: {path} / {destination}")
    storage = config["layer_storage"]
    roots = [
        (key, Path(storage[key]).as_posix().casefold())
        for key in ("base_directory", "matching_branch_directory", "other_branch_directory")
    ]
    for index, (key, path) in enumerate(roots):
        for other, destination in roots[index + 1 :]:
            if overlaps(path, destination):
                fail("layer_storage." + key, f"overlaps {other}")
    manifest = Path(config["semantic_index"]["manifest_file"]).as_posix().casefold()
    if overlaps(manifest, "file_overlay.json") or (
        "/" not in manifest and manifest.startswith("file_index_") and manifest.endswith(".json")
    ):
        fail("semantic_index.manifest_file", "overlaps reserved inventory files")
