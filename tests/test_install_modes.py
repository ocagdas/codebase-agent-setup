"""Installer modes: seeding, upgrade preservation, obsolete removal and --adopt migration."""

import argparse
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from codebase_agent_setup import install

GUIDE = "ai_workflow/project_guide.md"


class InstallHarness(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "repo"
        self.repo.mkdir()
        self.user = Path(self.temp.name) / "absent-user-config.json"

    def args(self, **options):
        values = {
            "repo": self.repo,
            "integration": None,
            "user_config": self.user,
            "upgrade": False,
            "apply": True,
            "adopt": False,
            "remove_obsolete": False,
        }
        values.update(options)
        return argparse.Namespace(**values)

    def run_install(self, **options):
        output = io.StringIO()
        with redirect_stdout(output):
            install.install(self.args(**options))
        plan, _ = json.JSONDecoder().raw_decode(output.getvalue())
        return plan

    def ledger(self):
        return json.loads((self.repo / install.LEDGER).read_text(encoding="utf-8"))


class RefusalTests(InstallHarness):
    """Regression cover for two behaviours whose only tests were gated on a CLI this package no longer ships."""

    def test_a_dry_run_writes_nothing_at_all(self):
        absent = Path(self.temp.name) / "never-created"
        plan = self.run_install(repo=absent, apply=False)
        self.assertFalse(plan["apply"])
        self.assertFalse(absent.exists(), "a dry run must not even create the target directory")

    def test_invalid_settings_stop_before_anything_is_written(self):
        config = self.repo / "ai_workflow/settings.local.json"
        config.parent.mkdir(parents=True)
        config.write_text('{"schema_version": "1.0", "settings": {"approvals": false}}', encoding="utf-8")
        with self.assertRaises(Exception) as caught:
            self.run_install()
        self.assertIn("approvals", str(caught.exception))
        self.assertFalse((self.repo / "AI_CONTEXT.md").exists())
        self.assertFalse((self.repo / install.LEDGER).exists())


class InstallModeTests(InstallHarness):
    def test_install_seeds_the_guide_layer(self):
        self.run_install()
        for relative in (
            "AI_CONTEXT.md",
            "AGENTS.md",
            "CLAUDE.md",
            "GEMINI.md",
            GUIDE,
            "ai_workflow/handover.md",
            "ai_workflow/tools/settings.py",
            "ai_workflow/tools/validate_handover.py",
            "ai_workflow/settings.md",
        ):
            self.assertTrue((self.repo / relative).is_file(), relative)
        # Spec Kit is no longer CAS's business: nothing of it is installed or claimed.
        for relative in ("ai_workflow/speckit_workflow.md", "ai_workflow/project.yaml", ".specify"):
            self.assertFalse((self.repo / relative).exists(), relative)
        ledger = self.ledger()
        self.assertNotIn(GUIDE, ledger["files"])
        self.assertIn("AI_CONTEXT.md", ledger["files"])

    def test_existing_project_guide_is_kept_on_first_install(self):
        (self.repo / "ai_workflow").mkdir()
        (self.repo / GUIDE).write_text("our guide\n", encoding="utf-8")
        plan = self.run_install()
        self.assertEqual((self.repo / GUIDE).read_text(encoding="utf-8"), "our guide\n")
        self.assertIn(GUIDE, plan["keep_existing"])

    def test_upgrade_never_touches_edited_project_guide(self):
        self.run_install()
        (self.repo / GUIDE).write_text("filled in by the owner\n", encoding="utf-8")
        plan = self.run_install(upgrade=True)
        self.assertEqual((self.repo / GUIDE).read_text(encoding="utf-8"), "filled in by the owner\n")
        self.assertNotIn(GUIDE, plan["replace_unmodified"])
        self.assertNotIn(GUIDE, plan["preserve_authored"])

    def test_command_line_surface_installs_without_any_external_tool(self):
        import os
        import subprocess

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "codebase_agent_setup",
                "install",
                str(self.repo),
                "--apply",
                "--user-config",
                str(self.user),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env={**os.environ, "PATH": "/nonexistent", "PYTHONPATH": str(ROOT / "src")},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.repo / "AI_CONTEXT.md").is_file())
        self.assertIn("Installed the agent guide", result.stdout)


class ObsoleteRemovalTests(InstallHarness):
    """A payload that drops a managed file must be able to retire it from consumer repositories."""

    OBSOLETE = "ai_workflow/retired_guide.md"

    def seed_with_obsolete(self, content="managed content\n"):
        self.run_install()
        path = self.repo / self.OBSOLETE
        path.write_text(content, encoding="utf-8")
        ledger_path = self.repo / install.LEDGER
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        ledger["files"][self.OBSOLETE] = install.digest(path)
        ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
        return path

    def test_reported_but_kept_without_the_flag(self):
        path = self.seed_with_obsolete()
        plan = self.run_install(upgrade=True)
        self.assertEqual(plan["retain_obsolete"], [self.OBSOLETE])
        self.assertEqual(plan["removed_obsolete"], [])
        self.assertTrue(path.is_file())
        self.assertIn(self.OBSOLETE, self.ledger()["files"])

    def test_unmodified_obsolete_file_is_archived_and_removed(self):
        path = self.seed_with_obsolete()
        plan = self.run_install(upgrade=True, remove_obsolete=True)
        self.assertEqual(plan["removed_obsolete"], [self.OBSOLETE])
        self.assertFalse(path.exists())
        backups = list((self.repo / ".ai_migration_backup").rglob("retired_guide.md"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), "managed content\n")
        self.assertNotIn(self.OBSOLETE, self.ledger()["files"])

    def test_locally_edited_obsolete_file_is_never_removed(self):
        path = self.seed_with_obsolete()
        path.write_text("the owner changed this\n", encoding="utf-8")
        plan = self.run_install(upgrade=True, remove_obsolete=True)
        self.assertEqual(plan["removed_obsolete"], [])
        self.assertEqual(plan["obsolete_modified"], [self.OBSOLETE])
        self.assertEqual(path.read_text(encoding="utf-8"), "the owner changed this\n")
        self.assertIn(self.OBSOLETE, self.ledger()["files"])

    def test_removal_requires_upgrade(self):
        self.seed_with_obsolete()
        with self.assertRaisesRegex(RuntimeError, "--upgrade"):
            self.run_install(remove_obsolete=True)


class AdoptTests(InstallHarness):
    AUTHORED = "# Agent Instructions\n\nRead `docs/project/agent-guidance.md` before making changes.\n"

    def setUp(self):
        super().setUp()
        (self.repo / "AGENTS.md").write_text(self.AUTHORED, encoding="utf-8")
        (self.repo / "CLAUDE.md").write_text(
            "Use [guidance](docs/project/agent-guidance.md) and `missing.md`.\n", encoding="utf-8"
        )
        (self.repo / "docs/project").mkdir(parents=True)
        (self.repo / "docs/project/agent-guidance.md").write_text("master\n", encoding="utf-8")

    def payload(self, relative):
        return (ROOT / "project" / relative).read_text(encoding="utf-8")

    def test_without_adopt_authored_pointer_is_a_conflict(self):
        with self.assertRaisesRegex(RuntimeError, "AGENTS.md"):
            self.run_install()
        self.assertEqual((self.repo / "AGENTS.md").read_text(encoding="utf-8"), self.AUTHORED)

    def test_adopt_imports_text_backs_up_and_replaces_pointers(self):
        plan = self.run_install(adopt=True)
        self.assertEqual(plan["adopted"], ["AGENTS.md", "CLAUDE.md"])
        guide = (self.repo / GUIDE).read_text(encoding="utf-8")
        self.assertIn("## Imported from AGENTS.md (review)\n\n" + self.AUTHORED, guide)
        self.assertIn("## Imported from CLAUDE.md (review)", guide)
        self.assertIn("<!-- cbsetup:unfilled -->", guide)
        self.assertEqual((self.repo / "AGENTS.md").read_text(encoding="utf-8"), self.payload("AGENTS.md"))
        backups = list((self.repo / ".ai_migration_backup").rglob("AGENTS.md"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), self.AUTHORED)

    def test_adopt_reports_referenced_guidance_that_exists(self):
        plan = self.run_install(adopt=True, apply=False)
        self.assertEqual(plan["referenced_guidance"], ["docs/project/agent-guidance.md"])
        self.assertFalse((self.repo / GUIDE).exists())

    def test_backticked_paths_in_nested_entry_files_resolve_from_repository_root(self):
        (self.repo / ".github").mkdir()
        (self.repo / ".github/copilot-instructions.md").write_text(
            "Use `docs/project/copilot-extra.md` and [local](notes.md).\n", encoding="utf-8"
        )
        (self.repo / "docs/project/copilot-extra.md").write_text("extra\n", encoding="utf-8")
        (self.repo / ".github/notes.md").write_text("notes\n", encoding="utf-8")
        plan = self.run_install(adopt=True, apply=False)
        self.assertIn("docs/project/copilot-extra.md", plan["referenced_guidance"])
        self.assertIn(".github/notes.md", plan["referenced_guidance"])

    def test_adopt_refuses_when_project_guide_exists(self):
        (self.repo / "ai_workflow").mkdir()
        (self.repo / GUIDE).write_text("already migrated\n", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "project_guide.md"):
            self.run_install(adopt=True)
        self.assertEqual((self.repo / "AGENTS.md").read_text(encoding="utf-8"), self.AUTHORED)

    def test_adopt_refuses_symlinked_pointer(self):
        (self.repo / "GEMINI.md").symlink_to(self.repo / "docs/project/agent-guidance.md")
        with self.assertRaisesRegex(RuntimeError, "GEMINI.md"):
            self.run_install(adopt=True)
        self.assertEqual((self.repo / "AGENTS.md").read_text(encoding="utf-8"), self.AUTHORED)
        self.assertFalse((self.repo / GUIDE).exists())

    def test_identical_pointer_is_not_adopted(self):
        (self.repo / "GEMINI.md").write_text(self.payload("GEMINI.md"), encoding="utf-8")
        plan = self.run_install(adopt=True)
        self.assertNotIn("GEMINI.md", plan["adopted"])


if __name__ == "__main__":
    unittest.main()
