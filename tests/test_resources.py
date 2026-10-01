"""Source/wheel identification must not follow an unrelated consumer project."""

import sys
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from codebase_agent_setup.resources import resource_root


class ResourceTests(unittest.TestCase):
    def test_bundled_resources_win_over_consumer_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            package = root / "src/codebase_agent_setup"
            package.mkdir(parents=True)
            (package / "project").mkdir()
            (package / "project/AI_CONTEXT.md").write_text("#", encoding="utf-8")
            (root / "pyproject.toml").write_text('[project]\nname="codebase-agent-setup"\n', encoding="utf-8")
            self.assertEqual(resource_root(package), package)

    def test_source_detection_requires_project_identity_and_payload(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            package = root / "src/codebase_agent_setup"
            package.mkdir(parents=True)
            settings = root / "project/ai_workflow/tools/settings.py"
            settings.parent.mkdir(parents=True)
            settings.touch()
            project = root / "pyproject.toml"
            for text in ('[project]\nname="consumer"\n', "broken = ["):
                project.write_text(text, encoding="utf-8")
                with self.assertRaisesRegex(RuntimeError, "resource payload is missing"):
                    resource_root(package)
            project.write_text('[project]\nname="codebase-agent-setup"\n', encoding="utf-8")
            self.assertEqual(resource_root(package), root)
