"""Atomic persistence, record contracts and integrity checks for local knowledge."""

from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import tempfile
from typing import Any

if __package__:
    from .bootstrap_validation import BootstrapError
else:
    from bootstrap_validation import BootstrapError


def valid_revision(value, object_format):
    length = {"sha1": 40, "sha256": 64}.get(object_format)
    return (
        length is not None
        and isinstance(value, str)
        and re.fullmatch(r"[0-9a-f]{" + str(length) + "}", value) is not None
    )


def atomic_json(path: Path, value: Any) -> None:
    atomic_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(value)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def read_json(path: Path) -> Any | None:
    if not path.is_file():
        return None
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise BootstrapError(f"{path}: expected a JSON object")
    return value


def stable_hash(value: Any) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def load_state(path, object_format="sha1"):
    value = read_json(path)
    if value is not None:
        if (
            value.get("schema_version") != "1.0"
            or any(
                not isinstance(value.get(key), str)
                for key in ("branch", "source_commit", "config_fingerprint", "worktree_fingerprint")
            )
            or not valid_revision(value["source_commit"], object_format)
            or not is_digest(value["config_fingerprint"])
            or not is_digest(value["worktree_fingerprint"])
            or ("file_index_digest" in value and not is_digest(value["file_index_digest"]))
        ):
            raise BootstrapError(f"{path}: invalid knowledge state; remove this cache state and run prepare")
    return value


def is_digest(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def validate_request(request, path, repo, layout, branch, object_format="sha1"):
    def fail():
        raise BootstrapError(f"{path}: invalid or old analysis request; run prepare again")

    if (
        request.get("schema_version") != "1.0"
        or request.get("branch") != branch
        or request.get("action_required") not in ("full_analysis", "incremental_analysis")
        or not is_digest(request.get("candidate_digest"))
        or any(
            not isinstance(request.get(key), str)
            for key in ("source_commit", "worktree_fingerprint", "config_fingerprint", "request_id")
        )
    ):
        fail()
    if (
        not valid_revision(request["source_commit"], object_format)
        or not is_digest(request["config_fingerprint"])
        or not is_digest(request["worktree_fingerprint"])
    ):
        fail()
    expected_id = request["source_commit"][:12] + "_" + request["worktree_fingerprint"][:12]
    if request["request_id"] != expected_id or not re.fullmatch(r"[0-9a-f]{12}_[0-9a-f]{12}", expected_id):
        fail()
    outputs = [str(layout["repository_analysis_file"].relative_to(repo))]
    if request["action_required"] == "incremental_analysis":
        outputs.append(str((layout["delta_directory"] / (expected_id + ".md")).relative_to(repo)))
    if request.get("required_analysis_outputs") != outputs or request.get("candidate_file_index") != str(
        layout["candidate"].relative_to(repo)
    ):
        fail()


def load_file_index(path, object_format="sha1"):
    value = read_json(path)
    if value is None:
        return None
    if (
        value.get("schema_version") != "1.0"
        or not isinstance(value.get("source_commit"), str)
        or not valid_revision(value["source_commit"], object_format)
        or not is_digest(value.get("worktree_fingerprint"))
    ):
        raise BootstrapError(f"{path}: invalid file index metadata; run prepare --force-full")
    records = value.get("files")
    if (
        not isinstance(records, list)
        or any(
            not isinstance(item, dict)
            or not isinstance(item.get("path"), str)
            or not is_digest(item.get("sha256"))
            or type(item.get("size")) is not int
            or item["size"] < 0
            for item in records
        )
        or len({item["path"] for item in records}) != len(records)
        or (
            "dirty_paths" in value
            and (
                not isinstance(value["dirty_paths"], list)
                or any(not isinstance(item, str) for item in value["dirty_paths"])
            )
        )
    ):
        raise BootstrapError(f"{path}: invalid file index; rebuild with --force-full")
    return value
