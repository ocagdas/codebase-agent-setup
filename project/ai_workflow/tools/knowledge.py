#!/usr/bin/env python3
"""Repository knowledge: run declared indexers, cache their output per file content, share it between clones.

This module ships no indexer. Every indexer is a command declared in settings, so the same wrapper serves
universal-ctags, tree-sitter, scip-clang or something that does not exist yet, with no code change and no
third-party dependency.

The unit of caching is a **file**, keyed by git's own blob hash of its content. Editing one file re-indexes one
file. A layer (base trunk / branch / worktree) is a manifest mapping path to key, not a monolithic artifact, so a
commit that touches 20 of 4,000 files leaves 3,980 cache hits behind.

Nothing here is the source of truth. Every artifact carries provenance so an agent can verify a claim with one read.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import quote

SCHEMA_VERSION = "1.0"
KINDS = ("symbols", "skeleton", "map", "summary", "scope")
GRANULARITIES = ("file", "directory", "scope")
LAYERS = ("base", "branch", "worktree")
# Lowest first. An overlay records only what differs from the layers beneath it.
BENEATH = {"base": (), "branch": ("base",), "worktree": ("branch", "base")}
MANIFEST = "manifest.json"
KEY = re.compile(r"^[0-9a-f]{64}$")
# Placeholders CAS substitutes in a declared command. Anything else is passed through untouched.
LIST_PLACEHOLDERS = ("{files}", "{paths}")


class KnowledgeError(ValueError):
    pass


def run_git(repo, args, check=True):
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if check and result.returncode != 0:
        raise KnowledgeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


class Indexer:
    def __init__(self, raw, position):
        if not isinstance(raw, dict):
            raise KnowledgeError(f"knowledge.indexers[{position}] must be an object")
        self.raw = dict(raw)
        self.id = raw.get("id")
        self.version = str(raw.get("version", ""))
        self.kind = raw.get("kind", "symbols")
        self.granularity = raw.get("granularity", "file")
        self.paths = list(raw.get("paths") or ["."])
        self.build_command = raw.get("build_command")
        self.query_command = raw.get("query_command")
        if not isinstance(self.id, str) or not self.id:
            raise KnowledgeError(f"knowledge.indexers[{position}] needs a non-empty string id")
        if self.kind not in KINDS:
            raise KnowledgeError(f"{self.id}: unknown kind {self.kind!r}; use one of {', '.join(KINDS)}")
        if self.granularity not in GRANULARITIES:
            raise KnowledgeError(
                f"{self.id}: unknown granularity {self.granularity!r}; use one of {', '.join(GRANULARITIES)}"
            )
        for name in ("build_command", "query_command"):
            command = getattr(self, name)
            if command is None:
                continue
            # A shell string would make every placeholder an injection point.
            if not isinstance(command, list) or not all(isinstance(part, str) for part in command):
                raise KnowledgeError(f"{self.id}: {name} must be a list of string arguments, not a shell string")
        if not self.build_command:
            raise KnowledgeError(f"{self.id}: needs a build_command")
        for path in self.paths:
            candidate = Path(path)
            if candidate.is_absolute() or ".." in candidate.parts:
                raise KnowledgeError(f"{self.id}: path {path!r} must stay inside the repository")


class Config:
    def __init__(self, repo, raw, indexers, cache, store, publication):
        self.repo = Path(repo).resolve()
        self.raw = raw
        self.indexers = indexers
        self.cache = cache
        self.store = store
        self.publication = publication

    @classmethod
    def from_settings(cls, repo, settings):
        repo = Path(repo).resolve()
        raw = dict(settings)
        cache = Path(raw.get("cache_root") or ".ai_cache/knowledge")
        if cache.is_absolute() or ".." in cache.parts:
            raise KnowledgeError("knowledge.cache_root must be a repository-relative path without '..'")
        indexers, seen = [], set()
        for position, item in enumerate(raw.get("indexers") or []):
            indexer = Indexer(item, position)
            if indexer.id in seen:
                raise KnowledgeError(f"indexer id {indexer.id!r} is declared twice")
            seen.add(indexer.id)
            indexers.append(indexer)
        store = raw.get("store")
        if store is not None and not isinstance(store, dict):
            raise KnowledgeError("knowledge.store must be an object or null")
        return cls(repo, raw, indexers, cache, store, raw.get("publication", "open"))

    @property
    def base_refs(self):
        return list(self.raw.get("base_refs") or ["origin/develop", "develop", "origin/main", "main"])


def cache_root(repo, cfg):
    return Path(repo).resolve() / cfg.cache


def artifact_path(repo, cfg, key):
    """Where one artifact lives. A key is a digest, so it can never contain a path separator."""
    if not isinstance(key, str) or not KEY.match(key):
        raise KnowledgeError(f"Invalid artifact key {key!r}")
    return cache_root(repo, cfg) / "files" / key[:2] / key


def file_key(indexer, blob):
    material = "\0".join([indexer.kind, indexer.id, indexer.version, blob])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def scope_key(indexer, digest):
    material = "\0".join([indexer.kind, indexer.id, indexer.version, "scope", digest])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def resolve_base_ref(repo, cfg):
    for ref in cfg.base_refs:
        if run_git(repo, ["rev-parse", "--verify", "--quiet", ref], check=False).strip():
            return ref
    return None


def layer_commit(repo, cfg, layer):
    """The commit a layer's content is measured against."""
    if layer == "worktree":
        return run_git(repo, ["rev-parse", "HEAD"]).strip()
    if layer == "branch":
        return run_git(repo, ["rev-parse", "HEAD"]).strip()
    ref = resolve_base_ref(repo, cfg)
    if not ref:
        raise KnowledgeError(
            "Cannot build the base layer: none of the configured base_refs resolve "
            f"({', '.join(cfg.base_refs)}). Fetch the trunk or set knowledge.base_refs."
        )
    merge_base = run_git(repo, ["merge-base", ref, "HEAD"], check=False).strip()
    return merge_base or run_git(repo, ["rev-parse", ref]).strip()


def within(path, roots):
    candidate = Path(path)
    return any(candidate == root or root in candidate.parents for root in roots)


def scope_files(repo, indexer, layer, cfg):
    """Map every in-scope path to a content hash. Committed content uses git's blob hash; nothing is re-hashed."""
    repo = Path(repo).resolve()
    roots = []
    for path in indexer.paths:
        if path != "." and not (repo / path).exists():
            raise KnowledgeError(f"{indexer.id}: configured path {path!r} does not exist in {repo}")
        roots.append(Path(path))
    commit = layer_commit(repo, cfg, layer)
    arguments = ["ls-tree", "-r", "-z", "--format=%(objectname) %(path)", commit, "--", *indexer.paths]
    files = {}
    for record in run_git(repo, arguments).split("\0"):
        if not record.strip():
            continue
        blob, _, path = record.partition(" ")
        files[path] = blob
    if layer != "worktree":
        return files
    # The worktree layer adds uncommitted reality: edits, new files and deletions.
    status = run_git(repo, ["status", "--porcelain=1", "-z", "--untracked-files=all"]).split("\0")
    for record in status:
        if len(record) < 4:
            continue
        code, path = record[:2], record[3:]
        if not within(path, roots) and "." not in indexer.paths:
            continue
        absolute = repo / path
        if code.strip() == "D" or not absolute.exists():
            files.pop(path, None)
        elif absolute.is_file() and not absolute.is_symlink():
            files[path] = hashlib.sha256(absolute.read_bytes()).hexdigest()
    return files


def dirty_paths(repo, cfg):
    """Uncommitted paths, ignoring our own cache: CAS's artifacts are never repository dirt."""
    cache = cfg.cache.as_posix().rstrip("/") + "/"
    changed = []
    for record in run_git(repo, ["status", "--porcelain=1", "-z", "--untracked-files=normal"]).split("\0"):
        if len(record) < 4:
            continue
        path = record[3:]
        if path.startswith(cache) or (cfg.cache.as_posix() + "/").startswith(path):
            continue
        changed.append(path)
    return changed


def read_manifest(repo, cfg):
    path = cache_root(repo, cfg) / MANIFEST
    if not path.is_file():
        return {"schema_version": SCHEMA_VERSION, "artifacts": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise KnowledgeError(f"Damaged knowledge manifest at {path}: {error}") from error
    if not isinstance(data, dict) or not isinstance(data.get("artifacts"), dict):
        raise KnowledgeError(f"Damaged knowledge manifest at {path}")
    return data


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(json.dumps(value, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def layer_manifest_path(repo, cfg, indexer, layer):
    return cache_root(repo, cfg) / "layers" / indexer.id / f"{layer}.json"


def layer_manifest(repo, cfg, indexer, layer):
    path = layer_manifest_path(repo, cfg, indexer, layer)
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("paths", {}) if isinstance(data, dict) else {}


def substitute(command, values):
    """Expand placeholders into a real argument list. List placeholders expand to many arguments."""
    expanded = []
    for part in command:
        matched = next((name for name in LIST_PLACEHOLDERS if name == part), None)
        if matched:
            expanded.extend(values.get(matched, []))
            continue
        for name, value in values.items():
            if name in LIST_PLACEHOLDERS:
                continue
            part = part.replace(name, str(value))
        expanded.append(part)
    return expanded


def execute(command, cwd):
    result = subprocess.run(command, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        raise KnowledgeError(f"exit {result.returncode}: {detail[-1] if detail else 'no output'}")
    return result


def collect(staged, expected, destination_for):
    """Move each produced file into its keyed artifact directory. Output outside `staged` is ignored."""
    stored, missing = [], []
    staged = staged.resolve()
    for path, key in expected.items():
        produced = (staged / path).resolve()
        if not str(produced).startswith(str(staged) + os.sep) or not produced.is_file():
            missing.append(path)
            continue
        target = destination_for(key) / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(produced, target)
        stored.append(path)
    return sorted(stored), sorted(missing)


def build_file_layer(repo, cfg, indexer, layer, apply, manifest):
    files = scope_files(repo, indexer, layer, cfg)
    keys = {path: file_key(indexer, blob) for path, blob in files.items()}
    reused = sorted(path for path, key in keys.items() if artifact_path(repo, cfg, key).is_dir())
    pending = sorted(path for path in keys if path not in set(reused))
    row = {
        "indexer": indexer.id,
        "granularity": indexer.granularity,
        "layer": layer,
        "files": len(keys),
        "reused": reused,
        "to_index": pending,
        "indexed": [],
        "no_output": [],
    }
    if not apply:
        return row, None
    if pending:
        with tempfile.TemporaryDirectory(prefix="cbsetup_index_") as temp:
            out = Path(temp) / "out"
            out.mkdir()
            listing = Path(temp) / "files.txt"
            listing.write_text("\n".join(pending) + "\n", encoding="utf-8")
            command = substitute(
                indexer.build_command,
                {
                    "{out}": str(out),
                    "{files}": pending,
                    "{paths}": list(indexer.paths),
                    "{files_from}": str(listing),
                    "{repo}": str(repo),
                },
            )
            execute(command, repo)
            stored, missing = collect(
                out, {path: keys[path] for path in pending}, lambda key: artifact_path(repo, cfg, key)
            )
        row["indexed"], row["no_output"] = stored, missing
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        for path in stored:
            manifest["artifacts"][keys[path]] = {
                "indexer": indexer.id,
                "indexer_version": indexer.version,
                "kind": indexer.kind,
                "granularity": indexer.granularity,
                "path": path,
                "blob": files[path],
                "created": stamp,
            }
    covered = {path: keys[path] for path in set(reused) | set(row["indexed"])}
    # Keep the overlay sparse: a path whose content matches a lower layer is already resolvable there.
    lower = {}
    for beneath in BENEATH[layer]:
        lower.update(layer_manifest(repo, cfg, indexer, beneath))
    row["inherited"] = sorted(path for path in keys if lower.get(path) == keys[path])
    covered = {path: key for path, key in covered.items() if lower.get(path) != key}
    return row, {"commit": layer_commit(repo, cfg, layer), "indexer": indexer.id, "paths": covered}


def build_scope_layer(repo, cfg, indexer, layer, apply, manifest):
    files = scope_files(repo, indexer, layer, cfg)
    digest = hashlib.sha256("\0".join(f"{p}:{b}" for p, b in sorted(files.items())).encode("utf-8")).hexdigest()
    key = scope_key(indexer, digest)
    present = artifact_path(repo, cfg, key).is_dir()
    row = {
        "indexer": indexer.id,
        "granularity": indexer.granularity,
        "layer": layer,
        "files": len(files),
        "reused": [key] if present else [],
        "to_index": [] if present else [key],
        "indexed": [],
        "no_output": [],
    }
    state = {
        "commit": layer_commit(repo, cfg, layer),
        "indexer": indexer.id,
        "scope": key,
        "digest": digest,
        "files": files,
    }
    if not apply or present:
        return row, state
    with tempfile.TemporaryDirectory(prefix="cbsetup_index_") as temp:
        out = Path(temp) / "out"
        out.mkdir()
        command = substitute(
            indexer.build_command,
            {"{out}": str(out), "{paths}": list(indexer.paths), "{files}": sorted(files), "{repo}": str(repo)},
        )
        execute(command, repo)
        target = artifact_path(repo, cfg, key)
        target.mkdir(parents=True, exist_ok=True)
        shutil.copytree(out, target, dirs_exist_ok=True)
    row["indexed"] = [key]
    manifest["artifacts"][key] = {
        "indexer": indexer.id,
        "indexer_version": indexer.version,
        "kind": indexer.kind,
        "granularity": indexer.granularity,
        "path": None,
        "blob": digest,
        "scope_digest": digest,
        "created": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    return row, state


def require_checked_out(repo, cfg, layer):
    """Declared indexers read the working tree, so a layer may only be built where its commit is HEAD.

    Building the base layer from a dev checkout would key working-tree content by the trunk's blob hashes: files that
    moved on the branch would be described wrongly and the error would travel to every clone that pulled the artifact.
    Refuse instead. CI builds the trunk layer with the trunk commit checked out, where this holds.
    """
    commit = layer_commit(repo, cfg, layer)
    head = run_git(repo, ["rev-parse", "HEAD"]).strip()
    if commit != head:
        raise KnowledgeError(
            f"Cannot build the {layer} layer here: it describes commit {commit}, which is not checked out ({head} is). "
            "The declared indexers read the working tree, so building it now would record this branch's content "
            f"under that commit's file hashes. Check out {commit} (or let CI build the {layer} layer) and retry."
        )
    return commit


def build(repo, cfg, layer, apply=False):
    repo = Path(repo).resolve()
    if layer not in LAYERS:
        raise KnowledgeError(f"Unknown layer {layer!r}; use one of {', '.join(LAYERS)}")
    require_checked_out(repo, cfg, layer)  # Fail before any work: unresolvable trunk, or a commit that is not HEAD.
    manifest = read_manifest(repo, cfg)
    rows, failed, written = [], [], []
    for indexer in cfg.indexers:
        builder = build_scope_layer if indexer.granularity == "scope" else build_file_layer
        try:
            row, state = builder(repo, cfg, indexer, layer, apply, manifest)
        except KnowledgeError as error:
            failed.append({"indexer": indexer.id, "error": str(error)})
            continue
        rows.append(row)
        if apply and state is not None:
            written.append((indexer, state))
    if apply:
        for indexer, state in written:
            write_json(layer_manifest_path(repo, cfg, indexer, layer), state)
        if manifest["artifacts"]:
            write_json(cache_root(repo, cfg) / MANIFEST, manifest)
    return {"apply": apply, "layer": layer, "indexers": rows, "failed": failed}


def status(repo, cfg):
    repo = Path(repo).resolve()
    report = {"configured": bool(cfg.indexers), "cache_root": str(cfg.cache), "layers": {}}
    if not cfg.indexers:
        return report
    for layer in LAYERS:
        rows = []
        for indexer in cfg.indexers:
            try:
                files = scope_files(repo, indexer, layer, cfg)
            except KnowledgeError as error:
                rows.append({"indexer": indexer.id, "state": "unavailable", "error": str(error)})
                continue
            if indexer.granularity == "scope":
                recorded = (
                    json.loads(layer_manifest_path(repo, cfg, indexer, layer).read_text(encoding="utf-8"))["scope"]
                    if layer_manifest_path(repo, cfg, indexer, layer).is_file()
                    else None
                )
                digest = hashlib.sha256(
                    "\0".join(f"{p}:{b}" for p, b in sorted(files.items())).encode("utf-8")
                ).hexdigest()
                current = scope_key(indexer, digest)
                if recorded and artifact_path(repo, cfg, recorded).is_dir():
                    if recorded == current:
                        rows.append(
                            {"indexer": indexer.id, "state": "current", "artifact": recorded, "changed_since": []}
                        )
                    else:
                        recorded_state = json.loads(
                            layer_manifest_path(repo, cfg, indexer, layer).read_text(encoding="utf-8")
                        )
                        rows.append(
                            {
                                "indexer": indexer.id,
                                # A coarse index is a baseline, not a binary: name the files it no longer covers.
                                "state": "stale",
                                "artifact": recorded,
                                "changed_since": changed_since(repo, cfg, indexer, layer, recorded_state.get("files")),
                            }
                        )
                else:
                    rows.append({"indexer": indexer.id, "state": "missing", "artifact": None, "changed_since": []})
                continue
            recorded = layer_manifest(repo, cfg, indexer, layer)
            missing = sorted(
                path
                for path, blob in files.items()
                if recorded.get(path) != file_key(indexer, blob)
                or not artifact_path(repo, cfg, file_key(indexer, blob)).is_dir()
            )
            current = len(files) - len(missing)
            state = "current" if not missing else ("missing" if current == 0 else "partial")
            rows.append(
                {"indexer": indexer.id, "state": state, "files": len(files), "current": current, "missing": missing}
            )
        report["layers"][layer] = rows
    return report


def changed_since(repo, cfg, indexer, layer, known):
    """Which in-scope files differ from the content the stored scope artifact was built from."""
    files = scope_files(repo, indexer, layer, cfg)
    if not known:
        # Without a recorded file list the honest answer is "the whole scope is unverified".
        return sorted(files)
    moved = {path for path, blob in files.items() if known.get(path, blob) != blob}
    return sorted(moved | (set(files) ^ set(known)))


def resolve(repo, cfg, indexer):
    """Resolve every in-scope path through worktree → branch → base."""
    resolved = {}
    for layer in LAYERS:
        for path, key in layer_manifest(repo, cfg, indexer, layer).items():
            if not artifact_path(repo, cfg, key).is_dir():
                continue
            if resolved.get(path, {}).get("key") == key:
                continue  # Same content as a lower layer; keep the lower attribution.
            resolved[path] = {"key": key, "layer": layer, "artifact": str(artifact_path(repo, cfg, key))}
    return resolved


def ask_one(repo, cfg, indexer, extra):
    """Run one indexer's declared query_command over the artifacts that resolve for it."""
    resolved = resolve(repo, cfg, indexer)
    if not resolved:
        return None
    directories = sorted({entry["artifact"] for entry in resolved.values()})
    command = substitute(
        indexer.query_command,
        {"{artifacts}": " ".join(directories), "{artifact}": directories[0], "{repo}": str(repo)},
    )
    result = subprocess.run(
        [*command, *extra], cwd=str(repo), capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    return {
        "indexer": indexer.id,
        "kind": indexer.kind,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "artifacts": len(resolved),
    }


def query(repo, cfg, extra, indexer=None):
    """Ask every configured indexer, or one named with `indexer`.

    Asking only the first configured indexer made a mixed-language repository answer every question from one language
    and report nothing for the others --- a wrong answer rather than a missing feature, since the artifacts were
    present and current. Each indexer answers for its own paths, so all of them are consulted and every result is
    labelled with the indexer that produced it.
    """
    repo = Path(repo).resolve()
    if not cfg.indexers:
        raise KnowledgeError("No indexers configured; set knowledge.indexers first")
    available = [item.id for item in cfg.indexers]
    if indexer is not None:
        chosen = [item for item in cfg.indexers if item.id == indexer]
        if not chosen:
            raise KnowledgeError(
                f"No indexer {indexer!r} is configured; this repository declares {', '.join(available)}"
            )
    else:
        chosen = list(cfg.indexers)
    # `query -- term` keeps the separator in argparse.REMAINDER; the declared command must not have to strip it.
    extra = [argument for argument in extra if argument != "--"]
    results, skipped = [], []
    for item in chosen:
        if not item.query_command:
            skipped.append({"indexer": item.id, "reason": "no query_command configured"})
            continue
        answer = ask_one(repo, cfg, item, extra)
        if answer is None:
            skipped.append({"indexer": item.id, "reason": "no artifacts resolve for it yet"})
            continue
        results.append(answer)
    if not results:
        detail = "; ".join(f"{entry['indexer']}: {entry['reason']}" for entry in skipped)
        raise KnowledgeError(
            "No indexer could answer. Run `cbsetup knowledge build --layer base --apply` "
            f"(or `cbsetup knowledge pull`) first. {detail}"
        )
    # A failing indexer must not hide the others' answers, but its exit code still has to reach the caller.
    failures = [entry["returncode"] for entry in results if entry["returncode"]]
    return {
        "requested": indexer,
        "results": results,
        "skipped": skipped,
        "returncode": failures[0] if failures else 0,
        "stdout": "".join(entry["stdout"] for entry in results),
        "stderr": "".join(entry["stderr"] for entry in results),
    }


def transport_prefix(cfg, identity, key):
    template = (cfg.store or {}).get("prefix") or "{repository_id}/{key}"
    return template.replace("{repository_id}", quote(identity, safe="")).replace("{key}", key)


def repository_id(repo, cfg):
    """A shared store is addressed by repository identity, so it must be the same in every clone."""
    explicit = (cfg.raw or {}).get("repository_id")
    if explicit:
        return str(explicit)
    remote = run_git(repo, ["config", "--get", "remote.origin.url"], check=False).strip()
    if not remote:
        raise KnowledgeError(
            "Cannot address the shared store: this checkout has no origin remote, so its identity would differ "
            "from every other clone. Set knowledge.repository_id explicitly, or add an origin."
        )
    return "remote:" + hashlib.sha256(remote.encode("utf-8")).hexdigest()


def known_keys(repo, cfg):
    return sorted(read_manifest(repo, cfg)["artifacts"])


def push(repo, cfg, apply=False, include_owner_only=False):
    repo = Path(repo).resolve()
    if not cfg.store or not cfg.store.get("push_command"):
        raise KnowledgeError("No knowledge.store.push_command configured; nowhere to push to")
    if cfg.publication == "owner-only" and not include_owner_only:
        raise KnowledgeError(
            "This repository's publication policy is owner-only. An index of its code is as sensitive as the code, "
            "so publishing needs --include-owner-only."
        )
    keys = known_keys(repo, cfg)
    plan = {"apply": apply, "candidates": keys, "pushed": []}
    if not apply:
        return plan
    if dirty_paths(repo, cfg):
        raise KnowledgeError("Refusing to push from a dirty checkout: a published artifact must match a clean commit")
    identity = repository_id(repo, cfg)
    for key in keys:
        local = artifact_path(repo, cfg, key)
        if not local.is_dir():
            continue
        command = substitute(
            cfg.store["push_command"],
            {
                "{local}": str(local),
                "{key}": key,
                "{prefix}": transport_prefix(cfg, identity, key),
                "{repository_id}": identity,
                "{container}": cfg.store.get("container", ""),
            },
        )
        execute(command, repo)
        plan["pushed"].append(key)
    return plan


def pull(repo, cfg, apply=False):
    repo = Path(repo).resolve()
    if not cfg.store or not cfg.store.get("pull_command"):
        raise KnowledgeError("No knowledge.store.pull_command configured; nowhere to pull from")
    identity = repository_id(repo, cfg)
    wanted = {}
    for indexer in cfg.indexers:
        for layer in LAYERS:
            try:
                files = scope_files(repo, indexer, layer, cfg)
            except KnowledgeError:
                continue
            if indexer.granularity == "scope":
                continue
            for path, blob in files.items():
                key = file_key(indexer, blob)
                if not artifact_path(repo, cfg, key).is_dir():
                    wanted[key] = path
    plan = {"apply": apply, "wanted": sorted(wanted), "fetched": [], "unavailable": []}
    if not apply:
        return plan
    manifest = read_manifest(repo, cfg)
    for key, path in sorted(wanted.items()):
        local = artifact_path(repo, cfg, key)
        command = substitute(
            cfg.store["pull_command"],
            {
                "{local}": str(local),
                "{key}": key,
                "{prefix}": transport_prefix(cfg, identity, key),
                "{repository_id}": identity,
                "{container}": cfg.store.get("container", ""),
            },
        )
        try:
            execute(command, repo)
        except KnowledgeError as error:
            plan["unavailable"].append({"key": key, "path": path, "error": str(error)})
            shutil.rmtree(local, ignore_errors=True)
            continue
        if not local.is_dir():
            plan["unavailable"].append({"key": key, "path": path, "error": "store returned nothing"})
            continue
        plan["fetched"].append(key)
        manifest["artifacts"].setdefault(
            key,
            {
                "indexer": None,
                "indexer_version": None,
                "kind": None,
                "granularity": "file",
                "path": path,
                "blob": None,
                "created": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "source": "pull",
            },
        )
    if plan["fetched"]:
        write_json(cache_root(repo, cfg) / MANIFEST, manifest)
        # Rebuild layer manifests so a pulled artifact is immediately resolvable.
        for indexer in cfg.indexers:
            if indexer.granularity == "scope":
                continue
            for layer in LAYERS:
                try:
                    files = scope_files(repo, indexer, layer, cfg)
                except KnowledgeError:
                    continue
                covered = {
                    path: file_key(indexer, blob)
                    for path, blob in files.items()
                    if artifact_path(repo, cfg, file_key(indexer, blob)).is_dir()
                }
                if covered:
                    write_json(
                        layer_manifest_path(repo, cfg, indexer, layer),
                        {"commit": layer_commit(repo, cfg, layer), "indexer": indexer.id, "paths": covered},
                    )
    return plan


def load_config(repo, user_config=None):
    """Read knowledge settings through the shared resolver so the six-level hierarchy applies."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from settings import resolve as resolve_settings

    resolved = resolve_settings(Path(repo).resolve(), user_config)["settings"]
    return Config.from_settings(repo, resolved.get("knowledge", {}))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="cbsetup knowledge", description=__doc__.splitlines()[0])
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--user-config", type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="What each layer covers, and what is missing or stale")
    make = sub.add_parser("build", help="Run the declared indexers for a layer")
    make.add_argument("--layer", choices=LAYERS, default="worktree")
    make.add_argument("--apply", action="store_true")
    ask = sub.add_parser("query", help="Ask every declared indexer, or one named with --indexer")
    ask.add_argument("--indexer", help="Ask only this indexer id instead of all of them")
    ask.add_argument("rest", nargs=argparse.REMAINDER)
    send = sub.add_parser("push", help="Publish artifacts to the configured store")
    send.add_argument("--apply", action="store_true")
    send.add_argument("--include-owner-only", action="store_true")
    fetch = sub.add_parser("pull", help="Fetch artifacts this checkout lacks")
    fetch.add_argument("--apply", action="store_true", default=True)
    args = parser.parse_args(argv)
    try:
        cfg = load_config(args.repo, args.user_config)
        if args.command == "status":
            print(json.dumps(status(args.repo, cfg), indent=2))
        elif args.command == "build":
            print(json.dumps(build(args.repo, cfg, args.layer, apply=args.apply), indent=2))
        elif args.command == "query":
            result = query(args.repo, cfg, args.rest, indexer=args.indexer)
            # Label each block when more than one indexer answered, so a C++ hit is never read as a Python one.
            for entry in result["results"]:
                if len(result["results"]) > 1:
                    sys.stdout.write(f"== {entry['indexer']} ({entry['kind']}) ==\n")
                sys.stdout.write(entry["stdout"])
                sys.stderr.write(entry["stderr"])
            for entry in result["skipped"]:
                sys.stderr.write(f"skipped {entry['indexer']}: {entry['reason']}\n")
            return result["returncode"]
        elif args.command == "push":
            print(json.dumps(push(args.repo, cfg, args.apply, args.include_owner_only), indent=2))
        else:
            print(json.dumps(pull(args.repo, cfg, args.apply), indent=2))
        return 0
    except (KnowledgeError, OSError) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
