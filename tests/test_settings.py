import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "project/ai_workflow/tools"))
from settings import SettingsError, bootstrap_config, canonical_remote, configure, resolve


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
                [sys.executable, str(ROOT / "configure.py"), command, "--repo", str(self.repo)],
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
                sys.executable,
                str(ROOT / "configure.py"),
                "inspect",
                "--repo",
                str(self.repo),
                "--user-config",
                str(self.user),
            ],
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

    def test_setup_uses_shared_resolver_and_explicit_cli_wins(self):
        self.write(self.user, {"tooling": {"mode": "conda", "conda_name": "configured"}})
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "setup_tooling.py"),
                "--user-config",
                str(self.user),
                "--conda-name",
                "explicit",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        plan = json.loads(result.stdout)
        self.assertEqual(plan["mode"], "conda")
        self.assertIn("explicit", plan["commands"][0])
        self.assertFalse(plan["apply"])


if __name__ == "__main__":
    unittest.main()
