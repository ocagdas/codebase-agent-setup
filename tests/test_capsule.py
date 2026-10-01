"""Portable capture and replay of the half of an agent setup that git cannot hold."""

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from codebase_agent_setup import capsule, redact


class CapsuleHarness(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.home = self.base / "home"
        self.repo = self.base / "repo"
        for folder in (self.home, self.repo):
            folder.mkdir()
        # The user config: machine-wide settings, carrying one secret.
        self.config = capsule.tool_root(capsule.USER_CONFIG, self.home) / "config.json"
        self.config.parent.mkdir(parents=True)
        self.config.write_text(
            json.dumps(
                {
                    "tooling": {"mode": "venv"},
                    "sourcegraph": {"token": "sk-live-AAAAAAAAAAAAAAAAAAAA", "token_env": "SOURCEGRAPH_TOKEN"},
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        # A tool's own global directory.
        self.claude = capsule.tool_root(capsule.TOOL_PATHS[0], self.home) / "settings.json"
        self.claude.parent.mkdir(parents=True)
        self.claude.write_text(json.dumps({"model": "opus", "apiKey": "sk-ant-AAAAAAAAAAAAAAAAAAAA"}), encoding="utf-8")
        # Per-checkout local settings: never committed, always needed again.
        self.local = self.repo / "ai_workflow/settings.local.json"
        self.local.parent.mkdir(parents=True)
        self.local.write_text(json.dumps({"knowledge": {"mode": "auto"}}), encoding="utf-8")

    def create(self, **options):
        options.setdefault("home", self.home)
        options.setdefault("repos", [self.repo])
        options.setdefault("out_dir", self.base / "capsule")
        return capsule.create(capsule.Request(**options))

    def manifest(self, folder):
        return json.loads((Path(folder) / "manifest.json").read_text(encoding="utf-8"))


class CreateTests(CapsuleHarness):
    def test_explicit_home_does_not_capture_the_current_users_windows_config(self):
        with patch.dict("os.environ", {"APPDATA": str(self.base / "ambient")}):
            self.assertEqual(
                capsule.tool_root(capsule.USER_CONFIG, self.home, windows=True),
                self.home / "AppData/Roaming/codebase-agent-setup",
            )

    def test_folder_capture_records_a_manifest_and_the_files(self):
        result = self.create()
        manifest = self.manifest(result.location)
        self.assertEqual(manifest["schema_version"], capsule.SCHEMA_VERSION)
        self.assertIn(manifest["host_class"], ("linux", "darwin", "windows"))
        origins = {entry["origin"] for entry in manifest["entries"]}
        self.assertEqual(origins, {"user-config", "tool-global", "repo"})
        for entry in manifest["entries"]:
            with self.subTest(entry["path"]):
                self.assertTrue((Path(result.location) / "files" / entry["path"]).is_file())
                self.assertEqual(
                    capsule.digest_bytes((Path(result.location) / "files" / entry["path"]).read_bytes()),
                    entry["sha256"],
                )

    def test_zip_is_the_default_and_contains_the_same_manifest(self):
        result = capsule.create(capsule.Request(home=self.home, repos=[self.repo], out=self.base / "setup.zip"))
        with zipfile.ZipFile(result.location) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            self.assertTrue(manifest["entries"])
            for entry in manifest["entries"]:
                self.assertEqual(
                    capsule.digest_bytes(archive.read("files/" + entry["path"])),
                    entry["sha256"],
                )

    def test_every_secret_is_removed_and_reported(self):
        result = self.create()
        reported = {(r.entry, r.removal.location) for r in result.redactions}
        self.assertIn(("user-config/config.json", "sourcegraph.token"), reported)
        self.assertIn(("tool-global/claude/settings.json", "apiKey"), reported)
        for path in Path(result.location).rglob("*"):
            if path.is_file():
                body = path.read_text(encoding="utf-8")
                with self.subTest(path.name):
                    self.assertNotIn("sk-live-", body)
                    self.assertNotIn("sk-ant-", body)

    def test_a_pointer_to_a_secret_survives_so_the_setup_still_works(self):
        result = self.create()
        captured = (Path(result.location) / "files/user-config/config.json").read_text(encoding="utf-8")
        self.assertIn("SOURCEGRAPH_TOKEN", captured)
        self.assertIn(redact.PLACEHOLDER, captured)

    def test_the_manifest_names_each_redaction_so_a_reviewer_sees_them_without_the_files(self):
        manifest = self.manifest(self.create().location)
        entry = next(e for e in manifest["entries"] if e["path"] == "user-config/config.json")
        self.assertEqual([r["location"] for r in entry["redactions"]], ["sourcegraph.token"])

    def test_a_home_directory_sweep_is_refused_as_a_sweep_not_as_a_missing_file(self):
        """The refusal must come from the sweep rule itself, so it holds however home is named."""
        for include in (self.home, Path("~"), self.home / "*", Path(self.home.anchor)):
            with self.subTest(str(include)):
                with self.assertRaises(capsule.CapsuleError) as raised:
                    self.create(include=[include])
                self.assertRegex(str(raised.exception), r"(?i)refusing (a glob|to capture)")

    def test_a_directory_named_in_include_is_refused_even_when_it_is_not_home(self):
        folder = self.home / "notes"
        folder.mkdir()
        (folder / "a.md").write_text("x\n", encoding="utf-8")
        with self.assertRaisesRegex(capsule.CapsuleError, "is not a file"):
            self.create(include=[folder])

    def test_an_arbitrary_include_is_captured_but_marked_host_specific(self):
        extra = self.home / "notes/setup-notes.md"
        extra.parent.mkdir()
        extra.write_text("remember to run make check\n", encoding="utf-8")
        manifest = self.manifest(self.create(include=[extra]).location)
        entry = next(e for e in manifest["entries"] if e["path"].endswith("setup-notes.md"))
        self.assertTrue(entry["host_specific"])
        self.assertTrue(all(not e["host_specific"] for e in manifest["entries"] if e is not entry))

    def test_an_excluded_path_is_not_captured(self):
        manifest = self.manifest(self.create(exclude=[self.claude]).location)
        self.assertNotIn("tool-global/claude/settings.json", [e["path"] for e in manifest["entries"]])

    def test_capturing_nothing_is_an_error_rather_than_an_empty_capsule(self):
        with self.assertRaisesRegex(capsule.CapsuleError, "nothing to capture"):
            capsule.create(capsule.Request(home=self.base / "empty-home", repos=[], out_dir=self.base / "none"))


class ShowTests(CapsuleHarness):
    def test_show_reports_provenance_and_redactions_for_either_format(self):
        folder = self.create().location
        archive = capsule.create(capsule.Request(home=self.home, repos=[self.repo], out=self.base / "s.zip")).location
        for location in (folder, archive):
            with self.subTest(str(location)):
                summary = capsule.show(location)
                self.assertEqual(summary["schema_version"], capsule.SCHEMA_VERSION)
                self.assertTrue(summary["redactions"])
                self.assertEqual(len(summary["entries"]), len(self.manifest(folder)["entries"]))


class ApplyTests(CapsuleHarness):
    def setUp(self):
        super().setUp()
        self.source = self.create().location
        self.target_home = self.base / "other-home"
        self.target_repo = self.base / "other-repo"
        self.target_home.mkdir()
        self.target_repo.mkdir()

    def apply(self, **options):
        options.setdefault("home", self.target_home)
        options.setdefault("repo", self.target_repo)
        return capsule.apply(self.source, capsule.Target(**options))

    def test_dry_run_is_the_default_and_writes_nothing(self):
        plan = self.apply()
        self.assertFalse(plan["apply"])
        self.assertTrue(plan["writes"])
        self.assertEqual(list(self.target_repo.rglob("*")), [])
        self.assertEqual(list(self.target_home.rglob("*")), [])

    def test_applying_to_another_repository_and_home_is_a_clone(self):
        plan = self.apply(apply=True)
        self.assertTrue(plan["apply"])
        self.assertTrue((self.target_repo / "ai_workflow/settings.local.json").is_file())
        self.assertTrue((capsule.tool_root(capsule.USER_CONFIG, self.target_home) / "config.json").is_file())
        self.assertTrue((capsule.tool_root(capsule.TOOL_PATHS[0], self.target_home) / "settings.json").is_file())

    def test_apply_reports_every_redaction_the_owner_must_restore_by_hand(self):
        plan = self.apply(apply=True)
        locations = {(r["entry"], r["location"]) for r in plan["restore_by_hand"]}
        self.assertIn(("user-config/config.json", "sourcegraph.token"), locations)
        self.assertIn(("tool-global/claude/settings.json", "apiKey"), locations)
        written = (capsule.tool_root(capsule.USER_CONFIG, self.target_home) / "config.json").read_text(encoding="utf-8")
        self.assertIn(redact.PLACEHOLDER, written)

    def test_an_existing_different_file_is_a_collision_and_nothing_is_written(self):
        existing = self.target_repo / "ai_workflow/settings.local.json"
        existing.parent.mkdir(parents=True)
        existing.write_text("mine\n", encoding="utf-8")
        with self.assertRaisesRegex(capsule.CapsuleError, "settings.local.json"):
            self.apply(apply=True)
        self.assertEqual(existing.read_text(encoding="utf-8"), "mine\n")
        self.assertFalse((capsule.tool_root(capsule.TOOL_PATHS[0], self.target_home) / "settings.json").exists())

    def test_overwrite_replaces_a_colliding_file_and_says_so(self):
        existing = self.target_repo / "ai_workflow/settings.local.json"
        existing.parent.mkdir(parents=True)
        existing.write_text("mine\n", encoding="utf-8")
        plan = self.apply(apply=True, overwrite=True)
        self.assertIn(str(existing), plan["replaced"])
        self.assertNotEqual(existing.read_text(encoding="utf-8"), "mine\n")

    def test_an_identical_existing_file_is_not_a_collision(self):
        self.apply(apply=True)
        plan = self.apply(apply=True)
        self.assertEqual(plan["replaced"], [])
        self.assertEqual(plan["writes"], [])

    def test_a_capsule_from_a_newer_schema_is_refused(self):
        manifest_path = Path(self.source) / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["schema_version"] = "99.0"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(capsule.CapsuleError, "newer"):
            self.apply()

    def test_a_tampered_file_is_refused_before_anything_is_written(self):
        (Path(self.source) / "files/user-config/config.json").write_text("tampered\n", encoding="utf-8")
        with self.assertRaisesRegex(capsule.CapsuleError, "does not match"):
            self.apply(apply=True)
        self.assertFalse((capsule.tool_root(capsule.TOOL_PATHS[0], self.target_home) / "settings.json").exists())

    def test_a_host_specific_entry_is_skipped_on_a_different_host_class(self):
        manifest_path = Path(self.source) / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["host_class"] = "windows" if manifest["host_class"] != "windows" else "linux"
        for entry in manifest["entries"]:
            entry["host_specific"] = True
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        plan = self.apply(apply=True)
        self.assertTrue(plan["skipped_host_specific"])
        self.assertEqual(plan["writes"], [])

    def test_applying_only_the_machine_layer_leaves_the_repository_alone(self):
        plan = self.apply(apply=True, repo=None)
        self.assertTrue((capsule.tool_root(capsule.TOOL_PATHS[0], self.target_home) / "settings.json").is_file())
        self.assertEqual(list(self.target_repo.rglob("*")), [])
        self.assertTrue(plan["skipped_no_target"])

    def test_a_capsule_entry_may_not_escape_its_target(self):
        manifest_path = Path(self.source) / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["entries"][0]["target_hint"] = "../escaped.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(capsule.CapsuleError):
            self.apply(apply=True)


if __name__ == "__main__":
    unittest.main()
