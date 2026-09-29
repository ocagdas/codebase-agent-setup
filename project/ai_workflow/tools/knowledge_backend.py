#!/usr/bin/env python3
"""Opt-in CGC/Sourcegraph retrieval. Graph results are navigation hints, not proof."""

from __future__ import annotations
import argparse
import asyncio
from contextlib import AsyncExitStack, redirect_stdout, contextmanager
import hashlib
from importlib.metadata import version
import tempfile
import zipfile
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import sysconfig
import shutil

if __package__:
    from .settings import SettingsError, cli_overrides, resolve
else:
    from settings import SettingsError, cli_overrides, resolve


def git(repo, *args):
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8", check=True
    )
    return result.stdout.strip()


def context(repo, user_config=None, overrides=None):
    repo = Path(git(repo, "rev-parse", "--show-toplevel")).resolve()
    config = resolve(repo, user_config, overrides)
    values = config["settings"]
    if values["cgc"]["executable"] == "cgc":
        companion = shutil.which("cgc", path=sysconfig.get_path("scripts"))
        if companion:
            values["cgc"]["executable"] = companion
    backend = values["knowledge"]["backend"]
    if values["knowledge"]["mode"] == "source":
        backend = "off"
    # Per-checkout by default: databases are mutable and contain absolute paths.
    data = Path(values["cgc"]["data_dir"] or repo / ".ai_cache/code_knowledge/cgc")
    return {
        "repo": str(repo),
        "repository_id": config["repository_id"],
        "revision": git(repo, "rev-parse", "HEAD"),
        "dirty": bool(git(repo, "status", "--porcelain", "--untracked-files=normal")),
        "backend": backend,
        "data_dir": str(data),
        "settings": values,
    }


def cgc_env(ctx):
    return {
        **os.environ,
        "KUZUDB_PATH": str(Path(ctx["data_dir"]) / "kuzudb"),
        "DEFAULT_DATABASE": "kuzudb",
        "CGC_ALLOWED_ROOTS": ctx["repo"],
        "CGC_RUNTIME_DB_TYPE": "kuzudb",
        "CGC_RUNTIME_DB_PATH": str(Path(ctx["data_dir"]) / "kuzudb"),
    }


def cgc_command(ctx, *args):
    return [
        ctx["settings"]["cgc"]["executable"],
        "--database",
        "kuzudb",
        "--db-path",
        str(Path(ctx["data_dir"]) / "kuzudb"),
        *args,
    ]


STATE_FILE = "codebase-agent-setup.json"
LEGACY_STATE_FILE = "repo-pilot.json"  # read-only fallback from before the rename


def state(ctx):
    path = Path(ctx["data_dir"]) / STATE_FILE
    if not path.exists():
        path = Path(ctx["data_dir"]) / LEGACY_STATE_FILE
    if not path.exists():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or any(
        not isinstance(value.get(key), str) for key in ("repo", "repository_id", "revision")
    ):
        raise SettingsError(f"{path}: invalid CGC state; expected repo, repository_id and revision strings.")
    return value


def status(ctx):
    record = state(ctx) if ctx["backend"] == "cgc" else None
    current = bool(
        record
        and record.get("revision") == ctx["revision"]
        and record.get("repo") == ctx["repo"]
        and record.get("repository_id") == ctx["repository_id"]
        and (Path(ctx["data_dir"]) / "kuzudb").exists()
        and not ctx["dirty"]
    )
    return {k: ctx[k] for k in ("backend", "repo", "repository_id", "revision", "dirty")} | {
        "storage": ctx["data_dir"]
        if ctx["backend"] == "cgc"
        else (ctx["settings"]["sourcegraph"]["url"] if ctx["backend"] == "sourcegraph" else None),
        "local_snapshot_current": current,
        "remote_availability": "unchecked" if ctx["backend"] == "sourcegraph" else None,
        "branch_graph_composition": False,
        "source_fallback_required": ctx["backend"] in ("off", "sourcegraph")
        or ctx["dirty"]
        or (ctx["backend"] == "cgc" and not current),
    }


def check_cgc_version(ctx):
    proc = subprocess.run(
        [ctx["settings"]["cgc"]["executable"], "--version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        timeout=15,
    )
    output = (proc.stdout + proc.stderr).strip()
    if output != "CodeGraphContext 0.6.13":
        raise SettingsError("CGC adapter requires codegraphcontext==0.6.13.")


def index(ctx):
    if ctx["backend"] != "cgc":
        raise SettingsError("Local indexing requires backend cgc; Sourcegraph indexing runs on its server.")
    if ctx["dirty"]:
        raise SettingsError("Index a clean checkout so the graph has an unambiguous source revision.")
    check_cgc_version(ctx)
    data = Path(ctx["data_dir"])
    data.mkdir(parents=True, exist_ok=True)
    marker = data / STATE_FILE
    # Invalidate first: failed or interrupted rebuilding must not leave a current marker.
    marker.unlink(missing_ok=True)
    (data / LEGACY_STATE_FILE).unlink(missing_ok=True)
    subprocess.run(
        cgc_command(ctx, "index", ctx["repo"], "--force"),
        cwd=ctx["repo"],
        env=cgc_env(ctx),
        check=True,
        stdout=sys.stderr,
        timeout=3600,
    )
    if git(ctx["repo"], "rev-parse", "HEAD") != ctx["revision"] or git(
        ctx["repo"], "status", "--porcelain", "--untracked-files=normal"
    ):
        raise SettingsError(
            "Checkout changed during indexing (CGC may have created .cgcignore); review and commit exclusions, then retry."
        )
    marker.write_text(
        json.dumps({k: ctx[k] for k in ("repo", "repository_id", "revision")}, indent=2) + "\n", encoding="utf-8"
    )
    return status(ctx)


def bundle(ctx, operation, filename):
    """Repo-scoped bundles with explicit clone rebasing and a provenance sidecar."""
    if ctx["backend"] != "cgc" or ctx["dirty"]:
        raise SettingsError("Bundle operations require CGC and a clean checkout.")
    if not ctx["repository_id"]:
        raise SettingsError("Configure a shared repository_id or canonical origin before sharing bundles.")
    if version("codegraphcontext") != "0.6.13":
        raise SettingsError("Bundle adapter requires codegraphcontext==0.6.13 in this Python environment.")
    from codegraphcontext.core.database_kuzu import KuzuDBManager
    from codegraphcontext.core.cgc_bundle import CGCBundle

    path = Path(filename).resolve()
    sidecar = Path(str(path) + ".json")
    data = Path(ctx["data_dir"])
    if operation == "export":
        if not status(ctx)["local_snapshot_current"]:
            raise SettingsError("Index the current clean revision before exporting.")
        if path.exists() or sidecar.exists():
            raise SettingsError("Bundle destination already exists; choose a new filename.")
        manager = KuzuDBManager(db_path=str(data / "kuzudb"))
        try:
            with redirect_stdout(sys.stderr):
                ok, _ = CGCBundle(manager).export_to_bundle(
                    path, repo_path=Path(state(ctx).get("graph_root", ctx["repo"]))
                )
            if not ok:
                raise SettingsError("CGC bundle export failed.")
        finally:
            manager.close_driver()
        if git(ctx["repo"], "rev-parse", "HEAD") != ctx["revision"] or git(
            ctx["repo"], "status", "--porcelain", "--untracked-files=normal"
        ):
            raise SettingsError("Checkout changed during export; no provenance sidecar written.")
        with path.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        record = {
            "schema_version": "1.0",
            "backend": "cgc",
            "cgc_version": "0.6.13",
            "repository_id": ctx["repository_id"],
            "revision": ctx["revision"],
            "sha256": digest,
        }
        with sidecar.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(record, indent=2) + "\n")
        return {"bundle": str(path), "manifest": str(sidecar), **record}
    record = json.loads(sidecar.read_text(encoding="utf-8"))
    for key, expected in [
        ("schema_version", "1.0"),
        ("backend", "cgc"),
        ("cgc_version", "0.6.13"),
        ("repository_id", ctx["repository_id"]),
        ("revision", ctx["revision"]),
    ]:
        if record.get(key) != expected:
            raise SettingsError(f"Bundle {key} does not match this checkout.")
    with path.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    if record.get("sha256") != digest:
        raise SettingsError("Bundle checksum mismatch.")
    if data.exists():
        raise SettingsError("Import requires a fresh data_dir; existing databases are preserved.")
    data.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".cgc-import-", dir=data.parent) as temporary:
        staging = Path(temporary)
        from codegraphcontext.core.cgc_bundle import _default_bundle_install_root

        with zipfile.ZipFile(path) as archive:
            metadata = json.loads(archive.read("metadata.json"))
        graph_root = _default_bundle_install_root(metadata, data / "source")
        manager = KuzuDBManager(db_path=str(staging / "kuzudb"))
        try:
            with redirect_stdout(sys.stderr):
                ok, _ = CGCBundle(manager).import_from_bundle(path, destination_root=data / "source")
            if not ok:
                raise SettingsError("CGC bundle import failed.")
        finally:
            manager.close_driver()
        if git(ctx["repo"], "rev-parse", "HEAD") != ctx["revision"] or git(
            ctx["repo"], "status", "--porcelain", "--untracked-files=normal"
        ):
            raise SettingsError("Checkout changed during import.")
        (staging / STATE_FILE).write_text(
            json.dumps({k: ctx[k] for k in ("repo", "repository_id", "revision")} | {"graph_root": graph_root}) + "\n",
            encoding="utf-8",
        )
        staging.rename(data)
    return status(ctx)


def query_request(ctx, query, limit):
    if ctx["backend"] == "cgc":
        if not status(ctx)["local_snapshot_current"]:
            raise SettingsError("CGC snapshot missing or stale; index a clean checkout or read source files.")
        return "find_code", {"query": query, "repo_path": state(ctx).get("graph_root", ctx["repo"])}
    sg = ctx["settings"]["sourcegraph"]
    if not sg["url"] or not sg["repository"]:
        raise SettingsError("Set sourcegraph.url and sourcegraph.repository before querying.")
    # Literal pattern prevents user search text from broadening repository/revision scope.
    repo_filter = json.dumps("^" + re.escape(sg["repository"]) + "$")
    return "keyword_search", {
        "query": f"repo:{repo_filter} rev:{ctx['revision']} count:{limit} patternType:literal {json.dumps(query)}"
    }


async def query_backend(ctx, query, limit):
    tool, arguments = query_request(ctx, query, limit)
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        from mcp.client.streamable_http import streamable_http_client
        import httpx
    except ImportError as exc:
        raise SettingsError("Install optional knowledge dependencies: pip install mcp==1.30.0") from exc
    async with AsyncExitStack() as stack:
        if ctx["backend"] == "cgc":
            streams = await stack.enter_async_context(
                stdio_client(
                    StdioServerParameters(
                        command=ctx["settings"]["cgc"]["executable"],
                        args=cgc_command(ctx, "mcp", "start")[1:],
                        env=cgc_env(ctx),
                        cwd=ctx["repo"],
                    )
                )
            )
        else:
            sg = ctx["settings"]["sourcegraph"]
            token = os.environ.get(sg["token_env"])
            if not token:
                raise SettingsError(f"Set the access-token environment variable {sg['token_env']}.")
            client = await stack.enter_async_context(
                httpx.AsyncClient(headers={"Authorization": "token " + token}, follow_redirects=False, timeout=60)
            )
            streams = await stack.enter_async_context(
                streamable_http_client(sg["url"].rstrip("/") + "/.api/mcp", http_client=client)
            )
        session = await stack.enter_async_context(ClientSession(streams[0], streams[1]))
        await session.initialize()
        result = await session.call_tool(tool, arguments)
        if result.isError:
            raise SettingsError("Backend reported a tool error; check availability and use source fallback.")
        texts = [block.text for block in result.content if block.type == "text"]
        if ctx["backend"] == "cgc":
            payload = json.loads(texts[0]) if texts else {}
            if payload.get("success") is not True:
                raise SettingsError("CGC could not complete the query.")
            matches = payload.get("results", {}).get("ranked_results", [])
            return map_matches(ctx, matches, limit)
        return {"text": "\n".join(texts)}


def map_matches(ctx, matches, limit):
    graph_root = Path(state(ctx).get("graph_root", ctx["repo"]))
    mapped = []
    for item in matches[:limit]:
        entry = {key: item[key] for key in ("name", "path", "line_number", "source") if key in item}
        if "path" in entry:
            relative = Path(entry["path"]).resolve().relative_to(graph_root.resolve())
            target = Path(ctx["repo"]) / relative
            if not target.is_file():
                raise SettingsError("Graph result does not map to a current source file.")
            entry["path"] = str(target)
        mapped.append(entry)
    return {"matches": mapped, "more_matches": len(matches) > limit}


@contextmanager
def database_lock(ctx):
    """Serialise wrapper access; direct upstream commands must be stopped separately."""
    if ctx["backend"] != "cgc":
        yield
        return
    data = Path(ctx["data_dir"])
    data.parent.mkdir(parents=True, exist_ok=True)
    lock = data.parent / (data.name + ".lock")
    try:
        handle = lock.open("x", encoding="utf-8")
    except FileExistsError as exc:
        raise SettingsError(
            "CGC database busy; after a crash remove its .lock only once all users have stopped."
        ) from exc
    try:
        with handle:
            handle.write(str(os.getpid()))
        yield
    finally:
        lock.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["status", "index", "query", "export", "import"])
    parser.add_argument("--repo", default=".")
    parser.add_argument("--user-config")
    parser.add_argument("--backend", choices=["off", "cgc", "sourcegraph", "sg"])
    parser.add_argument("--set", action="append", default=[])
    parser.add_argument("--query")
    parser.add_argument("--bundle", help="CGC bundle path; export/import also use a .json sidecar")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--max-chars", type=int, default=12000)
    args = parser.parse_args(argv)
    try:
        overrides = cli_overrides(args.set)
        if args.backend:
            overrides.setdefault("knowledge", {})["backend"] = "sourcegraph" if args.backend == "sg" else args.backend
        ctx = context(args.repo, args.user_config, overrides)
        if not 1 <= args.limit <= 100 or not 256 <= args.max_chars <= 100000:
            raise SettingsError("limit must be 1..100 and max-chars 256..100000")
        if args.command == "status":
            result = status(ctx)
        elif ctx["backend"] == "off":
            if ctx["settings"]["knowledge"]["mode"] == "index":
                raise SettingsError("Index-only mode requires an enabled backend.")
            result = status(ctx) | {"reason": "backend_disabled", "results": []}
        elif args.command == "index":
            with database_lock(ctx):
                result = index(ctx)
        elif args.command in ("export", "import"):
            if not args.bundle:
                raise SettingsError("--bundle is required")
            with database_lock(ctx):
                result = bundle(ctx, args.command, args.bundle)
        else:
            if not args.query or not args.query.strip():
                raise SettingsError("--query is required")
            if ctx["dirty"]:
                raise SettingsError(
                    "Checkout has local changes; read source files until a matching clean revision is available."
                )
            with database_lock(ctx):
                try:
                    response = asyncio.run(asyncio.wait_for(query_backend(ctx, args.query, args.limit), timeout=90))
                except SettingsError:
                    raise
                except Exception as exc:
                    # Remote exceptions can contain headers, tokens and response bodies.
                    raise SettingsError(
                        "Backend query failed (" + type(exc).__name__ + "); check installation, endpoint and access."
                    ) from None
            if git(ctx["repo"], "rev-parse", "HEAD") != ctx["revision"] or git(
                ctx["repo"], "status", "--porcelain", "--untracked-files=normal"
            ):
                raise SettingsError("Checkout changed during query; retry from current source.")
            rendered = json.dumps(response, ensure_ascii=False)
            result = status(ctx) | {
                "content": response if len(rendered) <= args.max_chars else rendered[: args.max_chars],
                "truncated": len(rendered) > args.max_chars,
                "source_fallback_required": False,
                "remote_availability": "query_succeeded" if ctx["backend"] == "sourcegraph" else None,
            }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (SettingsError, OSError, ValueError, subprocess.SubprocessError, TimeoutError) as exc:
        print(json.dumps({"error": str(exc), "source_fallback_required": True}), file=sys.stderr)
        return 2
    except Exception as exc:
        # Keep exception text private, but distinguish internal operation errors from transport failures.
        print(
            json.dumps(
                {
                    "error": f"Backend {args.command} failed unexpectedly ({type(exc).__name__}); report this operation and exception type.",
                    "source_fallback_required": True,
                }
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
