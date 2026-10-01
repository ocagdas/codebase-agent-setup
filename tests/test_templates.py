"""Editable template CLI flows and safe transactional target installation."""

import argparse
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from codebase_agent_setup import fleet, install, install_transaction, templates


class TemplateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.source = self.base / "edited template"
        self.target = self.base / "target"
        self.user = self.base / "missing.json"

    def export(self):
        return templates.create(self.source, apply=True)

    def run_install(self, **options):
        values = dict(
            repo=self.target,
            template=self.source,
            user_config=self.user,
            integration=None,
            apply=True,
            upgrade=False,
            adopt=False,
            replace_guide=False,
            remove_obsolete=False,
        )
        values.update(options)
        output = io.StringIO()
        with redirect_stdout(output):
            install.install(argparse.Namespace(**values))
        return json.JSONDecoder().raw_decode(output.getvalue())[0]

    def edit_guide(self, text="# Team guide\n\nUse the team's checks.\n"):
        (self.source / install.GUIDE).write_text(text, encoding="utf-8")
        return text

    def command(self, *args):
        result = subprocess.run(
            [sys.executable, "-m", "codebase_agent_setup", *map(str, args)],
            cwd=self.base,
            env=os.environ | {"PYTHONPATH": str(ROOT / "src")},
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.JSONDecoder().raw_decode(result.stdout)[0]

    def test_export_preview_and_empty_directory_do_not_overwrite(self):
        plan = templates.create(self.source, apply=False)
        self.assertFalse(plan["apply"])
        self.assertFalse(self.source.exists())
        self.source.mkdir()
        self.export()
        before = (self.source / templates.MANIFEST).read_bytes()
        with self.assertRaisesRegex(templates.TemplateError, "new or empty"):
            self.export()
        self.assertEqual((self.source / templates.MANIFEST).read_bytes(), before)

    def test_export_contains_only_baseline_not_local_state_or_test_scripts(self):
        plan = self.export()
        self.assertEqual(set(templates.snapshot(self.source).files), set(plan["files"]))
        for name in plan["files"]:
            self.assertFalse(name.startswith((".cbsetup/", ".git/", ".ai_cache/")))
            self.assertNotIn("settings.local.json", name)
            self.assertFalse(Path(name).name.startswith("test_"))

    def test_real_cli_export_edit_single_preview_apply_and_fleet(self):
        preview = self.command("template", "create", self.source, "--dry-run")
        self.assertFalse(preview["apply"])
        self.assertFalse(self.source.exists())
        self.command("template", "create", self.source)
        guide = self.edit_guide()
        plan = self.command("install", self.target, "--template", self.source, "--user-config", self.user, "--dry-run")
        self.assertFalse(plan["apply"])
        self.assertFalse(self.target.exists())
        applied = self.command("install", self.target, "--template", self.source, "--user-config", self.user)
        self.assertTrue(applied["apply"])
        self.assertEqual(applied["behaviour"], "upgrade")
        self.assertEqual((self.target / install.GUIDE).read_text(encoding="utf-8"), guide)
        other = self.base / "other target"
        other.mkdir()
        fleet_file = self.base / "fleet.json"
        fleet_file.write_text(
            json.dumps({"schema_version": "1.0", "repositories": [{"path": str(other)}]}), encoding="utf-8"
        )
        plan = self.command(
            "fleet", "--file", fleet_file, "--user-config", self.user, "apply", "--template", self.source, "--dry-run"
        )
        self.assertFalse(plan["apply"])
        self.assertFalse((other / "AI_CONTEXT.md").exists())
        self.command("fleet", "--file", fleet_file, "--user-config", self.user, "apply", "--template", self.source)
        self.assertEqual((other / install.GUIDE).read_text(encoding="utf-8"), guide)
        ledger = json.loads((other / install.LEDGER).read_text(encoding="utf-8"))
        self.assertNotIn(install.GUIDE, ledger["files"])
        self.assertNotIn(templates.MANIFEST, ledger["files"])
        self.assertIn("/ai_workflow/", (other / ".gitignore").read_text(encoding="utf-8"))

    def test_existing_guide_is_preserved_unless_explicitly_replaced_and_backed_up(self):
        self.export()
        self.target.mkdir()
        (self.target / "ai_workflow").mkdir()
        (self.target / install.GUIDE).write_text("Owner policy\n", encoding="utf-8")
        self.run_install()
        self.edit_guide()
        self.run_install(upgrade=True)
        self.assertEqual((self.target / install.GUIDE).read_text(encoding="utf-8"), "Owner policy\n")
        self.run_install(upgrade=True, replace_guide=True)
        copies = list((self.target / ".ai_migration_backup").rglob("project_guide.md"))
        self.assertEqual(len(copies), 1)
        self.assertEqual(copies[0].read_text(encoding="utf-8"), "Owner policy\n")
        self.assertEqual(
            (self.target / install.GUIDE).read_text(encoding="utf-8"), "# Team guide\n\nUse the team's checks.\n"
        )

    def test_upgrade_updates_managed_files_but_preserves_authored_edits(self):
        self.export()
        self.run_install()
        incoming = self.source / "AI_CONTEXT.md"
        incoming.write_text(incoming.read_text(encoding="utf-8") + "\nTeam addition\n", encoding="utf-8")
        self.run_install(upgrade=True)
        self.assertEqual((self.target / "AI_CONTEXT.md").read_bytes(), incoming.read_bytes())
        (self.target / "AI_CONTEXT.md").write_text("Owner edit\n", encoding="utf-8")
        self.assertIn("AI_CONTEXT.md", self.run_install(upgrade=True)["preserve_authored"])

    def test_behaviour_preserve_upgrade_and_override(self):
        self.export()
        self.run_install(behaviour="upgrade")
        incoming = self.source / "AI_CONTEXT.md"
        incoming.write_text(incoming.read_text(encoding="utf-8") + "\nTeam update\n", encoding="utf-8")
        before = (self.target / "AI_CONTEXT.md").read_bytes()
        plan = self.run_install(behaviour="preserve")
        self.assertIn("AI_CONTEXT.md", plan["preserve_authored"])
        self.assertEqual((self.target / "AI_CONTEXT.md").read_bytes(), before)
        self.run_install(behaviour="upgrade")
        self.assertEqual((self.target / "AI_CONTEXT.md").read_bytes(), incoming.read_bytes())
        (self.target / "AI_CONTEXT.md").write_text("Authored edit\n", encoding="utf-8")
        (self.target / install.GUIDE).write_text("Owner guide\n", encoding="utf-8")
        self.edit_guide()
        unrelated = self.target / "notes.txt"
        unrelated.write_text("Untouched\n", encoding="utf-8")
        local = self.target / "ai_workflow/settings.local.json"
        local.write_text('{"schema_version":"1.0","settings":{}}', encoding="utf-8")
        self.run_install(behaviour="override", apply=False)
        self.assertEqual((self.target / "AI_CONTEXT.md").read_text(encoding="utf-8"), "Authored edit\n")
        self.assertFalse((self.target / ".ai_migration_backup").exists())
        self.run_install(behaviour="override")
        self.assertEqual((self.target / "AI_CONTEXT.md").read_bytes(), incoming.read_bytes())
        backups = self.target / ".ai_migration_backup"
        self.assertEqual(next(backups.rglob("AI_CONTEXT.md")).read_text(encoding="utf-8"), "Authored edit\n")
        self.assertEqual(next(backups.rglob("project_guide.md")).read_text(encoding="utf-8"), "Owner guide\n")
        self.assertEqual(unrelated.read_text(encoding="utf-8"), "Untouched\n")
        self.assertTrue(local.exists())

    def test_upgrade_without_ledger_preserves_unknown_files_and_adds_missing(self):
        self.export()
        self.target.mkdir()
        pointer = self.target / "AGENTS.md"
        pointer.write_text("Existing instructions\n", encoding="utf-8")
        plan = self.run_install(behaviour="upgrade")
        self.assertIn("AGENTS.md", plan["preserve_authored"])
        self.assertEqual(pointer.read_text(encoding="utf-8"), "Existing instructions\n")
        self.assertTrue((self.target / "AI_CONTEXT.md").exists())
        self.assertNotIn("AGENTS.md", json.loads((self.target / install.LEDGER).read_text())["files"])

    def test_default_install_and_explicit_override_without_template(self):
        self.command("install", self.target, "--user-config", self.user)
        guide = self.target / install.GUIDE
        guide.write_text("Owner guide\n", encoding="utf-8")
        self.command("install", self.target, "--user-config", self.user)
        self.assertEqual(guide.read_text(encoding="utf-8"), "Owner guide\n")
        self.command("install", self.target, "--user-config", self.user, "--behaviour", "override")
        self.assertNotEqual(guide.read_text(encoding="utf-8"), "Owner guide\n")
        self.assertEqual(
            next((self.target / ".ai_migration_backup").rglob("project_guide.md")).read_text(), "Owner guide\n"
        )

    def test_behaviour_cli_validation_and_conflicting_write_flags(self):
        parser = install.add_arguments(argparse.ArgumentParser())
        for flags in (("--behaviour", "unknown"), ("--dry-run", "--apply"), ("--behaviour", "preserve", "--upgrade")):
            with self.subTest(flags=flags), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    parser.parse_args([str(self.target), *flags])
        self.assertEqual(parser.parse_args([str(self.target)]).behaviour, "upgrade")
        self.assertTrue(parser.parse_args([str(self.target)]).apply)
        with self.assertRaisesRegex(RuntimeError, "cannot be combined"):
            self.run_install(template=None, behaviour="override", adopt=True)

    def test_fleet_behaviour_override_backs_up_each_target(self):
        self.export()
        self.target.mkdir()
        entries = [fleet.Entry(self.target, "open")]
        options = fleet.Options(user_config=self.user, template=self.source)
        fleet.apply(entries, options)
        (self.target / install.GUIDE).write_text("Local policy\n", encoding="utf-8")
        result = fleet.apply(entries, options._replace(behaviour="override"))
        self.assertEqual(result["failed"], [])
        self.assertEqual(result["repositories"][0]["behaviour"], "override")
        self.assertEqual(
            next((self.target / ".ai_migration_backup").rglob("project_guide.md")).read_text(), "Local policy\n"
        )

    def test_duplicate_traversal_and_unsupported_manifests_write_nothing(self):
        self.export()
        path = self.source / templates.MANIFEST
        baseline = json.loads(path.read_text(encoding="utf-8"))
        for name in ("../escape", "AI_CONTEXT.md", "ai_workflow/settings.local.json", "C:\\escape"):
            with self.subTest(name=name):
                data = dict(baseline, files=baseline["files"] + [name])
                path.write_text(json.dumps(data), encoding="utf-8")
                with self.assertRaises(templates.TemplateError):
                    self.run_install()
                self.assertFalse(self.target.exists())
        path.write_text('{"schema_version":"9.0", "files":[]}', encoding="utf-8")
        with self.assertRaisesRegex(templates.TemplateError, "Unsupported"):
            self.run_install()

    def test_unlisted_secret_file_and_embedded_token_are_refused(self):
        self.export()
        extra = self.source / "credentials.local.yaml"
        extra.write_text("local only\n", encoding="utf-8")
        with self.assertRaisesRegex(templates.TemplateError, "unlisted"):
            self.run_install()
        extra.unlink()
        self.edit_guide("Key: sk-" + "A" * 24 + "\n")
        with self.assertRaisesRegex(templates.TemplateError, "credential-shaped"):
            self.run_install()
        self.assertFalse(self.target.exists())

    def test_invalid_json_and_python_are_refused(self):
        self.export()
        for name, text in (("ai_workflow/bootstrap.json", "{"), ("ai_workflow/tools/settings.py", "def !")):
            path = self.source / name
            before = path.read_bytes()
            path.write_text(text, encoding="utf-8")
            with self.assertRaisesRegex(templates.TemplateError, "Invalid template content"):
                self.run_install()
            path.write_bytes(before)

    def test_custom_python_is_validated_but_never_executed_during_install(self):
        self.export()
        executed = self.base / "executed"
        (self.source / "ai_workflow/tools/settings.py").write_text(
            "from pathlib import Path\nPath(" + repr(str(executed)) + ").write_text('executed')\n",
            encoding="utf-8",
        )
        self.run_install()
        self.assertFalse(executed.exists())

    def test_unlisted_state_directories_are_refused_even_when_empty(self):
        self.export()
        (self.source / ".git").mkdir()
        with self.assertRaisesRegex(templates.TemplateError, "unsupported directory"):
            self.run_install()
        self.assertFalse(self.target.exists())

    def test_symlinks_and_overlapping_directories_are_refused(self):
        self.export()
        real = Path.is_symlink
        with patch.object(
            Path, "is_symlink", autospec=True, side_effect=lambda p: p == self.source / "AI_CONTEXT.md" or real(p)
        ):
            with self.assertRaisesRegex(templates.TemplateError, "symlinks"):
                self.run_install()
        with self.assertRaisesRegex(templates.TemplateError, "overlap"):
            self.run_install(repo=self.source / "target")
        with self.assertRaisesRegex(templates.TemplateError, "overlap"):
            templates.create(templates.RESOURCE_ROOT / "project/export")

    def test_source_mutation_after_planning_is_refused(self):
        self.export()
        resolve = install.resolve

        def mutate(*args, **kwargs):
            self.edit_guide("Changed during planning\n")
            return resolve(*args, **kwargs)

        with patch.object(install, "resolve", side_effect=mutate):
            with self.assertRaisesRegex(templates.TemplateError, "changed after"):
                self.run_install()
        self.assertFalse((self.target / "AI_CONTEXT.md").exists())
        self.assertFalse((self.target / install.LEDGER).exists())

    def test_fleet_policy_and_per_target_failure_remain_enforced(self):
        self.export()
        self.target.mkdir()
        owner = self.base / "owner"
        owner.mkdir()
        entries = [fleet.Entry(self.target, "open"), fleet.Entry(owner, "owner-only")]
        options = fleet.Options(apply=True, user_config=self.user, template=self.source)
        result = fleet.apply(entries, options)
        self.assertEqual(result["skipped_owner_only"], ["owner"])
        self.assertFalse((owner / "AI_CONTEXT.md").exists())
        (owner / "AI_CONTEXT.md").mkdir()
        result = fleet.apply(entries, options._replace(upgrade=True, include_owner_only=True))
        self.assertEqual([row["repository"] for row in result["failed"]], ["owner"])
        # A non-file collision is never overwritten, even without a ledger.
        self.assertEqual(result["skipped_owner_only"], [])
        self.assertTrue((owner / "AI_CONTEXT.md").is_dir())
        self.assertEqual(len(result["repositories"]), 1)

    def test_explicit_guide_replacement_rolls_back_on_write_failure(self):
        self.export()
        self.run_install()
        before = (self.target / install.GUIDE).read_bytes()
        self.edit_guide()
        copy = install_transaction.atomic_copy
        calls = 0

        def fail(source, target):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("Injected write failure")
            return copy(source, target)

        with patch.object(install_transaction, "atomic_copy", side_effect=fail):
            with self.assertRaisesRegex(OSError, "Injected"):
                self.run_install(behaviour="override")
        self.assertEqual((self.target / install.GUIDE).read_bytes(), before)

    def test_replace_guide_requires_template_and_cannot_adopt(self):
        self.export()
        with self.assertRaisesRegex(RuntimeError, "requires --template"):
            self.run_install(template=None, replace_guide=True)
        with self.assertRaisesRegex(RuntimeError, "cannot be combined"):
            self.run_install(replace_guide=True, adopt=True)
