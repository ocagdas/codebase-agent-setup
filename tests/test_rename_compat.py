"""Compatibility with state written before the repo_pilot -> codebase-agent-setup rename."""

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from codebase_agent_setup import toolchains
from project.ai_workflow.tools import knowledge_backend as kb
from project.ai_workflow.tools import settings


class UserConfigLocation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        home = Path(self.temp.name)
        # Cover the Windows, macOS and XDG branches of user_file() alike.
        patches = [
            patch.dict(os.environ, {"APPDATA": str(home), "XDG_CONFIG_HOME": str(home)}),
            patch.object(settings.Path, "home", return_value=home),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    def test_new_location_is_default(self):
        self.assertEqual(settings.user_file().parent.name, "codebase-agent-setup")

    def test_legacy_location_is_used_until_migrated(self):
        new = settings.user_file()
        legacy = new.parent.parent / "repo-pilot/config.json"
        legacy.parent.mkdir(parents=True)
        legacy.write_text("{}", encoding="utf-8")
        self.assertEqual(settings.user_file(), legacy)
        new.parent.mkdir(parents=True)
        new.write_text("{}", encoding="utf-8")
        self.assertEqual(settings.user_file(), new)


class KnowledgeStateMarker(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name)
        self.value = {"repo": "r", "repository_id": "id", "revision": "abc"}

    def test_legacy_marker_is_read(self):
        (self.data / kb.LEGACY_STATE_FILE).write_text(json.dumps(self.value), encoding="utf-8")
        self.assertEqual(kb.state({"data_dir": str(self.data)}), self.value)

    def test_current_marker_wins_over_legacy(self):
        (self.data / kb.LEGACY_STATE_FILE).write_text(json.dumps(self.value | {"revision": "old"}), encoding="utf-8")
        (self.data / kb.STATE_FILE).write_text(json.dumps(self.value), encoding="utf-8")
        self.assertEqual(kb.state({"data_dir": str(self.data)})["revision"], "abc")


class TimeoutVariables(unittest.TestCase):
    def test_legacy_timeout_variable_is_accepted(self):
        with patch.dict(os.environ, {"REPO_PILOT_PROBE_TIMEOUT": "7"}, clear=False):
            os.environ.pop("CBSETUP_PROBE_TIMEOUT", None)
            self.assertEqual(toolchains.command_timeout("probe"), 7.0)

    def test_new_timeout_variable_takes_precedence(self):
        with patch.dict(os.environ, {"REPO_PILOT_PROBE_TIMEOUT": "7", "CBSETUP_PROBE_TIMEOUT": "3"}):
            self.assertEqual(toolchains.command_timeout("probe"), 3.0)


if __name__ == "__main__":
    unittest.main()
