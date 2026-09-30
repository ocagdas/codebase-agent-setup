"""Handover contract validator; stdlib payload tool run inside consumer repositories."""

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "project/ai_workflow/tools"))
import validate_handover as vh

CANONICAL = """# Example — handover

**As of 2026-09-29.** Verified against `main` at `abc1234`.

## State
Clean.

## Open issues
None.

## Tests and evidence
71 passed.

## Risks
Low.

## Next actions
1. Ship.
"""


class ValidateTextTests(unittest.TestCase):
    def test_canonical_template_passes(self):
        result = vh.validate(CANONICAL)
        self.assertTrue(result["ok"])
        self.assertEqual(result["missing"], [])
        self.assertEqual(result["warnings"], [])
        self.assertEqual(result["as_of"], "2026-09-29")

    def test_missing_required_section_fails(self):
        result = vh.validate(CANONICAL.replace("## Next actions", "## Afterword"))
        self.assertFalse(result["ok"])
        self.assertEqual(result["missing"], ["Next actions"])

    def test_numbered_and_aliased_headings_pass(self):
        text = """# X

**As of 2026-09-29.** Verified.

## 1. State
## 4. Outstanding code and quality issues (all re-verified)
## 7. SWOT
## 8. Resuming work
"""
        result = vh.validate(text)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["warnings"], ["Tests and evidence"])

    def test_missing_recommended_sections_only_warn(self):
        text = CANONICAL.replace("## Tests and evidence", "## Misc").replace("## Risks", "## Other")
        result = vh.validate(text)
        self.assertTrue(result["ok"])
        self.assertEqual(result["warnings"], ["Tests and evidence", "Risks"])

    def test_as_of_must_be_near_the_top(self):
        text = CANONICAL.replace("**As of 2026-09-29.** Verified against `main` at `abc1234`.", "") + "\n" * 12
        text += "As of 2026-09-29\n"
        result = vh.validate(text)
        self.assertFalse(result["ok"])
        self.assertIn("As of date", result["missing"])
        self.assertIsNone(result["as_of"])

    def test_heading_text_inside_code_block_is_ignored(self):
        text = CANONICAL.replace("## Next actions\n1. Ship.\n", "```\n## Next actions\n```\n")
        self.assertEqual(vh.validate(text)["missing"], ["Next actions"])


class ValidateCommandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def run_main(self, *args):
        output = io.StringIO()
        with redirect_stdout(output):
            code = vh.main(list(args))
        return code, json.loads(output.getvalue())

    def test_missing_file_reports_and_fails(self):
        code, result = self.run_main(str(self.root / "absent.md"))
        self.assertEqual(code, 1)
        self.assertEqual(result["missing"], ["file"])

    def test_explicit_path_passes(self):
        path = self.root / "HANDOVER.md"
        path.write_text(CANONICAL, encoding="utf-8")
        code, result = self.run_main(str(path))
        self.assertEqual(code, 0)
        self.assertEqual(result["path"], str(path.resolve()))

    def test_repo_uses_configured_location(self):
        repo = self.root / "repo"
        (repo / "ai_workflow").mkdir(parents=True)
        (repo / "ai_workflow/settings.local.json").write_text(
            json.dumps({"schema_version": "1.0", "settings": {"handover": {"path": "../../HANDOVER.md"}}}),
            encoding="utf-8",
        )
        (self.root / "HANDOVER.md").write_text(CANONICAL, encoding="utf-8")
        code, result = self.run_main("--repo", str(repo), "--user-config", str(self.root / "none.json"))
        self.assertEqual(code, 0, result)
        self.assertEqual(result["path"], str((self.root / "HANDOVER.md").resolve()))


if __name__ == "__main__":
    unittest.main()
