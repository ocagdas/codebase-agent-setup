"""Many repositories at once: status across the fleet, and mass apply with a publication policy."""

import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from codebase_agent_setup import fleet, install


class FleetHarness(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.repos = {}
        for name in ("open-repo", "owner-repo"):
            path = self.base / name
            path.mkdir()
            self.repos[name] = path
        self.file = self.base / "fleet.json"
        self.write_fleet(
            [
                {"path": str(self.repos["open-repo"])},
                {"path": str(self.repos["owner-repo"]), "publication": "owner-only"},
            ]
        )

    def write_fleet(self, repositories):
        self.file.write_text(
            json.dumps({"schema_version": fleet.SCHEMA_VERSION, "repositories": repositories}, indent=2),
            encoding="utf-8",
        )

    def seed(self, name):
        import argparse
        import contextlib
        import io

        args = argparse.Namespace(
            repo=self.repos[name],
            integration=None,
            user_config=self.base / "absent.json",
            upgrade=False,
            apply=True,
            adopt=False,
            remove_obsolete=False,
        )
        with contextlib.redirect_stdout(io.StringIO()):
            install.install(args)


class LoadTests(FleetHarness):
    def test_a_missing_fleet_file_says_how_to_make_one(self):
        with self.assertRaisesRegex(fleet.FleetError, "fleet.json"):
            fleet.load(self.base / "absent.json")

    def test_a_newer_schema_is_refused(self):
        self.file.write_text(json.dumps({"schema_version": "99.0", "repositories": []}), encoding="utf-8")
        with self.assertRaisesRegex(fleet.FleetError, "newer"):
            fleet.load(self.file)

    def test_an_unknown_publication_policy_is_refused_rather_than_ignored(self):
        self.write_fleet([{"path": str(self.repos["open-repo"]), "publication": "sometimes"}])
        with self.assertRaisesRegex(fleet.FleetError, "publication"):
            fleet.load(self.file)

    def test_duplicate_repositories_are_refused(self):
        path = str(self.repos["open-repo"])
        self.write_fleet([{"path": path}, {"path": path}])
        with self.assertRaisesRegex(fleet.FleetError, "listed twice"):
            fleet.load(self.file)

    def test_relative_paths_resolve_against_the_fleet_file_not_the_shell(self):
        self.write_fleet([{"path": "open-repo"}])
        entries = fleet.load(self.file)
        self.assertEqual(entries[0].path, self.repos["open-repo"])


class StatusTests(FleetHarness):
    def test_an_uninstalled_repository_is_reported_not_skipped(self):
        rows = fleet.status(fleet.load(self.file))
        row = next(r for r in rows if r["repository"] == "open-repo")
        self.assertFalse(row["installed"])
        self.assertEqual(row["managed"], 0)

    def test_an_installed_repository_reports_its_managed_files_and_no_drift(self):
        self.seed("open-repo")
        row = next(r for r in fleet.status(fleet.load(self.file)) if r["repository"] == "open-repo")
        self.assertTrue(row["installed"])
        self.assertGreater(row["managed"], 0)
        self.assertEqual(row["drift"], [])

    def test_a_locally_edited_managed_file_is_reported_as_drift(self):
        self.seed("open-repo")
        (self.repos["open-repo"] / "AI_CONTEXT.md").write_text("edited by hand\n", encoding="utf-8")
        row = next(r for r in fleet.status(fleet.load(self.file)) if r["repository"] == "open-repo")
        self.assertEqual(row["drift"], ["AI_CONTEXT.md"])

    def test_a_deleted_managed_file_is_reported_as_missing_not_as_drift(self):
        self.seed("open-repo")
        (self.repos["open-repo"] / "AI_CONTEXT.md").unlink()
        row = next(r for r in fleet.status(fleet.load(self.file)) if r["repository"] == "open-repo")
        self.assertEqual(row["missing"], ["AI_CONTEXT.md"])
        self.assertEqual(row["drift"], [])

    def test_an_unfilled_project_guide_is_flagged_because_it_is_the_one_manual_step(self):
        self.seed("open-repo")
        row = next(r for r in fleet.status(fleet.load(self.file)) if r["repository"] == "open-repo")
        self.assertFalse(row["guide_filled"])
        (self.repos["open-repo"] / install.GUIDE).write_text("# Project guide\n\nReal content.\n", encoding="utf-8")
        row = next(r for r in fleet.status(fleet.load(self.file)) if r["repository"] == "open-repo")
        self.assertTrue(row["guide_filled"])

    def test_a_missing_repository_directory_is_reported_without_failing_the_run(self):
        self.write_fleet([{"path": str(self.base / "gone")}, {"path": str(self.repos["open-repo"])}])
        rows = fleet.status(fleet.load(self.file))
        self.assertFalse(rows[0]["exists"])
        self.assertTrue(rows[1]["exists"])

    def test_the_publication_policy_is_carried_into_the_status_row(self):
        rows = {row["repository"]: row for row in fleet.status(fleet.load(self.file))}
        self.assertEqual(rows["open-repo"]["publication"], "open")
        self.assertEqual(rows["owner-repo"]["publication"], "owner-only")


class ApplyTests(FleetHarness):
    def test_fleet_defaults_to_local_only_with_an_explicit_override(self):
        result = fleet.apply(fleet.load(self.file), fleet.Options(apply=False))
        self.assertTrue(result["repositories"][0]["local_only"])
        result = fleet.apply(fleet.load(self.file), fleet.Options(apply=False, track_guidance=True))
        self.assertFalse(result["repositories"][0]["local_only"])
        self.assertNotIn("/AI_CONTEXT.md", result["repositories"][0]["gitignore_additions"])

    def test_explicit_dry_run_touches_nothing(self):
        result = fleet.apply(fleet.load(self.file), fleet.Options(apply=False))
        self.assertFalse(result["apply"])
        self.assertEqual(list(self.repos["open-repo"].rglob("*")), [])

    def test_owner_only_repositories_are_skipped_unless_named_explicitly(self):
        result = fleet.apply(fleet.load(self.file), fleet.Options(apply=True))
        self.assertEqual(result["skipped_owner_only"], ["owner-repo"])
        self.assertTrue((self.repos["open-repo"] / "AI_CONTEXT.md").is_file())
        self.assertFalse((self.repos["owner-repo"] / "AI_CONTEXT.md").exists())

    def test_including_owner_only_repositories_is_an_explicit_choice(self):
        result = fleet.apply(fleet.load(self.file), fleet.Options(apply=True, include_owner_only=True))
        self.assertEqual(result["skipped_owner_only"], [])
        self.assertTrue((self.repos["owner-repo"] / "AI_CONTEXT.md").is_file())

    def test_one_failing_repository_does_not_stop_the_others_and_is_reported(self):
        collision = self.repos["open-repo"] / "AI_CONTEXT.md"
        collision.mkdir()
        result = fleet.apply(fleet.load(self.file), fleet.Options(apply=True, include_owner_only=True))
        failed = {row["repository"]: row for row in result["failed"]}
        self.assertIn("open-repo", failed)
        self.assertIn("AI_CONTEXT.md", failed["open-repo"]["error"])
        self.assertTrue(collision.is_dir())
        self.assertTrue((self.repos["owner-repo"] / "AI_CONTEXT.md").is_file())

    def test_a_second_apply_reports_each_repository_as_already_current(self):
        fleet.apply(fleet.load(self.file), fleet.Options(apply=True))
        result = fleet.apply(fleet.load(self.file), fleet.Options(apply=True, upgrade=True))
        row = next(r for r in result["repositories"] if r["repository"] == "open-repo")
        self.assertEqual(row["replace_unmodified"], [])


if __name__ == "__main__":
    unittest.main()
