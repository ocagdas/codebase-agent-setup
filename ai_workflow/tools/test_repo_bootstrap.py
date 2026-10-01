#!/usr/bin/env python3

from __future__ import annotations

import sys

import json
from pathlib import Path
import subprocess
import tempfile
import unittest


TOOLS = Path(__file__).resolve().parent
SCRIPT = TOOLS / "repo_bootstrap.py"
CONFIG = TOOLS.parent / "bootstrap.json"


class RepositoryBootstrapTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.repo = Path(self.temporary.name)
        self.git("init", "-b", "main")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "Bootstrap Test")
        (self.repo / "src").mkdir()
        (self.repo / "src/main.c").write_text("int main(void) { return 0; }\n", encoding="utf-8")
        (self.repo / "CMakeLists.txt").write_text("project(example C)\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-m", "initial")
        self.git("checkout", "-b", "develop/feature")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(self.repo), *args],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.strip()

    def command(
        self,
        name: str,
        *extra: str,
        expect_success: bool = True,
        config: Path | None = None,
    ) -> dict:
        process = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                name,
                "--repo",
                str(self.repo),
                "--config",
                str(config or CONFIG),
                "--base-ref",
                "main",
                *extra,
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if expect_success and process.returncode != 0:
            self.fail(process.stderr)
        source = process.stdout if process.returncode == 0 else process.stderr
        return json.loads(source)

    def test_project_config_used_for_all_commands_without_explicit_path(self):
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        config["semantic_index"]["mode"] = "disabled"
        config["state_directory"] = ".ai_cache/custom"
        project_config = self.repo / "ai_workflow/bootstrap.json"
        project_config.parent.mkdir()
        project_config.write_text(json.dumps(config), encoding="utf-8")

        def invoke(command):
            result = subprocess.run(
                [sys.executable, str(SCRIPT), command, "--repo", str(self.repo), "--base-ref", "main"],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)

        prepared = invoke("prepare")
        self.assertEqual(prepared["semantic_index"]["mode"], "disabled")
        self.satisfy_request(prepared)
        invoke("complete")
        self.assertTrue(invoke("status")["knowledge_fresh"])
        self.assertTrue((self.repo / ".ai_cache/custom").is_dir())
        self.assertFalse((self.repo / ".ai_cache/code_knowledge").exists())
        explicit = self.command("prepare")  # helper supplies the distribution config explicitly
        self.assertEqual(explicit["semantic_index"]["mode"], "auto")

    def test_missing_project_config_falls_back_but_malformed_config_fails(self):
        import repo_bootstrap

        args = repo_bootstrap.parser().parse_args(["status", "--repo", str(self.repo)])
        self.assertEqual(repo_bootstrap.effective_config(args, self.repo)["semantic_index"]["mode"], "auto")
        path = self.repo / "ai_workflow/bootstrap.json"
        path.parent.mkdir()
        path.write_text("{", encoding="utf-8")
        with self.assertRaisesRegex(repo_bootstrap.BootstrapError, "bootstrap.json: invalid JSON"):
            repo_bootstrap.effective_config(args, self.repo)

    def test_personal_semantic_override_and_invocation_precedence(self) -> None:
        local = self.repo / "ai_workflow/settings.local.json"
        local.parent.mkdir()
        local.write_text(
            json.dumps({"schema_version": "1.0", "settings": {"knowledge": {"mode": "source"}}}), encoding="utf-8"
        )
        self.assertEqual(self.command("prepare")["semantic_index"]["mode"], "disabled")
        error = self.command("prepare", "--knowledge-mode", "index", expect_success=False)
        self.assertIn("Required semantic index is unavailable", error["message"])

    def test_personal_config_change_invalidates_completed_and_pending_analysis(self) -> None:
        # Ignore local preferences as installed projects do, so source identity
        # stays unchanged and only the effective configuration causes invalidation.
        exclude = self.repo / ".git/info/exclude"
        with exclude.open("a", encoding="utf-8") as handle:
            handle.write("\n/ai_workflow/settings.local.json\n")
        initial = self.command("prepare")
        self.satisfy_request(initial)
        self.command("complete")
        local = self.repo / "ai_workflow/settings.local.json"
        local.parent.mkdir(exist_ok=True)
        local.write_text(
            json.dumps({"schema_version": "1.0", "settings": {"knowledge": {"mode": "source"}}}), encoding="utf-8"
        )
        self.assertFalse(self.command("status")["knowledge_fresh"])
        pending = self.command("prepare")
        self.satisfy_request(pending)
        local.write_text(
            json.dumps({"schema_version": "1.0", "settings": {"knowledge": {"mode": "auto"}}}), encoding="utf-8"
        )
        error = self.command("complete", expect_success=False)
        self.assertIn("Configuration changed after preparation", error["message"])

    def custom_config(self, **semantic_changes: object) -> Path:
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        config["semantic_index"].update(semantic_changes)
        path = self.repo / "bootstrap.test.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        return path

    def semantic_manifest(self, layer: str, source_commit: str) -> dict:
        return {
            "schema_version": "1.0",
            "layer": layer,
            "repository_id": "test-repository",
            "source_commit": source_commit,
            "base_index_commit": None,
            "branch": "develop/feature",
            "generator": {
                "name": "test-indexer",
                "version": "1.0",
                "parser_version": "1.0",
            },
            "compile_context_hash": "compile-context",
            "embedding_configuration_hash": None,
            "inputs_hash": "inputs",
            "created_at": "2026-01-01T00:00:00Z",
            "trust": {"publisher": "test", "trusted": True},
            "statistics": {},
            "validation": {"status": "pass", "failures": []},
            "artefact_checksum": "checksum",
        }

    def satisfy_request(self, request: dict) -> None:
        for relative in request["required_analysis_outputs"]:
            path = self.repo / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# Analysis\n\nVerified test output.\n", encoding="utf-8")

    def test_candidate_integrity_and_request_paths_rejected_before_promotion(self):
        for mutation in ("revision", "contents", "missing_digest", "path"):
            with self.subTest(mutation=mutation):
                request = self.command("prepare", "--force-full")
                self.satisfy_request(request)
                candidate = self.repo / request["candidate_file_index"]
                pending = self.repo / request["state_directory"] / "analysis_request.json"
                value = json.loads(candidate.read_text(encoding="utf-8"))
                if mutation == "revision":
                    value["source_commit"] = "0" * 40
                elif mutation == "contents":
                    value["files"] = []
                elif mutation == "missing_digest":
                    modified = dict(request)
                    del modified["candidate_digest"]
                    pending.write_text(json.dumps(modified), encoding="utf-8")
                else:
                    modified = dict(request, candidate_file_index="../other.json")
                    pending.write_text(json.dumps(modified), encoding="utf-8")
                candidate.write_text(json.dumps(value), encoding="utf-8")
                self.command("complete", expect_success=False)
                self.assertFalse((self.repo / request["state_directory"] / "state.json").exists())

    def test_layout_collisions_rejected_without_cache_writes(self):
        for section, key, value in (
            ("analysis", "file_index_file", "state.json"),
            ("analysis", "pending_request_file", "candidate_file_index.json"),
            ("analysis", "repository_analysis_file", "deltas/report.md"),
            ("analysis", "file_index_file", "STATE.JSON"),
            ("layer_storage", "branch_overlay_directory", "overlays"),
            ("layer_storage", "base_directory", "matching_branches/subdir"),
            ("semantic_index", "manifest_file", "file_overlay.json"),
        ):
            with self.subTest(key=key, value=value):
                config = json.loads(CONFIG.read_text(encoding="utf-8"))
                config[section][key] = value
                path = self.repo / "config.json"
                path.write_text(json.dumps(config), encoding="utf-8")
                self.command("prepare", config=path, expect_success=False)
                self.assertFalse((self.repo / ".ai_cache").exists())

    def test_saved_index_corruption_is_not_reported_fresh_and_can_be_rebuilt(self):
        request = self.command("prepare")
        self.satisfy_request(request)
        self.command("complete")
        index = self.repo / request["state_directory"] / "file_index.json"
        data = json.loads(index.read_text(encoding="utf-8"))
        data["files"] = []
        index.write_text(json.dumps(data), encoding="utf-8")
        self.assertFalse(self.command("status")["knowledge_fresh"])
        self.command("prepare", expect_success=False)
        refreshed = self.command("prepare", "--force-full")
        self.assertEqual(refreshed["action_required"], "full_analysis")

    def test_index_path_change_invalidates_before_integrity_check(self):
        first = self.command("prepare")
        self.satisfy_request(first)
        self.command("complete")
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        config["analysis"]["file_index_file"] = "new_index.json"
        path = self.repo / "changed-config.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        request = self.command("prepare", config=path)
        self.assertEqual(request["action_required"], "full_analysis")
        self.assertIn("configuration_changed", request["reasons"])
        self.satisfy_request(request)
        self.command("complete", config=path)
        self.assertTrue(self.command("status", config=path)["knowledge_fresh"])
        self.assertEqual(self.command("prepare", config=path)["action_required"], "none")

    def test_configuration_change_rebuilds_without_reading_obsolete_index(self):
        first = self.command("prepare")
        self.satisfy_request(first)
        self.command("complete")
        old = self.repo / first["state_directory"] / "file_index.json"
        old.write_text("corrupt old data", encoding="utf-8")
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        config["source_selection"]["include_globs"].append("**/*.custom")
        path = self.repo / "changed-config.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        request = self.command("prepare", config=path)
        self.assertEqual(request["action_required"], "full_analysis")
        self.assertIn("configuration_changed", request["reasons"])

    def test_sha256_repository_full_incremental_and_unchanged_flow(self):
        # Keep the same fixture root but construct an independent SHA-256 Git repo.
        self.repo = self.repo / "sha256"
        self.repo.mkdir()
        self.git("init", "--object-format=sha256", "-b", "main")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "Bootstrap Test")
        source = self.repo / "example.py"
        source.write_text("x = 1\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-m", "initial")
        request = self.command("prepare")
        self.assertEqual(len(request["source_commit"]), 64)
        self.satisfy_request(request)
        self.command("complete")
        self.assertTrue(self.command("status")["knowledge_fresh"])
        self.assertEqual(self.command("prepare")["action_required"], "none")
        source.write_text("x = 2\n", encoding="utf-8")
        request = self.command("prepare")
        self.assertEqual(request["action_required"], "incremental_analysis")
        self.satisfy_request(request)
        self.command("complete")
        self.assertTrue(self.command("status")["knowledge_fresh"])

    def test_full_incremental_and_unchanged_flow(self) -> None:
        initial = self.command("prepare")
        self.assertEqual(initial["action_required"], "full_analysis")
        self.assertTrue(initial["branch_matches_shared_policy"])
        self.assertFalse(initial["shared_publish_allowed"])
        self.satisfy_request(initial)
        self.assertEqual(self.command("complete")["status"], "completed")
        self.assertTrue(self.command("status")["knowledge_fresh"])
        self.assertEqual(self.command("prepare")["action_required"], "none")

        source = self.repo / "src/main.c"
        source.write_text("int main(void) { return 1; }\n", encoding="utf-8")
        incremental = self.command("prepare")
        self.assertEqual(incremental["action_required"], "incremental_analysis")
        self.assertEqual([item["path"] for item in incremental["changed_paths"]], ["src/main.c"])
        self.satisfy_request(incremental)
        self.command("complete")
        self.assertEqual(self.command("prepare")["action_required"], "none")

    def test_header_dependency_and_global_invalidation(self) -> None:
        initial = self.command("prepare")
        self.satisfy_request(initial)
        self.command("complete")

        header = self.repo / "src/api.h"
        header.write_text("int api(void);\n", encoding="utf-8")
        request = self.command("prepare")
        self.assertEqual(request["action_required"], "incremental_analysis")
        self.assertTrue(request["dependency_closure_required"])
        self.satisfy_request(request)
        self.command("complete")

        cmake = self.repo / "CMakeLists.txt"
        cmake.write_text("project(example C)\nadd_executable(example src/main.c)\n", encoding="utf-8")
        request = self.command("prepare")
        self.assertEqual(request["action_required"], "full_analysis")
        self.assertIn("global_invalidation", request["reasons"])

    def test_branch_state_is_separate(self) -> None:
        initial = self.command("prepare")
        self.satisfy_request(initial)
        self.command("complete")
        first_state = initial["state_directory"]

        self.git("checkout", "-b", "develop/other")
        other = self.command("prepare")
        self.assertEqual(other["action_required"], "full_analysis")
        self.assertNotEqual(first_state, other["state_directory"])

    def test_completion_rejects_repository_drift(self) -> None:
        request = self.command("prepare")
        self.satisfy_request(request)
        (self.repo / "src/main.c").write_text("int main(void) { return 2; }\n", encoding="utf-8")
        error = self.command("complete", expect_success=False)
        self.assertEqual(error["status"], "error")
        self.assertIn("changed after analysis preparation", error["message"])

    def test_commit_of_already_analysed_content_needs_no_second_analysis(self) -> None:
        initial = self.command("prepare")
        self.satisfy_request(initial)
        self.command("complete")

        source = self.repo / "src/main.c"
        source.write_text("int main(void) { return 7; }\n", encoding="utf-8")
        incremental = self.command("prepare")
        self.satisfy_request(incremental)
        self.command("complete")
        self.git("add", "src/main.c")
        self.git("commit", "-m", "change result")

        refresh = self.command("prepare")
        self.assertEqual(refresh["action_required"], "none")
        self.assertEqual(refresh["reason"], "relevant_content_unchanged")

    def test_branch_delta_records_committed_change(self) -> None:
        source = self.repo / "src/main.c"
        source.write_text("int main(void) { return 9; }\n", encoding="utf-8")
        self.git("add", "src/main.c")
        self.git("commit", "-m", "branch change")
        request = self.command("prepare")
        delta = json.loads((self.repo / request["branch_delta_data"]).read_text(encoding="utf-8"))
        self.assertEqual([item["path"] for item in delta["changes"]], ["src/main.c"])

    def test_layers_are_separate_and_ordered(self) -> None:
        source = self.repo / "src/main.c"
        source.write_text("int main(void) { return 4; }\n", encoding="utf-8")
        self.git("add", "src/main.c")
        self.git("commit", "-m", "branch layer")
        source.write_text("int main(void) { return 5; }\n", encoding="utf-8")

        request = self.command("prepare")
        layers = request["layers"]
        self.assertEqual(
            layers["query_precedence"],
            ["worktree_overlay", "branch_overlay", "base"],
        )
        self.assertNotEqual(layers["base"], layers["branch_overlay"])
        self.assertNotEqual(layers["branch_overlay"], layers["worktree_overlay"])
        branch_overlay = json.loads(
            (self.repo / layers["branch_overlay"] / "file_overlay.json").read_text(encoding="utf-8")
        )
        worktree_overlay = json.loads(
            (self.repo / layers["worktree_overlay"] / "file_overlay.json").read_text(encoding="utf-8")
        )
        self.assertEqual(branch_overlay["records"][0]["source_revision"], self.git("rev-parse", "HEAD"))
        self.assertEqual(worktree_overlay["records"][0]["source_revision"], "worktree")

    def test_semantic_index_auto_falls_back_when_absent(self) -> None:
        request = self.command("prepare")
        semantic = request["semantic_index"]
        self.assertEqual(semantic["mode"], "auto")
        self.assertFalse(semantic["use_for_queries"])
        self.assertTrue(semantic["fallback_to_direct_source"])

    def test_semantic_index_can_be_disabled(self) -> None:
        config = self.custom_config(mode="disabled")
        request = self.command("prepare", config=config)
        self.assertEqual(request["semantic_index"]["reason"], "semantic_index_disabled")
        self.assertFalse(request["semantic_index"]["use_for_queries"])

    def test_compatible_semantic_base_is_used_and_updated(self) -> None:
        config = self.custom_config(
            mode="auto",
            query_command="semantic-query {layers} {query}",
            branch_overlay_update_command="semantic-update-overlay {compile_database} {output}",
            create_when_missing=True,
        )
        (self.repo / "compile_commands.json").write_text("[]\n", encoding="utf-8")
        first = self.command("prepare", config=config)
        base_manifest = self.repo / first["semantic_index"]["manifest_paths"]["base"]
        base_manifest.parent.mkdir(parents=True, exist_ok=True)
        base_manifest.write_text(
            json.dumps(
                self.semantic_manifest(
                    "base",
                    first["layers"]["base_source_commit"],
                )
            ),
            encoding="utf-8",
        )
        second = self.command("prepare", "--force-full", config=config)
        semantic = second["semantic_index"]
        self.assertTrue(semantic["use_for_queries"])
        self.assertTrue(semantic["update_enabled"])
        self.assertIn("base", semantic["existing_layers"])

    def test_required_semantic_index_blocks_when_unavailable(self) -> None:
        config = self.custom_config(mode="required")
        error = self.command("prepare", expect_success=False, config=config)
        self.assertEqual(error["status"], "error")
        self.assertIn("Required semantic index is unavailable", error["message"])

    def test_matching_and_other_branches_use_different_roots(self) -> None:
        matching = self.command("prepare")
        self.assertIn("matching_branches", matching["state_directory"])
        self.git("checkout", "-b", "feature/local")
        local = self.command("prepare")
        self.assertIn("local_branches", local["state_directory"])

    def test_branch_deletion_creates_overlay_tombstone(self) -> None:
        self.git("rm", "src/main.c")
        self.git("commit", "-m", "remove source")
        request = self.command("prepare")
        overlay_path = self.repo / request["layers"]["branch_overlay"] / "file_overlay.json"
        overlay = json.loads(overlay_path.read_text(encoding="utf-8"))
        self.assertIn(
            {"operation": "delete", "path": "src/main.c"},
            overlay["records"],
        )

    def test_incompatible_semantic_manifest_falls_back(self) -> None:
        config = self.custom_config(
            mode="auto",
            query_command="semantic-query {layers} {query}",
        )
        first = self.command("prepare", config=config)
        base_manifest = self.repo / first["semantic_index"]["manifest_paths"]["base"]
        base_manifest.parent.mkdir(parents=True, exist_ok=True)
        base_manifest.write_text(
            json.dumps(self.semantic_manifest("base", "wrong")),
            encoding="utf-8",
        )
        second = self.command("prepare", "--force-full", config=config)
        semantic = second["semantic_index"]
        self.assertFalse(semantic["use_for_queries"])
        self.assertEqual(semantic["incompatible_layers"]["base"], "source_commit_mismatch")
        self.assertTrue(semantic["fallback_to_direct_source"])

    def test_malformed_semantic_manifest_uses_source_fallback(self):
        first = self.command("prepare")
        manifest = self.repo / first["semantic_index"]["manifest_paths"]["base"]
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text("[]", encoding="utf-8")
        second = self.command("prepare")
        self.assertTrue(second["semantic_index"]["fallback_to_direct_source"])
        self.assertIn("invalid_manifest", second["semantic_index"]["incompatible_layers"]["base"])

    def test_python_source_is_included(self) -> None:
        (self.repo / "pipeline.py").write_text("x = 1\n")
        request = self.command("prepare")
        inventory = json.loads((self.repo / request["candidate_file_index"]).read_text())
        self.assertIn("pipeline.py", [item["path"] for item in inventory["files"]])

    def test_reverted_dirty_source_is_reanalysed(self) -> None:
        path = self.repo / "src/main.c"
        path.write_text("int main(void) { return 3; }\n")
        first = self.command("prepare")
        self.satisfy_request(first)
        self.command("complete")
        self.git("restore", "src/main.c")
        second = self.command("prepare")
        self.assertEqual(second["action_required"], "incremental_analysis")
        self.assertIn("src/main.c", [item["path"] for item in second["changed_paths"]])

    def test_removed_untracked_file_is_reanalysed(self) -> None:
        path = self.repo / "extra.py"
        path.write_text("x = 1\n")
        first = self.command("prepare")
        self.satisfy_request(first)
        self.command("complete")
        path.unlink()
        second = self.command("prepare")
        self.assertIn({"path": "extra.py", "status": "D"}, second["changed_paths"])

    def test_config_change_rejects_pending_completion(self) -> None:
        config = self.custom_config(mode="auto")
        first = self.command("prepare", config=config)
        self.satisfy_request(first)
        self.custom_config(mode="disabled")
        error = self.command("complete", config=config, expect_success=False)
        self.assertIn("Configuration changed", error["message"])

    def test_required_mode_does_not_accept_update_declaration(self) -> None:
        config = self.custom_config(mode="required", create_when_missing=True, branch_overlay_update_command="update")
        (self.repo / "compile_commands.json").write_text("[]")
        error = self.command("prepare", config=config, expect_success=False)
        self.assertEqual(error["status"], "error")

    def test_partial_index_requires_source_fallback(self) -> None:
        config = self.custom_config(query_command="query")
        (self.repo / "src/main.c").write_text("int main(void) { return 2; }\n")
        first = self.command("prepare", config=config)
        path = self.repo / first["semantic_index"]["manifest_paths"]["base"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.semantic_manifest("base", first["layers"]["base_source_commit"])))
        result = self.command("prepare", config=config)["semantic_index"]
        self.assertTrue(result["use_for_queries"])
        self.assertFalse(result["current_view_complete"])
        self.assertTrue(result["fallback_to_direct_source"])
        self.assertIn("worktree_overlay", result["missing_current_layers"])


if __name__ == "__main__":
    unittest.main()
