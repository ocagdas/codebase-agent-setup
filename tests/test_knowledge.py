"""Backend policy and protocol tests; no production service or graph dependencies required."""

import asyncio
from contextlib import redirect_stdout, redirect_stderr
import io
import hashlib
from types import SimpleNamespace
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "project/ai_workflow/tools"))
import knowledge_backend as kb
from settings import SettingsError, validate_settings


class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "repo"
        self.repo.mkdir()
        self.user = Path(self.temp.name) / "user.json"
        (self.repo / ".gitignore").write_text(".ai_cache/\nai_workflow/settings.local.json\n", encoding="utf-8")
        (self.repo / "sample.py").write_text("def hello(): return 1\n", encoding="utf-8")
        for args in [
            ("init", "-q"),
            ("config", "user.email", "test@example.invalid"),
            ("config", "user.name", "Test"),
            ("add", "."),
            ("commit", "-qm", "initial"),
            ("remote", "add", "origin", "https://example.invalid/team/repo.git"),
        ]:
            subprocess.run(["git", "-C", str(self.repo), *args], check=True, capture_output=True)

    def ctx(self, backend="cgc"):
        return kb.context(self.repo, self.user, {"knowledge": {"backend": backend}})

    def invoke(self, *args):
        output, error = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            code = kb.main(["--repo", str(self.repo), "--user-config", str(self.user), *args])
        return code, output.getvalue(), error.getvalue()

    def mark_current(self, ctx):
        data = Path(ctx["data_dir"])
        data.mkdir(parents=True)
        (data / "kuzudb").touch()
        (data / "codebase-agent-setup.json").write_text(
            json.dumps({key: ctx[key] for key in ("repo", "revision", "repository_id")}), encoding="utf-8"
        )

    def test_off_never_launches_backend_or_writes_cache(self):
        with (
            patch.object(kb, "query_backend", side_effect=AssertionError("launched")),
            patch.object(kb, "index", side_effect=AssertionError("indexed")),
        ):
            for command in ("query", "index"):
                code, output, _ = self.invoke(command)
                self.assertEqual(code, 0)
                self.assertEqual(json.loads(output)["reason"], "backend_disabled")
        self.assertFalse((self.repo / ".ai_cache").exists())

    def test_config_selection_cli_override_and_source_policy(self):
        self.user.write_text(
            json.dumps({"schema_version": "1.0", "settings": {"knowledge": {"backend": "cgc"}}}), encoding="utf-8"
        )
        code, output, _ = self.invoke("status", "--backend", "sg")
        self.assertEqual(json.loads(output)["backend"], "sourcegraph")
        code, output, _ = self.invoke("query", "--set", 'knowledge.mode="source"')
        self.assertEqual(json.loads(output)["backend"], "off")
        code, _, error = self.invoke("query", "--backend", "off", "--set", 'knowledge.mode="index"')
        self.assertEqual(code, 2)

    def test_invalid_backend_and_unsafe_credentials_rejected(self):
        for values in (
            {"knowledge": {"backend": []}},
            {"knowledge": {"backend": "unknown"}},
            {"sourcegraph": {"url": "http://example.com"}},
            {"sourcegraph": {"url": "https://user:secret@example.com"}},
            {"sourcegraph": {"url": "https://example.com/?token=secret"}},
            {"sourcegraph": {"token_env": "BAD-NAME"}},
        ):
            with self.assertRaises(SettingsError):
                validate_settings(values)

    def test_database_path_overrides_inherited_cgc_context(self):
        ctx = self.ctx()
        with patch.dict(os.environ, {"CGC_RUNTIME_DB_PATH": "/wrong/db", "CGC_RUNTIME_DB_TYPE": "neo4j"}):
            env = kb.cgc_env(ctx)
        expected = str(Path(ctx["data_dir"]) / "kuzudb")
        self.assertEqual(env["CGC_RUNTIME_DB_PATH"], expected)
        self.assertEqual(env["CGC_RUNTIME_DB_TYPE"], "kuzudb")
        self.assertIn(expected, kb.cgc_command(ctx, "index", ctx["repo"]))

    def test_missing_dirty_and_other_clone_snapshots_rejected(self):
        ctx = self.ctx()
        with self.assertRaises(SettingsError):
            kb.query_request(ctx, "hello", 20)
        self.mark_current(ctx)
        self.assertTrue(kb.status(ctx)["local_snapshot_current"])
        (self.repo / "sample.py").write_text("def hello(): return 2\n", encoding="utf-8")
        with self.assertRaises(SettingsError):
            kb.query_request(self.ctx(), "hello", 20)
        ctx["repo"] = "/different/clone"
        self.assertFalse(kb.status(ctx)["local_snapshot_current"])

    def test_sourcegraph_search_is_revision_scoped_and_literal(self):
        ctx = self.ctx("sourcegraph")
        ctx["settings"]["sourcegraph"].update(url="https://sg.example", repository="github.com/team/repo")
        name, args = kb.query_request(ctx, "hello OR repo:other", 7)
        self.assertEqual(name, "keyword_search")
        self.assertIn("rev:" + ctx["revision"], args["query"])
        self.assertIn("count:7", args["query"])
        self.assertTrue(args["query"].endswith('"hello OR repo:other"'))
        self.assertIn("patternType:literal", args["query"])

    def test_lock_prevents_concurrent_mutation(self):
        ctx = self.ctx()
        with kb.database_lock(ctx):
            with self.assertRaises(SettingsError):
                with kb.database_lock(ctx):
                    pass
        self.assertFalse(Path(ctx["data_dir"] + ".lock").exists())

    def test_version_probe_supports_stderr_and_rejects_other_versions(self):
        ctx = self.ctx()
        with patch.object(
            kb.subprocess,
            "run",
            return_value=subprocess.CompletedProcess([], 0, stdout="", stderr="CodeGraphContext 0.6.13\n"),
        ):
            kb.check_cgc_version(ctx)
        with patch.object(
            kb.subprocess,
            "run",
            return_value=subprocess.CompletedProcess([], 0, stdout="CodeGraphContext 0.5.0", stderr=""),
        ):
            with self.assertRaises(SettingsError):
                kb.check_cgc_version(ctx)

    def test_failed_index_invalidates_marker(self):
        ctx = self.ctx()
        self.mark_current(ctx)
        with (
            patch.object(kb, "check_cgc_version"),
            patch.object(kb.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "cgc")),
        ):
            with self.assertRaises(subprocess.CalledProcessError):
                kb.index(ctx)
        self.assertIsNone(kb.state(ctx))

    def test_imported_paths_map_to_clone_and_reject_missing_source(self):
        ctx = self.ctx()
        self.mark_current(ctx)
        marker = Path(ctx["data_dir"]) / "codebase-agent-setup.json"
        marker.write_text(
            json.dumps(
                json.loads(marker.read_text(encoding="utf-8")) | {"graph_root": "/virtual/bundle/producer-name"}
            ),
            encoding="utf-8",
        )
        result = kb.map_matches(ctx, [{"name": "hello", "path": "/virtual/bundle/producer-name/sample.py"}], 1)
        self.assertEqual(result["matches"][0]["path"], str((self.repo / "sample.py").resolve()))
        with self.assertRaises(SettingsError):
            kb.map_matches(ctx, [{"path": "/virtual/bundle/producer-name/missing.py"}], 1)
        with self.assertRaises(ValueError):
            kb.map_matches(ctx, [{"path": "/another-repository/sample.py"}], 1)

    def test_bundle_rejects_wrong_identity_revision_checksum_and_existing_data(self):
        ctx = self.ctx()
        artifact = Path(self.temp.name) / "fixture.cgc"
        artifact.write_bytes(b"fixture")
        sidecar = Path(str(artifact) + ".json")
        metadata = {
            "schema_version": "1.0",
            "backend": "cgc",
            "cgc_version": "0.6.13",
            "repository_id": ctx["repository_id"],
            "revision": ctx["revision"],
            "sha256": hashlib.sha256(b"fixture").hexdigest(),
        }
        manager = MagicMock()
        modules = {
            "codegraphcontext.core.database_kuzu": SimpleNamespace(KuzuDBManager=manager),
            "codegraphcontext.core.cgc_bundle": SimpleNamespace(CGCBundle=MagicMock()),
        }
        with patch.dict(sys.modules, modules), patch.object(kb, "version", return_value="0.6.13"):
            for field in ("repository_id", "revision", "sha256", "cgc_version"):
                sidecar.write_text(json.dumps(metadata | {field: "wrong"}), encoding="utf-8")
                with self.assertRaises(SettingsError):
                    kb.bundle(ctx, "import", str(artifact))
                self.assertFalse(Path(ctx["data_dir"]).exists())
            sidecar.write_text(json.dumps(metadata), encoding="utf-8")
            self.mark_current(ctx)
            with self.assertRaises(SettingsError):
                kb.bundle(ctx, "import", str(artifact))
            self.assertTrue(kb.status(ctx)["local_snapshot_current"])
        manager.assert_not_called()

    def test_import_cleans_staging_on_metadata_constructor_and_close_failures(self):
        ctx = self.ctx()
        artifact = Path(self.temp.name) / "broken.cgc"
        for failure in ("metadata", "constructor", "close"):
            with self.subTest(failure=failure):
                with zipfile.ZipFile(artifact, "w") as archive:
                    archive.writestr("metadata.json", "{" if failure == "metadata" else "{}")
                metadata = {
                    "schema_version": "1.0",
                    "backend": "cgc",
                    "cgc_version": "0.6.13",
                    "repository_id": ctx["repository_id"],
                    "revision": ctx["revision"],
                    "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                }
                Path(str(artifact) + ".json").write_text(json.dumps(metadata), encoding="utf-8")
                manager = MagicMock()
                if failure == "constructor":
                    manager.side_effect = RuntimeError("constructor failed")
                if failure == "close":
                    manager.return_value.close_driver.side_effect = RuntimeError("close failed")
                adapter = MagicMock()
                adapter.return_value.import_from_bundle.return_value = (True, "ok")
                modules = {
                    "codegraphcontext.core.database_kuzu": SimpleNamespace(KuzuDBManager=manager),
                    "codegraphcontext.core.cgc_bundle": SimpleNamespace(
                        CGCBundle=adapter, _default_bundle_install_root=lambda *args: "virtual/root"
                    ),
                }
                with patch.dict(sys.modules, modules), patch.object(kb, "version", return_value="0.6.13"):
                    with self.assertRaises((ValueError, RuntimeError)):
                        kb.bundle(ctx, "import", str(artifact))
                self.assertFalse(Path(ctx["data_dir"]).exists())
                self.assertEqual(list(Path(ctx["data_dir"]).parent.glob(".cgc-import-*")), [])

    def test_transport_failure_does_not_echo_credentials(self):
        async def fail(*args):
            raise RuntimeError("token super-secret")

        with patch.object(kb, "query_backend", fail):
            code, _, error = self.invoke("query", "--backend", "sg", "--query", "hello")
        self.assertEqual(code, 2)
        self.assertNotIn("super-secret", error)

    def test_output_budget_and_checkout_race(self):
        async def response(*args):
            return {"text": "a" * 1000}

        with patch.object(kb, "query_backend", response):
            code, output, _ = self.invoke("query", "--backend", "sg", "--query", "hello", "--max-chars", "256")
        self.assertEqual(code, 0)
        result = json.loads(output)
        self.assertTrue(result["truncated"])
        self.assertEqual(len(result["content"]), 256)

        async def race(*args):
            (self.repo / "sample.py").write_text("changed", encoding="utf-8")
            return {"text": "stale"}

        with patch.object(kb, "query_backend", race):
            code, _, error = self.invoke("query", "--backend", "sg", "--query", "hello")
        self.assertEqual(code, 2)
        self.assertIn("changed during query", error)


class SourcegraphTransportTests(unittest.TestCase):
    setUp = KnowledgeTests.setUp
    ctx = KnowledgeTests.ctx

    def test_mcp_handshake_and_authenticated_tool_call(self):
        try:
            import httpx

            __import__("mcp")
        except ImportError:
            self.skipTest("Optional MCP dependencies unavailable")
        ctx = self.ctx("sourcegraph")
        ctx["settings"]["sourcegraph"].update(url="https://sg.example", repository="github.com/team/repo")
        calls = []

        def handle(request):
            self.assertEqual(request.headers["Authorization"], "token fixture-token")
            self.assertEqual(request.url.path, "/.api/mcp")
            if request.method == "DELETE":
                return httpx.Response(200)
            if request.method == "GET":
                return httpx.Response(405)
            body = json.loads(request.content)
            calls.append(body)
            if "id" not in body:
                return httpx.Response(202)
            if body["method"] == "initialize":
                result = {
                    "protocolVersion": body["params"]["protocolVersion"],
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "fixture", "version": "1"},
                }
            elif body["method"] == "tools/list":
                result = {"tools": [{"name": "keyword_search", "inputSchema": {"type": "object"}}]}
            else:
                self.assertEqual(body["method"], "tools/call")
                result = {"content": [{"type": "text", "text": "sample.py:1 hello"}]}
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": result})

        original = httpx.AsyncClient

        def factory(**kwargs):
            self.assertFalse(kwargs["follow_redirects"])
            return original(transport=httpx.MockTransport(handle), **kwargs)

        with (
            patch.dict(os.environ, {"SOURCEGRAPH_TOKEN": "fixture-token"}),
            patch.object(httpx, "AsyncClient", factory),
        ):
            result = asyncio.run(kb.query_backend(ctx, "hello", 5))
        self.assertEqual(result, {"text": "sample.py:1 hello"})
        call = next(item for item in calls if item["method"] == "tools/call")
        self.assertEqual(call["params"]["name"], "keyword_search")
        self.assertIn(ctx["revision"], call["params"]["arguments"]["query"])


if __name__ == "__main__":
    unittest.main()
