import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from codebase_agent_setup import toolchains

sys.path.insert(0, str(ROOT / "project/ai_workflow/tools"))
from settings import resolve


class ToolchainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.selection = {
            **toolchains.resolve_selection(),
            "requested_ref": "v1.0.3",
            "upstream_commit": "6906bc582230bb752776e23287ee97990c1af743",
            "specify_cli_version": "1.0.3",
        }

    def record(self, data=None):
        path = self.root / "record.json"
        toolchains.write_record(path, data or self.selection)
        return path

    def test_default_selection_is_offline_and_pin_exact(self):
        with patch.object(toolchains, "run", side_effect=AssertionError("Unexpected network")):
            result = toolchains.resolve_selection()
        self.assertEqual(result["upstream_commit"], toolchains.lock()["upstream_commit"])
        self.assertFalse(toolchains.is_override(result))

    def test_import_is_offline_and_rejects_conflicting_selection(self):
        record = self.record()
        with patch.object(toolchains, "run", side_effect=AssertionError("Unexpected network")):
            self.assertEqual(toolchains.resolve_selection(record_file=record), self.selection)
            with self.assertRaises(toolchains.ToolchainError):
                toolchains.resolve_selection("v1.0.2", record)

    def test_record_rejects_arbitrary_repositories_and_bad_commits(self):
        for key, value in [
            ("upstream_repository", "https://example.com/untrusted"),
            ("upstream_commit", "--upload-pack=evil"),
            ("schema_version", "99"),
        ]:
            record = self.record({**self.selection, key: value})
            with self.assertRaises(toolchains.ToolchainError):
                toolchains.resolve_selection(record_file=record)

    def test_tag_resolution_prefers_peeled_commit_and_reads_version(self):
        commit = self.selection["upstream_commit"]
        responses = [
            f"{'a' * 40}\trefs/tags/v1.0.3\n{commit}\trefs/tags/v1.0.3^{{}}",
            "",
            "",
            commit,
            '[project]\nversion = "1.0.3"\n',
        ]
        with patch.object(toolchains, "run", side_effect=responses) as run:
            result = toolchains.resolve_selection("v1.0.3")
        self.assertEqual(result["upstream_commit"], commit)
        self.assertIn(commit, run.call_args_list[2].args[0])

    def test_invalid_ref_is_rejected_before_network(self):
        with patch.object(toolchains, "run", side_effect=AssertionError("Unexpected network")):
            for ref in ["main", "abc123", "--help", "v1.0.3;echo", "https://example.com/repo"]:
                with self.assertRaises(toolchains.ToolchainError):
                    toolchains.resolve_selection(ref)

    def test_export_refuses_authored_file(self):
        path = self.root / "README.md"
        path.write_text("Keep this documentation", encoding="utf-8")
        with self.assertRaises(toolchains.ToolchainError):
            toolchains.check_export_path(path)
        self.assertEqual(path.read_text(encoding="utf-8"), "Keep this documentation")

    def test_same_version_with_wrong_source_commit_is_rejected(self):
        executable = self.root / "specify"
        executable.touch()
        (self.root / ("python.exe" if os.name == "nt" else "python")).touch()
        metadata = {
            "version": "1.0.3",
            "source": {"url": toolchains.OFFICIAL + ".git", "vcs_info": {"commit_id": "a" * 40}},
        }
        with patch.object(toolchains, "run", side_effect=["CLI Version 1.0.3", json.dumps(metadata)]):
            with self.assertRaises(toolchains.ToolchainError):
                toolchains.probe_cli(str(executable), self.selection)

    def test_version_paths_preserve_custom_base_and_are_distinct(self):
        settings = resolve(user_config=self.root / "missing")["settings"]
        settings["tooling"]["env_dir"] = str(self.root / "tools with spaces")
        default = toolchains.environment_path(settings, toolchains.resolve_selection())
        alternate = toolchains.environment_path(settings, self.selection)
        self.assertEqual(default, self.root / "tools with spaces")
        self.assertNotEqual(default, alternate)
        self.assertIn(self.selection["upstream_commit"], str(alternate))
        self.assertNotEqual(toolchains.conda_environment(settings, self.selection), settings["tooling"]["conda_name"])
        self.assertFalse(alternate.exists())

    def test_settings_hierarchy_accepts_release_and_null_reset(self):
        repo = self.root / "repo"
        local = repo / "ai_workflow/settings.local.json"
        local.parent.mkdir(parents=True)
        local.write_text(
            json.dumps({"schema_version": "1.0", "settings": {"speckit": {"ref": "v1.0.3"}}}), encoding="utf-8"
        )
        self.assertEqual(resolve(repo, self.root / "missing")["settings"]["speckit"]["ref"], "v1.0.3")
        self.assertIsNone(
            resolve(repo, self.root / "missing", {"speckit": {"ref": None}})["settings"]["speckit"]["ref"]
        )

    def test_discovery_uses_matching_active_cli_and_skips_wrong_candidates(self):
        settings = resolve(user_config=self.root / "missing")["settings"]
        settings["tooling"]["env_dir"] = str(self.root / "absent-env")
        scripts = self.root / "active"
        scripts.mkdir()
        companion = scripts / ("specify.exe" if os.name == "nt" else "specify")
        companion.touch()
        fallback = self.root / "fallback"
        fallback.touch()
        with (
            patch.object(toolchains.sysconfig, "get_path", return_value=str(scripts)),
            patch.object(toolchains.shutil, "which", return_value=str(fallback)),
            patch.object(toolchains, "probe_cli", return_value="verified_commit") as probe,
        ):
            self.assertEqual(toolchains.discover_cli(settings, self.selection), str(companion))
            probe.assert_called_once_with(str(companion), self.selection)
        with (
            patch.object(toolchains.sysconfig, "get_path", return_value=str(scripts)),
            patch.object(toolchains.shutil, "which", return_value=str(fallback)),
            patch.object(
                toolchains, "probe_cli", side_effect=[toolchains.ToolchainError("wrong commit"), "verified_commit"]
            ),
        ):
            self.assertEqual(toolchains.discover_cli(settings, self.selection), str(fallback))
        with (
            patch.object(toolchains.sysconfig, "get_path", return_value=str(scripts)),
            patch.object(toolchains.shutil, "which", return_value=str(fallback)),
            patch.object(toolchains, "probe_cli", side_effect=toolchains.ToolchainError("wrong commit")),
        ):
            with self.assertRaises(toolchains.ToolchainError):
                toolchains.discover_cli(settings, self.selection)

    def test_discovery_checks_path_after_mismatched_companion(self):
        settings = resolve(user_config=self.root / "missing")["settings"]
        settings["tooling"]["env_dir"] = str(self.root / "absent")
        wrong = self.root / "wrong"
        wrong.touch()
        right = self.root / "right"
        right.touch()

        def which(name, path=None):
            return str(wrong if path == "first" else right)

        with (
            patch.object(toolchains.sysconfig, "get_path", return_value=str(self.root / "empty")),
            patch.object(toolchains.os, "get_exec_path", return_value=["first", "second"]),
            patch.object(toolchains.shutil, "which", side_effect=which),
            patch.object(
                toolchains, "probe_cli", side_effect=[toolchains.ToolchainError("wrong version"), "verified_commit"]
            ),
        ):
            self.assertEqual(toolchains.discover_cli(settings, self.selection), str(right))

    def test_override_preview_native_uses_isolated_venv_and_conda_names_are_distinct(self):
        for mode in ("native", "conda"):
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "setup_tooling.py"),
                    "--mode",
                    mode,
                    "--toolchain-record",
                    str(self.record()),
                    "--env-dir",
                    str(self.root / "env"),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )
            plan = json.loads(result.stdout)
            self.assertFalse(plan["apply"])
            self.assertIn(self.selection["upstream_commit"], plan["environment"])
            self.assertTrue(any(toolchains.requirement(self.selection) in command for command in plan["commands"]))
            self.assertEqual(plan["effective_install_mode"], "venv" if mode == "native" else "conda")
        self.assertFalse((self.root / "env").exists())


@unittest.skipUnless(
    os.environ.get("SPECIFY_BIN")
    and os.environ.get("SPECIFY_ALTERNATE_BIN")
    and os.environ.get("SPECIFY_ALTERNATE_RECORD"),
    "Set default and alternate CLI paths and alternate record for live version tests",
)
class LiveVersionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "project"

    def install(self, alternate=False, *extra):
        args = [
            sys.executable,
            str(ROOT / "install.py"),
            str(self.repo),
            "--specify",
            os.environ["SPECIFY_ALTERNATE_BIN" if alternate else "SPECIFY_BIN"],
        ]
        if alternate:
            args += ["--toolchain-record", os.environ["SPECIFY_ALTERNATE_RECORD"]]
        return subprocess.run(args + list(extra), capture_output=True, text=True, encoding="utf-8")

    def test_alternate_preview_apply_and_upgrade_preserve_authored_files(self):
        preview = self.install(True)
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertFalse(self.repo.exists())
        result = self.install(True, "--apply")
        self.assertEqual(result.returncode, 0, result.stderr)
        ledger_path = self.repo / ".specify/engineering-install.json"
        before = ledger_path.read_bytes()
        authored = self.repo / "AI_CONTEXT.md"
        authored.write_text("Project-owned instructions\n", encoding="utf-8")
        preview = self.install(False, "--upgrade")
        self.assertEqual(preview.returncode, 0, preview.stderr)
        plan = json.loads(preview.stdout)
        self.assertIn("AI_CONTEXT.md", plan["preserve_authored"])
        self.assertTrue(plan["replace_unmodified"])
        self.assertEqual(ledger_path.read_bytes(), before)
        applied = self.install(False, "--upgrade", "--apply")
        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assertEqual(authored.read_text(encoding="utf-8"), "Project-owned instructions\n")
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        self.assertEqual(ledger["toolchain"]["upstream_commit"], toolchains.lock()["upstream_commit"])

    def test_mismatched_cli_fails_before_target_writes(self):
        result = self.install(False, "--toolchain-record", os.environ["SPECIFY_ALTERNATE_RECORD"], "--apply")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not match CLI", result.stderr)
        self.assertFalse(self.repo.exists())

    def test_alternate_cli_discovered_on_path_without_specify_flag(self):
        env = dict(
            os.environ, PATH=str(Path(os.environ["SPECIFY_ALTERNATE_BIN"]).parent) + os.pathsep + os.environ["PATH"]
        )
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "install.py"),
                str(self.repo),
                "--toolchain-record",
                os.environ["SPECIFY_ALTERNATE_RECORD"],
            ],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["compatibility"]["source_verification"], "verified_commit")
        self.assertFalse(self.repo.exists())

    def test_alternate_all_integrations(self):
        result = self.install(
            True, "--integration", "codex", "--integration", "cursor-agent", "--integration", "copilot", "--apply"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        record = json.loads((self.repo / ".specify/engineering-install.json").read_text(encoding="utf-8"))
        self.assertEqual(record["compatibility"]["source_verification"], "verified_commit")
        self.assertEqual(record["compatibility"]["classification"], "local_override_checked")


if __name__ == "__main__":
    unittest.main()
