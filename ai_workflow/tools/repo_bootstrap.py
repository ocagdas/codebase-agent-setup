#!/usr/bin/env python3
"""Provider neutral repository knowledge bootstrap and delta preparation."""

from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Iterable

if __package__:
    from .settings import bootstrap_config, SettingsError
    from .bootstrap_validation import BootstrapError, load_config, branch_layout
    from .knowledge_state import (
        atomic_json,
        atomic_text,
        read_json,
        stable_hash,
        load_state,
        load_file_index,
        validate_request,
    )
else:
    from settings import bootstrap_config, SettingsError
    from bootstrap_validation import BootstrapError, load_config, branch_layout
    from knowledge_state import (
        atomic_json,
        atomic_text,
        read_json,
        stable_hash,
        load_state,
        load_file_index,
        validate_request,
    )


SCRIPT_PATH = Path(__file__).resolve()
DEFAULT_CONFIG = SCRIPT_PATH.parent.parent / "bootstrap.json"


def run_git(repo: Path, args: list[str], check: bool = True) -> bytes:
    process = subprocess.run(
        ["git", "-C", str(repo), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and process.returncode != 0:
        message = process.stderr.decode("utf-8", errors="replace").strip()
        raise BootstrapError(f"Git command failed: {' '.join(args)}: {message}")
    return process.stdout


def git_text(repo: Path, args: list[str], check: bool = True) -> str:
    return run_git(repo, args, check).decode("utf-8", errors="replace").strip()


def repository_root(candidate: Path) -> Path:
    output = git_text(candidate.resolve(), ["rev-parse", "--show-toplevel"])
    return Path(output).resolve()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def branch_name(repo: Path, explicit: str | None) -> str:
    if explicit:
        return explicit
    symbolic = git_text(repo, ["symbolic-ref", "--quiet", "--short", "HEAD"], False)
    if symbolic:
        return symbolic
    for variable in (
        "AI_SOURCE_BRANCH",
        "GITHUB_HEAD_REF",
        "CI_MERGE_REQUEST_SOURCE_BRANCH_NAME",
        "BUILD_SOURCEBRANCHNAME",
    ):
        value = os.environ.get(variable)
        if value:
            return value
    return f"detached/{git_text(repo, ['rev-parse', '--short=12', 'HEAD'])}"


def branch_key(branch: str) -> str:
    readable = re.sub(r"[^A-Za-z0-9_.]+", "__", branch).strip("_") or "branch"
    readable = readable[:80]
    suffix = hashlib.sha256(branch.encode("utf-8")).hexdigest()[:8]
    return f"{readable}__{suffix}"


def matches_any(path: str, patterns: Iterable[str]) -> bool:
    for pattern in patterns:
        if fnmatch.fnmatch(path, pattern):
            return True
        if pattern.startswith("**/") and fnmatch.fnmatch(path, pattern[3:]):
            return True
    return False


def selected_path(path: str, config: dict[str, Any]) -> bool:
    selection = config["source_selection"]
    normalised = path.replace(os.sep, "/")
    if matches_any(normalised, selection["exclude_globs"]):
        return False
    if normalised in selection.get("include_root_files", []):
        return True
    return matches_any(normalised, selection["include_globs"])


def branch_selected(branch: str, config: dict[str, Any]) -> bool:
    selection = config["branch_selection"]
    included = any(re.search(pattern, branch) for pattern in selection["include_regex"])
    excluded = any(re.search(pattern, branch) for pattern in selection["exclude_regex"])
    return included and not excluded


def branch_state_root(repo: Path, branch: str, selected: bool, config: dict[str, Any]) -> Path:
    directory = (
        config["layer_storage"]["matching_branch_directory"]
        if selected
        else config["layer_storage"]["other_branch_directory"]
    )
    return repo / config["state_directory"] / directory / branch_key(branch)


def head_commit(repo: Path) -> str:
    return git_text(repo, ["rev-parse", "HEAD"])


def revision_exists(repo: Path, revision: str) -> bool:
    process = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-e", f"{revision}^{{commit}}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return process.returncode == 0


def is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    process = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", ancestor, descendant],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return process.returncode == 0


def resolve_base_ref(repo: Path, explicit: str | None, config: dict[str, Any]) -> str | None:
    candidates = [explicit] if explicit else config["branch_selection"]["base_ref_candidates"]
    for candidate in candidates:
        if candidate and revision_exists(repo, candidate):
            return candidate
    return None


def parse_name_status(data: bytes) -> list[dict[str, str]]:
    tokens = data.decode("utf-8", errors="surrogateescape").split("\0")
    if tokens and tokens[-1] == "":
        tokens.pop()
    changes: list[dict[str, str]] = []
    index = 0
    while index < len(tokens):
        status = tokens[index]
        index += 1
        kind = status[:1]
        if kind in {"R", "C"}:
            if index + 1 >= len(tokens):
                raise BootstrapError("Invalid Git rename or copy record")
            old_path, new_path = tokens[index], tokens[index + 1]
            index += 2
            changes.append({"status": status, "old_path": old_path, "path": new_path})
        else:
            if index >= len(tokens):
                raise BootstrapError("Invalid Git change record")
            changes.append({"status": status, "path": tokens[index]})
            index += 1
    return changes


def committed_changes(repo: Path, base: str, target: str = "HEAD") -> list[dict[str, str]]:
    data = run_git(repo, ["diff", "--name-status", "-z", "-M", base, target, "--"])
    return parse_name_status(data)


def worktree_changes(repo: Path) -> list[dict[str, str]]:
    changes = parse_name_status(run_git(repo, ["diff", "--name-status", "-z", "-M", "--"]))
    changes.extend(parse_name_status(run_git(repo, ["diff", "--cached", "--name-status", "-z", "-M", "--"])))
    untracked = run_git(repo, ["ls-files", "--others", "--exclude-standard", "-z"])
    for path in untracked.decode("utf-8", errors="surrogateescape").split("\0"):
        if path:
            changes.append({"status": "?", "path": path})
    return merge_changes(changes)


def merge_changes(changes: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    merged: dict[str, dict[str, str]] = {}
    for change in changes:
        key = change["path"]
        existing = merged.get(key)
        if existing is None:
            merged[key] = dict(change)
        else:
            old_path = change.get("old_path") or existing.get("old_path")
            merged[key] = {"status": "M", "path": key}
            if old_path:
                merged[key]["old_path"] = old_path
    return [merged[key] for key in sorted(merged)]


def relevant_changes(changes: Iterable[dict[str, str]], config: dict[str, Any]) -> list[dict[str, str]]:
    result = []
    for change in changes:
        paths = [change["path"]]
        if "old_path" in change:
            paths.append(change["old_path"])
        if any(selected_path(path, config) for path in paths):
            result.append(change)
    return result


def current_fingerprint(repo: Path, head: str, changes: list[dict[str, str]]) -> str:
    records = []
    for change in changes:
        path = repo / change["path"]
        record: dict[str, Any] = dict(change)
        if path.is_symlink():
            target = os.readlink(path)
            record["sha256"] = sha256_bytes(target.encode("utf-8", errors="surrogateescape"))
            record["size"] = len(target.encode("utf-8", errors="surrogateescape"))
            record["kind"] = "symlink"
        elif path.is_file():
            record["sha256"] = sha256_file(path)
            record["size"] = path.stat().st_size
        records.append(record)
    return stable_hash({"head": head, "worktree": records})


def tracked_and_untracked_files(repo: Path, config: dict[str, Any]) -> list[str]:
    data = run_git(repo, ["ls-files", "-co", "--exclude-standard", "-z"])
    paths = data.decode("utf-8", errors="surrogateescape").split("\0")
    return sorted(
        {
            path
            for path in paths
            if path and selected_path(path, config) and ((repo / path).is_file() or (repo / path).is_symlink())
        }
    )


def file_record(repo: Path, path: str) -> dict[str, Any]:
    absolute = repo / path
    if absolute.is_symlink():
        target = os.readlink(absolute)
        encoded = target.encode("utf-8", errors="surrogateescape")
        return {
            "path": path,
            "sha256": sha256_bytes(encoded),
            "size": len(encoded),
            "suffix": absolute.suffix.lower(),
            "kind": "symlink",
            "target": target,
        }
    return {
        "path": path,
        "sha256": sha256_file(absolute),
        "size": absolute.stat().st_size,
        "suffix": absolute.suffix.lower(),
        "kind": "file",
    }


def revision_file_record(repo: Path, revision: str, path: str) -> dict[str, Any]:
    data = run_git(repo, ["show", f"{revision}:{path}"])
    return {
        "path": path,
        "sha256": sha256_bytes(data),
        "size": len(data),
        "suffix": Path(path).suffix.lower(),
        "kind": "git_blob",
        "source_revision": revision,
    }


def base_file_index(repo: Path, revision: str, config: dict[str, Any]) -> dict[str, Any]:
    data = run_git(repo, ["ls-tree", "-r", "-z", "--full-tree", revision])
    records = []
    for token in data.decode("utf-8", errors="surrogateescape").split("\0"):
        if not token:
            continue
        metadata, path = token.split("\t", 1)
        mode, kind, object_id = metadata.split(" ", 2)
        if kind != "blob" or not selected_path(path, config):
            continue
        records.append(
            {
                "path": path,
                "git_object_id": object_id,
                "git_mode": mode,
                "suffix": Path(path).suffix.lower(),
            }
        )
    return {
        "schema_version": "1.0",
        "source_commit": revision,
        "files": sorted(records, key=lambda item: item["path"]),
    }


def overlay_file_index(
    repo: Path,
    changes: list[dict[str, str]],
    source_revision: str | None,
) -> dict[str, Any]:
    records = []
    for change in changes:
        old_path = change.get("old_path")
        if old_path:
            records.append({"operation": "delete", "path": old_path})
        path = change["path"]
        if change["status"].startswith("D"):
            records.append({"operation": "delete", "path": path})
            continue
        absolute = repo / path
        if source_revision is None:
            if not absolute.is_file() and not absolute.is_symlink():
                records.append({"operation": "delete", "path": path})
                continue
            record = file_record(repo, path)
            record["source_revision"] = "worktree"
        else:
            record = revision_file_record(repo, source_revision, path)
        record["operation"] = "upsert"
        if old_path:
            record["renamed_from"] = old_path
        records.append(record)
    return {
        "schema_version": "1.0",
        "source_revision": source_revision or "worktree",
        "records": records,
    }


def semantic_index_status(
    repo: Path,
    config: dict[str, Any],
    layers: dict[str, Path],
    analysis_mode: str,
    head: str,
    base_commit: str | None,
    worktree_fingerprint: str,
) -> dict[str, Any]:
    semantic = config["semantic_index"]
    mode = semantic["mode"]
    if mode not in {"disabled", "auto", "required"}:
        raise BootstrapError(f"Unsupported semantic index mode: {mode}")
    compile_database = next(
        (repo / candidate for candidate in semantic["compile_database_candidates"] if (repo / candidate).is_file()),
        None,
    )
    manifest_paths = {
        name: path / semantic["manifest_file"]
        for name, path in layers.items()
        if name in {"base", "branch_overlay", "worktree_overlay"}
    }
    expected_commits = {
        "base": base_commit,
        "branch_overlay": head,
        "worktree_overlay": head,
    }
    existing_layers = []
    incompatible_layers: dict[str, str] = {}
    for name, path in manifest_paths.items():
        if not path.is_file():
            continue
        try:
            manifest = read_json(path)
        except (BootstrapError, OSError, json.JSONDecodeError) as error:
            incompatible_layers[name] = f"invalid_manifest: {error}"
            continue
        if (
            not isinstance(manifest, dict)
            or not isinstance(manifest.get("validation"), dict)
            or not isinstance(manifest.get("trust"), dict)
        ):
            incompatible_layers[name] = "invalid_manifest_types"
            continue
        required_fields = {
            "schema_version",
            "layer",
            "repository_id",
            "source_commit",
            "branch",
            "generator",
            "compile_context_hash",
            "inputs_hash",
            "created_at",
            "trust",
            "validation",
        }
        missing_fields = sorted(required_fields - set(manifest))
        if missing_fields:
            incompatible_layers[name] = f"manifest_missing_fields: {','.join(missing_fields)}"
            continue
        if manifest.get("schema_version") != "1.0" or manifest.get("layer") != name:
            incompatible_layers[name] = "manifest_schema_or_layer_mismatch"
            continue
        if manifest.get("validation", {}).get("status") != "pass":
            incompatible_layers[name] = "manifest_validation_not_passed"
            continue
        if not manifest.get("trust", {}).get("trusted", False):
            incompatible_layers[name] = "manifest_not_trusted"
            continue
        expected_commit = expected_commits[name]
        if expected_commit is None or manifest.get("source_commit") != expected_commit:
            incompatible_layers[name] = "source_commit_mismatch"
            continue
        if name == "worktree_overlay" and manifest.get("worktree_fingerprint") != worktree_fingerprint:
            incompatible_layers[name] = "worktree_fingerprint_mismatch"
            continue
        existing_layers.append(name)
    query_configured = bool(semantic.get("query_command"))
    update_commands = {
        "base": semantic.get("base_update_command"),
        "branch_overlay": semantic.get("branch_overlay_update_command"),
        "worktree_overlay": semantic.get("worktree_overlay_update_command"),
    }
    writable_update_commands = {
        name: command
        for name, command in update_commands.items()
        if name in {"branch_overlay", "worktree_overlay"} and command
    }
    update_configured = bool(writable_update_commands) and compile_database is not None
    create_allowed = bool(semantic.get("create_when_missing"))
    use_for_queries = mode != "disabled" and query_configured and bool(existing_layers)
    update_enabled = mode != "disabled" and update_configured and (bool(existing_layers) or create_allowed)

    required_layers = {"base"}
    for name in ("branch_overlay", "worktree_overlay"):
        overlay = read_json(layers[name] / "file_overlay.json")
        if overlay and overlay.get("records"):
            required_layers.add(name)
    missing_layers = sorted(required_layers - set(existing_layers))
    current_view_complete = query_configured and not missing_layers
    fallback_needed = not current_view_complete

    if mode == "disabled":
        reason = "semantic_index_disabled"
    elif incompatible_layers and not existing_layers:
        reason = "semantic_index_incompatible"
    elif not existing_layers and not create_allowed:
        reason = "semantic_index_not_present"
    elif not query_configured:
        reason = "semantic_query_adapter_not_configured"
    elif use_for_queries and analysis_mode != "none" and not update_enabled:
        reason = "semantic_index_available_but_not_updateable"
    else:
        reason = "semantic_index_available"

    if mode == "required" and not current_view_complete:
        raise BootstrapError(
            f"Required semantic index is unavailable: {reason}; "
            f"missing current layers: {missing_layers}. Refresh adapters before retrying."
        )

    return {
        "mode": mode,
        "current_view_complete": mode != "disabled" and current_view_complete,
        "missing_current_layers": missing_layers,
        "trust_verification": "manifest_declaration_only",
        "backend": semantic.get("backend"),
        "use_for_queries": use_for_queries,
        "update_enabled": update_enabled,
        "update_required": update_enabled and analysis_mode != "none",
        "fallback_to_direct_source": mode != "required" and fallback_needed,
        "reason": reason,
        "compile_database": str(compile_database.relative_to(repo)) if compile_database else None,
        "existing_layers": existing_layers,
        "incompatible_layers": incompatible_layers,
        "manifest_paths": {name: str(path.relative_to(repo)) for name, path in manifest_paths.items()},
        "query_command": semantic.get("query_command"),
        "update_commands": update_commands,
        "session_writable_layers": sorted(writable_update_commands),
        "base_update_allowed_in_session": False,
    }


def build_candidate_index(
    repo: Path,
    config: dict[str, Any],
    mode: str,
    previous_index: dict[str, Any] | None,
    changes: list[dict[str, str]],
    head: str,
    fingerprint: str,
) -> dict[str, Any]:
    current_paths = set(tracked_and_untracked_files(repo, config))
    dirty = relevant_changes(worktree_changes(repo), config)
    dirty_paths = sorted({item[key] for item in dirty for key in ("path", "old_path") if key in item})
    before = {item["path"]: item for item in previous_index.get("files", [])} if previous_index else {}
    # Old indices lack dirty-path provenance: refresh once rather than risk missing a reversion.
    reusable = mode == "incremental_analysis" and previous_index is not None and "dirty_paths" in previous_index
    affected = {item[key] for item in changes for key in ("path", "old_path") if key in item}
    affected.update(dirty_paths)
    affected.update(previous_index.get("dirty_paths", []) if previous_index else [])
    files = {
        path: before[path] if reusable and path in before and path not in affected else file_record(repo, path)
        for path in current_paths
    }
    return {
        "schema_version": "1.0",
        "source_commit": head,
        "worktree_fingerprint": fingerprint,
        "dirty_paths": dirty_paths,
        "files": [files[path] for path in sorted(files)],
    }


def change_has_global_invalidation(change: dict[str, str], config: dict[str, Any]) -> bool:
    paths = [change["path"]]
    if change.get("old_path"):
        paths.append(change["old_path"])
    return any(matches_any(path, config["global_invalidation_globs"]) for path in paths)


def change_is_header(change: dict[str, str], config: dict[str, Any]) -> bool:
    paths = [change["path"]]
    if change.get("old_path"):
        paths.append(change["old_path"])
    return any(matches_any(path, config["header_globs"]) for path in paths)


def render_delta_markdown(delta: dict[str, Any]) -> str:
    lines = [
        "# Branch Delta",
        "",
        f"Branch: `{delta['branch']}`",
        "",
        f"Current commit: `{delta['source_commit']}`",
        "",
        f"Base reference: `{delta.get('base_ref') or 'unresolved'}`",
        "",
        f"Merge base: `{delta.get('merge_base') or 'unresolved'}`",
        "",
        "## Changed paths",
        "",
    ]
    if not delta["changes"]:
        lines.append("No relevant changes were detected.")
    for change in delta["changes"]:
        old = f" from `{change['old_path']}`" if change.get("old_path") else ""
        lines.append(f"1. `{change['status']}` `{change['path']}`{old}")
    lines.extend(
        [
            "",
            "## Invalidation",
            "",
            f"Global invalidation: `{str(delta['global_invalidation']).lower()}`",
            "",
            f"Changed headers: `{len(delta['changed_headers'])}`",
            "",
        ]
    )
    return "\n".join(lines)


def effective_config(args, repo):
    """Resolve project configuration identically for prepare, complete and status."""
    project_config = repo / "ai_workflow/bootstrap.json"
    if args.config:
        config_path = Path(args.config).resolve()
    elif project_config.exists() or project_config.is_symlink():
        config_path = project_config
    else:
        config_path = DEFAULT_CONFIG
    knowledge = {key: value for key, value in (("mode", getattr(args, "knowledge_mode", None)),) if value is not None}
    return bootstrap_config(
        load_config(config_path), repo, getattr(args, "user_config", None), {"knowledge": knowledge}
    )


def choose_analysis(repo, config, previous_state, config_fingerprint, head, worktree, unchanged, force_full):
    """Choose analysis scope without writing any cache files."""
    if force_full or previous_state is None:
        mode = "full_analysis"
        changes = []
        reasons = ["forced" if force_full else "knowledge_state_missing"]
    elif previous_state.get("config_fingerprint") != config_fingerprint:
        mode, changes, reasons = "full_analysis", [], ["configuration_changed"]
    elif unchanged:
        mode = "none"
        changes = []
        reasons = []
    else:
        previous_commit = previous_state.get("source_commit", "")
        if (
            not previous_commit
            or not revision_exists(repo, previous_commit)
            or not is_ancestor(repo, previous_commit, head)
        ):
            mode = "full_analysis"
            changes = []
            reasons = ["previous_index_is_not_a_current_ancestor"]
        else:
            changes = relevant_changes(committed_changes(repo, previous_commit), config)
            changes = merge_changes([*changes, *worktree])
            global_paths = [item["path"] for item in changes if change_has_global_invalidation(item, config)]
            if global_paths:
                mode = "full_analysis"
                reasons = ["global_invalidation", *global_paths]
            else:
                mode = "incremental_analysis"
                reasons = ["repository_changed"]

    return mode, changes, reasons


def write_inventory_layers(
    repo, config, config_fingerprint, layers, merge_base, head, committed_branch_changes, worktree
):
    """Persist immutable base inventory and current branch/worktree overlays."""
    base_root = layers["base"]
    branch_overlay_root = layers["branch_overlay"]
    worktree_overlay_root = layers["worktree_overlay"]
    if merge_base:
        base_index_path = base_root / f"file_index_{config_fingerprint[:16]}.json"
        if not base_index_path.is_file():
            atomic_json(base_index_path, base_file_index(repo, merge_base, config))
    atomic_json(
        branch_overlay_root / "file_overlay.json",
        overlay_file_index(repo, committed_branch_changes, head),
    )
    atomic_json(
        worktree_overlay_root / "file_overlay.json",
        overlay_file_index(repo, worktree, None),
    )


def prepare(args: argparse.Namespace) -> dict[str, Any]:
    repo = repository_root(Path(args.repo))
    object_format = git_text(repo, ["rev-parse", "--show-object-format"])
    config = effective_config(args, repo)
    config_fingerprint = stable_hash(config)
    head = head_commit(repo)
    branch = branch_name(repo, args.branch)
    selected = branch_selected(branch, config)
    state_root = branch_state_root(repo, branch, selected, config)
    layout = branch_layout(config, state_root)
    state_path = layout["state"]
    pending_path = layout["pending_request_file"]
    candidate_path = layout["candidate"]
    previous_state = load_state(state_path, object_format)
    if previous_state and "file_index_digest" not in previous_state:
        previous_state = None  # Refresh pre-integrity caches once.
    worktree = relevant_changes(worktree_changes(repo), config)
    fingerprint = current_fingerprint(repo, head, worktree)

    unchanged = bool(
        previous_state
        and previous_state.get("config_fingerprint") == config_fingerprint
        and previous_state.get("source_commit") == head
        and previous_state.get("worktree_fingerprint") == fingerprint
        and (layout["repository_analysis_file"]).is_file()
        and (layout["file_index_file"]).is_file()
    )

    mode, changes, reasons = choose_analysis(
        repo, config, previous_state, config_fingerprint, head, worktree, unchanged, args.force_full
    )

    # Only compatible caches are candidates for reuse. Configuration changes,
    # forced rebuilds and ancestry invalidation must not inspect the new layout
    # using old integrity metadata.
    previous_index = None
    if mode != "full_analysis":
        previous_index = load_file_index(layout["file_index_file"], object_format)
        if previous_index is None or stable_hash(previous_index) != previous_state["file_index_digest"]:
            raise BootstrapError("Saved file index changed; run prepare --force-full")

    base_ref = resolve_base_ref(repo, args.base_ref, config)
    merge_base = git_text(repo, ["merge-base", base_ref, "HEAD"], False) if base_ref else ""
    committed_branch_changes = relevant_changes(committed_changes(repo, merge_base), config) if merge_base else []
    branch_changes = merge_changes([*committed_branch_changes, *worktree])
    base_root = (
        repo
        / config["state_directory"]
        / config["layer_storage"]["base_directory"]
        / branch_key(base_ref or "unresolved")
        / (merge_base or "unresolved")
    )
    branch_overlay_root = layout["branch_overlay_directory"]
    worktree_overlay_root = layout["worktree_overlay_directory"]
    layers = {
        "base": base_root,
        "branch_overlay": branch_overlay_root,
        "worktree_overlay": worktree_overlay_root,
    }
    write_inventory_layers(
        repo, config, config_fingerprint, layers, merge_base, head, committed_branch_changes, worktree
    )
    changed_headers = [item["path"] for item in branch_changes if change_is_header(item, config)]
    branch_delta = {
        "schema_version": "1.0",
        "branch": branch,
        "source_commit": head,
        "worktree_fingerprint": fingerprint,
        "base_ref": base_ref,
        "merge_base": merge_base or None,
        "changes": branch_changes,
        "committed_branch_changes": committed_branch_changes,
        "worktree_changes": worktree,
        "changed_headers": changed_headers,
        "global_invalidation": any(change_has_global_invalidation(item, config) for item in branch_changes),
    }
    atomic_json(layout["branch_delta_data_file"], branch_delta)
    atomic_text(layout["branch_delta_file"], render_delta_markdown(branch_delta))
    semantic_status = semantic_index_status(
        repo,
        config,
        layers,
        mode,
        head,
        merge_base or None,
        fingerprint,
    )
    layer_output = {
        "query_precedence": config["layer_storage"]["query_precedence"],
        "base": str(base_root.relative_to(repo)),
        "branch_overlay": str(branch_overlay_root.relative_to(repo)),
        "worktree_overlay": str(worktree_overlay_root.relative_to(repo)),
        "base_source_commit": merge_base or None,
        "base_ref": base_ref,
        "branch_overlay_source_commit": head,
        "worktree_fingerprint": fingerprint,
        "base_remote_namespace": config["semantic_index"]["base_remote_namespace"].format(
            base_ref=base_ref or "unresolved", commit=merge_base or "unresolved", branch=branch
        ),
        "matching_branch_remote_namespace": config["semantic_index"]["matching_branch_remote_namespace"].format(
            base_ref=base_ref or "unresolved", commit=head, branch=branch
        ),
        "publish_matching_branch_overlay": bool(
            selected and config["semantic_index"]["publish_matching_branch_overlays"]
        ),
        "publish_worktree_overlay": bool(config["semantic_index"]["publish_worktree_overlays"]),
    }

    if mode == "none":
        if pending_path.exists():
            pending_path.unlink()
        return {
            "schema_version": "1.0",
            "action_required": "none",
            "branch": branch,
            "source_commit": head,
            "state_directory": str(state_root.relative_to(repo)),
            "branch_delta": str((layout["branch_delta_file"]).relative_to(repo)),
            "shared_publish_allowed": layer_output["publish_matching_branch_overlay"],
            "layers": layer_output,
            "semantic_index": semantic_status,
        }

    candidate = build_candidate_index(repo, config, mode, previous_index, changes, head, fingerprint)
    if previous_index is not None and mode == "incremental_analysis":
        before = {item["path"]: item for item in previous_index.get("files", [])}
        after = {item["path"]: item for item in candidate.get("files", [])}
        changes = [
            {"path": path, "status": "D" if path not in after else "A" if path not in before else "M"}
            for path in sorted(before.keys() | after.keys())
            if before.get(path) != after.get(path)
        ]
        if any(change_has_global_invalidation(item, config) for item in changes):
            mode, reasons = "full_analysis", ["global_invalidation"]
    atomic_json(candidate_path, candidate)
    if (
        mode == "incremental_analysis"
        and previous_index is not None
        and stable_hash(previous_index.get("files", [])) == stable_hash(candidate.get("files", []))
    ):
        final_index = layout["file_index_file"]
        atomic_json(final_index, candidate)
        refreshed_state = dict(previous_state)
        refreshed_state.update(
            {
                "source_commit": head,
                "worktree_fingerprint": fingerprint,
                "analysis_mode": "metadata_refresh",
                "file_index_digest": stable_hash(candidate),
                "file_index": str(final_index.relative_to(repo)),
                "completed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            }
        )
        atomic_json(state_path, refreshed_state)
        if pending_path.exists():
            pending_path.unlink()
        if candidate_path.exists():
            candidate_path.unlink()
        return {
            "schema_version": "1.0",
            "action_required": "none",
            "reason": "relevant_content_unchanged",
            "branch": branch,
            "source_commit": head,
            "state_directory": str(state_root.relative_to(repo)),
            "branch_delta": str((layout["branch_delta_file"]).relative_to(repo)),
            "shared_publish_allowed": layer_output["publish_matching_branch_overlay"],
            "layers": layer_output,
            "semantic_index": semantic_status,
        }
    request_id = f"{head[:12]}_{fingerprint[:12]}"
    delta_output = layout["delta_directory"] / f"{request_id}.md"
    repository_analysis = layout["repository_analysis_file"]
    required_outputs = [repository_analysis]
    if mode == "incremental_analysis":
        required_outputs.append(delta_output)
    request = {
        "schema_version": "1.0",
        "request_id": request_id,
        "config_fingerprint": config_fingerprint,
        "action_required": mode,
        "reasons": reasons,
        "branch": branch,
        "branch_matches_shared_policy": selected,
        "shared_publish_allowed": layer_output["publish_matching_branch_overlay"],
        "layers": layer_output,
        "semantic_index": semantic_status,
        "source_commit": head,
        "worktree_fingerprint": fingerprint,
        "previous_source_commit": previous_state.get("source_commit") if previous_state else None,
        "state_directory": str(state_root.relative_to(repo)),
        "candidate_file_index": str(candidate_path.relative_to(repo)),
        "candidate_digest": stable_hash(candidate),
        "branch_delta": str((layout["branch_delta_file"]).relative_to(repo)),
        "branch_delta_data": str((layout["branch_delta_data_file"]).relative_to(repo)),
        "changed_paths": changes,
        "changed_headers": [item["path"] for item in changes if change_is_header(item, config)],
        "dependency_closure_required": any(change_is_header(item, config) for item in changes),
        "required_analysis_outputs": [str(path.relative_to(repo)) for path in required_outputs],
        "prepared_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    atomic_json(pending_path, request)
    return request


def complete(args: argparse.Namespace) -> dict[str, Any]:
    repo = repository_root(Path(args.repo))
    object_format = git_text(repo, ["rev-parse", "--show-object-format"])
    config = effective_config(args, repo)
    branch = branch_name(repo, args.branch)
    selected = branch_selected(branch, config)
    state_root = branch_state_root(repo, branch, selected, config)
    layout = branch_layout(config, state_root)
    pending_path = layout["pending_request_file"]
    request = read_json(pending_path)
    if request is None:
        raise BootstrapError("No pending analysis request exists for this branch")
    validate_request(request, pending_path, repo, layout, branch, object_format)
    if request.get("config_fingerprint") != stable_hash(config):
        raise BootstrapError("Configuration changed after preparation; run prepare again")
    head = head_commit(repo)
    worktree = relevant_changes(worktree_changes(repo), config)
    fingerprint = current_fingerprint(repo, head, worktree)
    if request["source_commit"] != head or request["worktree_fingerprint"] != fingerprint:
        raise BootstrapError("Repository changed after analysis preparation; run prepare again")
    missing = []
    for relative in request["required_analysis_outputs"]:
        path = repo / relative
        if not path.is_file() or path.stat().st_size == 0:
            missing.append(relative)
    if missing:
        raise BootstrapError(f"Required analysis outputs are missing or empty: {', '.join(missing)}")
    candidate_path = layout["candidate"]
    candidate = load_file_index(candidate_path, object_format)
    if candidate is None:
        raise BootstrapError("Candidate file index is missing")
    if (
        candidate.get("source_commit") != head
        or candidate.get("worktree_fingerprint") != fingerprint
        or stable_hash(candidate) != request["candidate_digest"]
    ):
        raise BootstrapError("Candidate index changed after preparation; run prepare again")
    final_index = layout["file_index_file"]
    atomic_json(final_index, candidate)
    state = {
        "schema_version": "1.0",
        "branch": branch,
        "source_commit": head,
        "worktree_fingerprint": fingerprint,
        "request_id": request["request_id"],
        "config_fingerprint": request["config_fingerprint"],
        "analysis_mode": request["action_required"],
        "file_index_digest": stable_hash(candidate),
        "repository_analysis": request["required_analysis_outputs"][0],
        "file_index": str(final_index.relative_to(repo)),
        "completed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    atomic_json(layout["state"], state)
    pending_path.unlink()
    if candidate_path.exists():
        candidate_path.unlink()
    return {
        "schema_version": "1.0",
        "status": "completed",
        "branch": branch,
        "source_commit": head,
        "state_directory": str(state_root.relative_to(repo)),
        "analysis_mode": request["action_required"],
    }


def status(args: argparse.Namespace) -> dict[str, Any]:
    repo = repository_root(Path(args.repo))
    object_format = git_text(repo, ["rev-parse", "--show-object-format"])
    config = effective_config(args, repo)
    branch = branch_name(repo, args.branch)
    selected = branch_selected(branch, config)
    state_root = branch_state_root(repo, branch, selected, config)
    layout = branch_layout(config, state_root)
    state = load_state(layout["state"], object_format)
    head = head_commit(repo)
    worktree = relevant_changes(worktree_changes(repo), config)
    fingerprint = current_fingerprint(repo, head, worktree)
    fresh = bool(
        state
        and state.get("source_commit") == head
        and state.get("config_fingerprint") == stable_hash(config)
        and state.get("worktree_fingerprint") == fingerprint
        and state.get("file_index_digest") == stable_hash(load_file_index(layout["file_index_file"], object_format))
    )
    return {
        "schema_version": "1.0",
        "branch": branch,
        "source_commit": head,
        "state_directory": str(state_root.relative_to(repo)),
        "knowledge_exists": state is not None,
        "knowledge_fresh": fresh,
        "analysed_source_commit": state.get("source_commit") if state else None,
        "branch_matches_shared_policy": selected,
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("command", choices=("prepare", "complete", "status"))
    result.add_argument("--repo", default=".")
    result.add_argument("--config")
    result.add_argument("--user-config")
    result.add_argument("--knowledge-mode", choices=("auto", "source", "index"))
    result.add_argument("--branch")
    result.add_argument("--base-ref")
    result.add_argument("--force-full", action="store_true")
    result.add_argument("--pretty", action="store_true")
    return result


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare(args)
        elif args.command == "complete":
            result = complete(args)
        else:
            result = status(args)
        print(json.dumps(result, indent=2 if args.pretty else None, sort_keys=True))
        return 0
    except (BootstrapError, SettingsError, OSError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "error", "message": str(error)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
