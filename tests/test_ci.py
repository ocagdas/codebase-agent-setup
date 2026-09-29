"""Quality gates must fail closed and release manifests must cover exact artifacts."""

import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import check, run_tests, validate_project


class QualityGateTests(unittest.TestCase):
    def test_setup_failure_has_uploadable_no_go_evidence(self):
        import yaml

        workflow = yaml.load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
        steps = workflow["jobs"]["integration"]["steps"]
        initializer = next(i for i, step in enumerate(steps) if "initialize_reports" in step.get("run", ""))
        install = next(i for i, step in enumerate(steps) if "pip install" in step.get("run", ""))
        self.assertLess(initializer, install)
        upload = next(step for step in steps if step.get("uses", "").startswith("actions/upload-artifact@"))
        self.assertEqual(upload["if"], "always()")
        self.assertEqual(upload["with"]["include-hidden-files"], "true")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "gate.json").write_text('{"go": true}', encoding="utf-8")
            check.initialize_reports(directory)
            gate = json.loads((directory / "gate.json").read_text(encoding="utf-8"))
            tests = json.loads((directory / "tests.json").read_text(encoding="utf-8"))
            self.assertIs(gate["go"], False)
            self.assertIs(tests["passed"], False)
            self.assertEqual(gate["checks"], [])
            self.assertEqual(tests["suites"], [])
            # Successful execution replaces setup placeholders, not merely the GO flag.
            with patch.object(check.subprocess, "run", return_value=SimpleNamespace(returncode=0)):
                self.assertEqual(check.main(["--full", "--report", str(directory / "gate.json")]), 0)
            self.assertNotIn("error", json.loads((directory / "gate.json").read_text(encoding="utf-8")))

    def test_local_gate_overwrites_stale_go_and_stops_on_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary) / "gate.json"
            report.write_text('{"go": true}', encoding="utf-8")
            with (
                patch.object(check.subprocess, "run", return_value=SimpleNamespace(returncode=1)) as command,
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(check.main(["--report", str(report)]), 1)
            self.assertFalse(json.loads(report.read_text(encoding="utf-8"))["go"])
            self.assertEqual(command.call_count, 1)

    def test_full_test_profile_rejects_missing_prerequisites_and_writes_evidence(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {}, clear=True):
            report = Path(temporary) / "tests.json"
            self.assertEqual(run_tests.main(["--full", "--report", str(report)]), 1)
            result = json.loads(report.read_text(encoding="utf-8"))
            self.assertFalse(result["passed"])
            self.assertIn("SPECIFY_BIN", result["error"])

    def test_full_test_profile_rejects_skips_unit_profile_discloses_them(self):
        class Skipped(unittest.TestCase):
            @unittest.skip("fixture unavailable")
            def test_fixture(self):
                pass

        def suite(*args, **kwargs):
            return unittest.TestSuite([Skipped("test_fixture")])

        environment = {key: "fixture" for key in ("SPECIFY_BIN", "SPECIFY_ALTERNATE_BIN", "SPECIFY_ALTERNATE_RECORD")}
        environment["CBSETUP_PACKAGE_TESTS"] = "1"
        with (
            patch.dict(os.environ, environment),
            patch.object(unittest.TestLoader, "discover", side_effect=suite),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            self.assertTrue(run_tests.run(full=False)["passed"])
            report = run_tests.run(full=True)
        self.assertFalse(report["passed"])
        self.assertEqual(report["suites"][0]["skipped"][0]["reason"], "fixture unavailable")

    def test_distribution_contracts_and_license_metadata(self):
        validate_project.validate()

    def test_required_gate_and_release_dependency_are_present(self):
        import yaml

        workflow = yaml.load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
        gate = workflow["jobs"]["quality-gate"]
        self.assertEqual(set(gate["needs"]), {"quality", "unit", "integration", "artifacts"})
        self.assertEqual(gate["if"], "always()")
        self.assertIn("merge_group", workflow["on"])
        self.assertIn("workflow_call", workflow["on"])
        release = yaml.load(
            (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8"), Loader=yaml.BaseLoader
        )
        self.assertEqual(release["jobs"]["release-candidate"]["needs"], "checks")
        self.assertIn("outputs.go == 'true'", release["jobs"]["release-candidate"]["if"])


class WorkflowPinTests(unittest.TestCase):
    def test_inconsistent_or_unpinned_actions_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workflows = root / ".github/workflows"
            workflows.mkdir(parents=True)
            (workflows / "ci.yml").write_text(
                "jobs:\n  test:\n    steps:\n      - uses: actions/checkout@" + "a" * 40 + " # v5.0.0\n",
                encoding="utf-8",
            )
            other = workflows / "verify-release.yml"
            for reference in ("b" * 40 + " # v5.0.0", "a" * 40 + " # v4.0.0", "v5", "a" * 40 + " # v5"):
                with self.subTest(reference=reference):
                    other.write_text(
                        "jobs:\n  test:\n    steps:\n      - uses: actions/checkout@" + reference + "\n",
                        encoding="utf-8",
                    )
                    with self.assertRaises(ValueError):
                        validate_project.validate_workflow_pins(root)
            other.write_text(
                "jobs:\n  test:\n    steps:\n      - uses: actions/checkout@" + "a" * 40 + " # v5.0.0\n",
                encoding="utf-8",
            )
            validate_project.validate_workflow_pins(root)
