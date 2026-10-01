"""Consumer payload content: one tool-neutral guide, thin pointers, stdlib-only tools."""

import ast
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "project"
POINTERS = ("AGENTS.md", "CLAUDE.md", "GEMINI.md", ".github/copilot-instructions.md", ".cursor/rules/engineering.mdc")


class PayloadTests(unittest.TestCase):
    def read(self, relative):
        return (PROJECT / relative).read_text(encoding="utf-8")

    def test_every_tool_pointer_leads_to_the_neutral_guide(self):
        for relative in POINTERS:
            with self.subTest(relative):
                self.assertIn("AI_CONTEXT.md", self.read(relative))

    def test_neutral_guide_states_the_loading_order(self):
        text = self.read("AI_CONTEXT.md")
        for required in (
            "ai_workflow/project_guide.md",
            "ai_workflow/tools/settings.py handover",
            "ai_workflow/tools/validate_handover.py",
            ".specify/",
            "ai_workflow/handover.md",
        ):
            with self.subTest(required):
                self.assertIn(required, text)

    def test_neutral_guide_leaves_the_spec_kit_workflow_to_spec_kit(self):
        """CAS no longer ships or manages Spec Kit; the guide may point at it but must not describe it."""
        text = self.read("AI_CONTEXT.md")
        for detail in ("SPECIFY_FEATURE_DIRECTORY", "tasks.md", "completion.json", "speckit_workflow.md"):
            with self.subTest(detail):
                self.assertNotIn(detail, text)

    def test_neutral_guide_references_only_files_the_installer_ships(self):
        for relative in re.findall(r"`(ai_workflow/[^`\s]+)", self.read("AI_CONTEXT.md")):
            with self.subTest(relative):
                self.assertTrue((PROJECT / relative).is_file())

    def test_neutral_guide_names_no_single_vendor_as_the_audience(self):
        text = self.read("AI_CONTEXT.md").lower()
        for vendor in ("claude", "codex", "copilot", "cursor", "gemini"):
            self.assertNotIn(vendor, text)

    def test_project_guide_template_is_marked_unfilled(self):
        text = self.read("ai_workflow/project_guide.md")
        self.assertIn("<!-- cbsetup:unfilled -->", text)
        self.assertNotIn("CUSTOMISE", text)

    def test_handover_contract_lists_required_sections(self):
        sys.path.insert(0, str(PROJECT / "ai_workflow/tools"))
        import validate_handover

        text = self.read("ai_workflow/handover.md")
        for name in [*validate_handover.REQUIRED, *validate_handover.RECOMMENDED]:
            self.assertIn(name, text)

    def test_payload_tools_import_only_the_standard_library(self):
        local = {path.stem for path in (PROJECT / "ai_workflow/tools").glob("*.py")}
        allowed = set(sys.stdlib_module_names) | local | {"__future__"}
        # Optional adapters imported lazily inside functions are permitted third-party imports.
        optional = {"mcp", "codegraphcontext", "kuzu"}
        for path in sorted((PROJECT / "ai_workflow/tools").glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in tree.body:
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    names = [node.module]
                for name in names:
                    with self.subTest(path=path.name, module=name):
                        self.assertIn(name.split(".")[0], allowed - optional)


if __name__ == "__main__":
    unittest.main()
