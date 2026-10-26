"""Exact tool mappings and user manuals must survive installation and overrides."""

import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from codebase_agent_setup import capsule, fleet, install, tool_catalog
import test_templates


class ManualTests(unittest.TestCase):
    setUp = test_templates.TemplateTests.setUp
    export = test_templates.TemplateTests.export
    run_install = test_templates.TemplateTests.run_install

    def test_catalog_and_entry_pointers_match(self):
        root = install.ROOT / "project"
        guide = (root / "AI_CONTEXT.md").read_text(encoding="utf-8")
        self.assertIn("ai_workflow/tool_registry.json", guide)
        for tool, entry in tool_catalog.catalog()["tools"].items():
            pointer = (root / entry["entry_file"]).read_text(encoding="utf-8")
            self.assertIn("AI_CONTEXT.md", pointer, tool)
            self.assertNotIn(entry["manual_file"], pointer, tool)
            self.assertTrue((root / entry["manual_file"]).is_file(), tool)
            self.assertIn(entry["manual_file"], capsule.REPO_FILES)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(tool_catalog.main(["list", "--json"]), 0)
        self.assertEqual(
            set(json.loads(output.getvalue())["tools"]), {"codex", "claude", "copilot", "cursor", "gemini"}
        )

    def test_user_manuals_survive_every_behaviour_and_obsolete_cleanup(self):
        self.export()
        self.run_install(behaviour="upgrade")
        originals = {}
        for name in install.USER_MANUALS:
            content = f"# Authored {name}\r\nKeep this byte-for-byte.\r\n".encode()
            (self.target / name).write_bytes(content)
            originals[name] = content
        for behaviour in ("preserve", "upgrade", "override"):
            plan = self.run_install(behaviour=behaviour)
            self.assertTrue(install.USER_MANUALS.issubset(plan["keep_existing"]))
            for name, content in originals.items():
                self.assertEqual((self.target / name).read_bytes(), content)
        self.run_install(behaviour="upgrade", remove_obsolete=True)
        ledger = json.loads((self.target / install.LEDGER).read_text(encoding="utf-8"))
        self.assertFalse(install.USER_MANUALS.intersection(ledger["files"]))
        for name, content in originals.items():
            self.assertEqual((self.target / name).read_bytes(), content)

    def test_manuals_are_ignored_and_missing_ones_are_reseeded(self):
        self.export()
        self.run_install(behaviour="upgrade")
        subprocess.run(["git", "init", "-q", str(self.target)], check=True)
        for name in install.USER_MANUALS:
            result = subprocess.run(["git", "-C", str(self.target), "check-ignore", name], capture_output=True)
            self.assertEqual(result.returncode, 0)
        name = sorted(install.USER_MANUALS)[0]
        (self.target / name).unlink()
        self.run_install(behaviour="override")
        self.assertTrue((self.target / name).is_file())

    def test_manuals_are_captured_and_restored_in_setup_capsules(self):
        self.export()
        self.run_install(behaviour="upgrade")
        name = "ai_workflow/tools/codex_manual.md"
        (self.target / name).write_text("# Local custom instructions\n", encoding="utf-8")
        home = self.base / "empty-home"
        home.mkdir()
        result = capsule.create(capsule.Request(home=home, repos=(self.target,), out_dir=self.base / "capsule"))
        clone = self.base / "clone"
        capsule.apply(result.location, capsule.Target(home=home, repo=clone, apply=True))
        self.assertEqual((clone / name).read_bytes(), (self.target / name).read_bytes())

    def test_fleet_override_preserves_each_targets_manual(self):
        self.export()
        other = self.base / "other"
        self.target.mkdir()
        other.mkdir()
        entries = [fleet.Entry(self.target, "open"), fleet.Entry(other, "open")]
        options = fleet.Options(user_config=self.user, template=self.source)
        self.assertEqual(fleet.apply(entries, options)["failed"], [])
        manual = "ai_workflow/tools/cursor_manual.md"
        for index, target in enumerate((self.target, other)):
            (target / manual).write_text(f"Local instructions {index}\n", encoding="utf-8")
        self.assertEqual(fleet.apply(entries, options._replace(behaviour="override"))["failed"], [])
        for index, target in enumerate((self.target, other)):
            self.assertEqual((target / manual).read_text(encoding="utf-8"), f"Local instructions {index}\n")


if __name__ == "__main__":
    unittest.main()
