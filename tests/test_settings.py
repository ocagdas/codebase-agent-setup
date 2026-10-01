import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "project/ai_workflow/tools"))

# The single command surface; the per-verb launcher scripts were removed.
CLI = [sys.executable, "-m", "codebase_agent_setup", "configure"]
CLI_ENV = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
from settings import (
    SettingsError,
    bootstrap_config,
    canonical_remote,
    configure,
    handover_location,
    resolve,
    validate_settings,
)


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.user = self.root / "user/config.json"
        self.shared = self.repo / "ai_workflow/settings.json"
        self.local = self.repo / "ai_workflow/settings.local.json"

    def write(self, path, settings=None, **extra):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"schema_version": "1.0", "settings": settings or {}, **extra}), encoding="utf-8")

    def resolve(self, overrides=None):
        return resolve(self.repo, self.user, overrides)

    def test_precedence_at_every_boundary(self):
        self.assertEqual(self.resolve()["settings"]["tooling"]["conda_name"], "codebase-agent-setup")
        self.write(
            self.user,
            {"tooling": {"conda_name": "user"}},
            projects={"team:repo": {"tooling": {"conda_name": "personal"}}},
        )
        self.assertEqual(self.resolve()["settings"]["tooling"]["conda_name"], "user")
        self.write(self.shared, {"tooling": {"conda_name": "team"}})
        self.assertEqual(self.resolve()["settings"]["tooling"]["conda_name"], "team")
        self.write(self.shared, {"tooling": {"conda_name": "team"}}, repository_id="team:repo")
        self.assertEqual(self.resolve()["settings"]["tooling"]["conda_name"], "personal")
        self.write(self.local, {"tooling": {"conda_name": "checkout"}})
        self.assertEqual(self.resolve()["settings"]["tooling"]["conda_name"], "checkout")
        result = self.resolve({"tooling": {"conda_name": "cli"}})
        self.assertEqual(result["settings"]["tooling"]["conda_name"], "cli")
        self.assertEqual(result["origins"]["tooling.conda_name"], "invocation")

    def test_lists_replace_and_null_resets(self):
        self.write(self.user, {"agent": {"integrations": ["codex", "copilot"]}, "tooling": {"mode": "conda"}})
        self.write(self.local, {"agent": {"integrations": ["cursor-agent"]}, "tooling": {"mode": None}})
        result = self.resolve()["settings"]
        self.assertEqual(result["agent"]["integrations"], ["cursor-agent"])
        self.assertEqual(result["tooling"]["mode"], "venv")

    def test_relative_paths_follow_declaring_file(self):
        self.write(self.user, {"tooling": {"env_dir": "envs/tools"}})
        self.assertEqual(
            self.resolve()["settings"]["tooling"]["env_dir"], str((self.user.parent / "envs/tools").resolve())
        )
        self.write(self.local, {"tooling": {"env_dir": "../local-env"}})
        self.assertEqual(self.resolve()["settings"]["tooling"]["env_dir"], str((self.repo / "local-env").resolve()))

    def test_clone_identity_and_checkout_isolation(self):
        other = self.root / "clone"
        self.write(other / "ai_workflow/settings.json", repository_id="team:repo")
        self.write(self.shared, repository_id="team:repo")
        self.write(self.user, projects={"team:repo": {"knowledge": {"mode": "source"}}})
        self.assertEqual(self.resolve()["fingerprint"], resolve(other, self.user)["fingerprint"])
        self.write(self.local, {"knowledge": {"mode": "index"}})
        self.assertEqual(self.resolve()["settings"]["knowledge"]["mode"], "index")
        self.assertEqual(resolve(other, self.user)["settings"]["knowledge"]["mode"], "source")

    def test_remote_identity_removes_credentials_and_protocol(self):
        self.assertEqual(
            canonical_remote("git@example.com:Team/repo.git"),
            canonical_remote("https://user:secret@example.com/Team/repo.git"),
        )
        self.assertIsNone(canonical_remote("/tmp/project"))

    def test_malformed_and_unsupported_policy_rejected(self):
        for value in (
            {"quality_gates": {"required": []}},
            {"knowledge": {"mode": True}},
            {"tooling": {"conda_name": "a;echo"}},
        ):
            self.write(self.local, value)
            with self.assertRaises(SettingsError):
                self.resolve()
        self.local.write_text("{", encoding="utf-8")
        with self.assertRaises(SettingsError):
            self.resolve()

    def test_legacy_settings_remain_shared_defaults(self):
        config = {"semantic_index": {"mode": "required"}, "branch_selection": {"base_ref_candidates": ["origin/rc"]}}
        self.write(self.user, {"knowledge": {"mode": "source"}})
        self.assertEqual(bootstrap_config(config, self.repo, self.user)["semantic_index"], config["semantic_index"])
        self.write(self.local, {"knowledge": {"mode": "source", "base_refs": ["origin/release"]}})
        effective = bootstrap_config(config, self.repo, self.user)
        self.assertEqual(effective["semantic_index"]["mode"], "disabled")
        self.assertEqual(effective["branch_selection"]["base_ref_candidates"], ["origin/release"])
        self.assertEqual(config["semantic_index"]["mode"], "required")

    def test_configuration_preview_preserves_files_and_apply_is_conservative(self):
        self.shared.parent.mkdir()
        legacy = self.shared.parent / "bootstrap.json"
        legacy.write_text('{"authored": true}\n', encoding="utf-8")
        ignore = self.repo / ".gitignore"
        ignore.write_text("important/\n", encoding="utf-8")
        configure(self.repo)
        self.assertFalse(self.shared.exists())
        self.assertEqual(ignore.read_text(encoding="utf-8"), "important/\n")
        configure(self.repo, True)
        self.assertEqual(legacy.read_text(encoding="utf-8"), '{"authored": true}\n')
        self.assertEqual(json.loads(self.shared.read_text(encoding="utf-8"))["settings"], {})
        self.assertIn("important/\n/ai_workflow/settings.local.json\n", ignore.read_text(encoding="utf-8"))
        before = self.shared.read_bytes()
        with self.assertRaises(SettingsError):
            configure(self.repo, True)
        self.assertEqual(self.shared.read_bytes(), before)

    def test_configure_cli_and_deprecated_alias_preview_without_writes(self):
        for command in ("configure", "migrate"):
            result = subprocess.run(
                [*CLI, command, "--repo", str(self.repo)],
                env=CLI_ENV,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )
            self.assertFalse(json.loads(result.stdout)["apply"])
            self.assertFalse(self.shared.exists())
            self.assertEqual("deprecated" in result.stderr, command == "migrate")

    def test_inspect_has_no_writes_and_fingerprint_ignores_provenance(self):
        before = list(self.repo.rglob("*"))
        result = subprocess.run(
            [
                *CLI,
                "inspect",
                "--repo",
                str(self.repo),
                "--user-config",
                str(self.user),
            ],
            env=CLI_ENV,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        self.assertIsNone(json.loads(result.stdout)["repository_id"])
        self.assertEqual(list(self.repo.rglob("*")), before)
        initial = self.resolve()["fingerprint"]
        self.write(self.local, {"knowledge": {"mode": "auto"}})
        self.assertEqual(initial, self.resolve()["fingerprint"])


class HandoverLocationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        (self.repo / "ai_workflow").mkdir(parents=True)
        self.user = self.root / "user/config.json"
        self.user.parent.mkdir()
        (self.repo / "ai_workflow/settings.json").write_text(
            json.dumps({"schema_version": "1.0", "repository_id": "team:repo"}), encoding="utf-8"
        )

    def write_user(self, handover):
        self.user.write_text(
            json.dumps({"schema_version": "1.0", "projects": {"team:repo": {"handover": handover}}}), encoding="utf-8"
        )

    def test_default_is_in_repo_handover_not_the_maintainer_handoff(self):
        # HANDOFF.md is commonly an authored maintainer guide; session state must not overwrite it.
        result = handover_location(self.repo, self.user)
        self.assertEqual(result["path"], str((self.repo / "HANDOVER.md").resolve()))
        self.assertEqual(result["origin"], "default")
        self.assertFalse(result["configured"])
        self.assertFalse(result["exists"])

    def test_user_project_absolute_path(self):
        target = self.root / "docs/repo/HANDOVER.md"
        target.parent.mkdir(parents=True)
        target.write_text("x", encoding="utf-8")
        self.write_user({"path": str(target)})
        result = handover_location(self.repo, self.user)
        self.assertEqual(result["path"], str(target.resolve()))
        self.assertTrue(result["exists"])
        self.assertTrue(result["configured"])
        self.assertIn("#projects/team:repo", result["origin"])

    def test_relative_path_resolves_against_declaring_file(self):
        self.write_user({"path": "../docs/repo/HANDOVER.md"})
        result = handover_location(self.repo, self.user)
        self.assertEqual(result["path"], str((self.root / "docs/repo/HANDOVER.md").resolve()))

    def test_local_checkout_override_wins(self):
        self.write_user({"path": "/elsewhere/HANDOVER.md"})
        (self.repo / "ai_workflow/settings.local.json").write_text(
            json.dumps({"schema_version": "1.0", "settings": {"handover": {"path": "../NOTES.md"}}}), encoding="utf-8"
        )
        result = handover_location(self.repo, self.user)
        self.assertEqual(result["path"], str((self.repo / "NOTES.md").resolve()))

    def test_empty_path_rejected(self):
        with self.assertRaises(SettingsError):
            validate_settings({"handover": {"path": " "}})

    def test_cli_prints_location(self):
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "project/ai_workflow/tools/settings.py"),
                "handover",
                "--repo",
                str(self.repo),
                "--user-config",
                str(self.user),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["origin"], "default")


if __name__ == "__main__":
    unittest.main()
