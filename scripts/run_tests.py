"""Run both unittest suites and emit structured evidence; full mode rejects skips."""

import argparse
import json
import os
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def run(full=False):
    required = ("SPECIFY_BIN", "SPECIFY_ALTERNATE_BIN", "SPECIFY_ALTERNATE_RECORD")
    if full and (any(not os.environ.get(key) for key in required) or os.environ.get("CBSETUP_PACKAGE_TESTS") != "1"):
        raise ValueError(
            "Full tests require SPECIFY_BIN, SPECIFY_ALTERNATE_BIN, SPECIFY_ALTERNATE_RECORD and CBSETUP_PACKAGE_TESTS=1"
        )
    records = []
    for directory in (ROOT / "tests", ROOT / "project/ai_workflow/tools"):
        suite = unittest.TestLoader().discover(str(directory), pattern="test_*.py", top_level_dir=str(directory))
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        records.append(
            {
                "suite": str(directory.relative_to(ROOT)),
                "tests": result.testsRun,
                "failures": len(result.failures),
                "errors": len(result.errors),
                "unexpected_successes": len(result.unexpectedSuccesses),
                "skipped": [{"test": str(test), "reason": reason} for test, reason in result.skipped],
                "passed": result.wasSuccessful() and result.testsRun > 0 and (not full or not result.skipped),
            }
        )
    return {
        "schema_version": "1.0",
        "profile": "full" if full else "unit",
        "passed": all(item["passed"] for item in records),
        "suites": records,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--report", type=Path, default=ROOT / ".quality/tests.json")
    args = parser.parse_args(argv)
    try:
        report = run(args.full)
    except Exception as error:
        report = {"schema_version": "1.0", "passed": False, "error": str(error)}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
