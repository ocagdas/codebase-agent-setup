"""CAS delegates only to an installed compatible tool, without sibling imports."""

import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from codebase_agent_setup import repo_map
from codebase_agent_setup.project.ai_workflow.tools import knowledge


class BridgeTests(unittest.TestCase):
    def test_missing_tool_is_actionable_and_never_runs_anything(self):
        with (
            patch.object(knowledge.shutil, "which", return_value=None),
            patch.object(knowledge.subprocess, "run") as run,
        ):
            with contextlib.redirect_stderr(io.StringIO()) as output:
                self.assertEqual(repo_map.main(["status"]), 2)
            self.assertIn("never downloads", output.getvalue())
            run.assert_not_called()

    def test_contract_and_literal_arguments_and_exit_code(self):
        capabilities = {"contract_version": 1, "commands": ["repo-map", "knowledge"], "settings_stdin": True}
        results = [subprocess.CompletedProcess([], 0, json.dumps(capabilities), ""), subprocess.CompletedProcess([], 7)]
        with (
            patch.object(knowledge.shutil, "which", return_value="/tool path/cbkit"),
            patch.object(knowledge.subprocess, "run", side_effect=results) as run,
        ):
            self.assertEqual(repo_map.main(["show", "--repo", "literal;$(path)"]), 7)
        self.assertEqual(
            run.call_args_list[1].args[0], ["/tool path/cbkit", "repo-map", "show", "--repo", "literal;$(path)"]
        )
        self.assertNotIn("shell", run.call_args_list[1].kwargs)

    def test_discovery_uses_cbkit_only(self):
        with (
            patch.object(knowledge.shutil, "which", return_value=None) as which,
            contextlib.redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(knowledge.delegate("knowledge", ["status"]), 2)
        which.assert_called_once_with("cbkit")

    def test_incompatible_contract_refuses_before_operation(self):
        for contract in (2, True, "1"):
            with (
                patch.object(knowledge.shutil, "which", return_value="cbkit"),
                patch.object(
                    knowledge.subprocess,
                    "run",
                    return_value=subprocess.CompletedProcess([], 0, json.dumps({"contract_version": contract}), ""),
                ) as run,
                contextlib.redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(knowledge.delegate("knowledge", ["status"]), 2)
                self.assertEqual(run.call_count, 1)

    def test_legacy_settings_are_private_stdin_and_query_arguments_stay_literal(self):
        from codebase_agent_setup.project.ai_workflow.tools import settings

        with (
            patch.object(settings, "resolve", return_value={"settings": {"knowledge": {"indexers": []}}}),
            patch.object(knowledge, "delegate", return_value=0) as delegate,
        ):
            self.assertEqual(knowledge.main(["query", "--repo", "/target", "--", "--repo", "literal"]), 0)
        command, arguments, effective = delegate.call_args.args
        self.assertEqual(command, "knowledge")
        self.assertEqual(arguments, ["--repo", "/target", "query", "--", "--repo", "literal"])
        self.assertEqual(effective, {"indexers": []})

    def test_help_works_without_companion(self):
        with patch.object(knowledge.shutil, "which", return_value=None), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(repo_map.main(["--help"]), 0)
            with self.assertRaises(SystemExit) as result:
                knowledge.main(["--help"])
            self.assertEqual(result.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
