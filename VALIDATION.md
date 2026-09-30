# Current validation

[CI.md](CI.md) owns check commands and [STATUS.md](STATUS.md) owns capabilities.
Use Git history for superseded evidence.

## Verified locally

2026-10-01, dev/mvp_0.30-consolidation, Linux/Python 3.12.12, Ruff 0.16.8:
`CBSETUP_PACKAGE_TESTS=1 .venv/bin/python scripts/check.py --full` passed with **217 unit/distribution tests
and 31 payload/bootstrap tests, zero failures and zero skips**. Formatting, lint, contracts and shared-standard
conformance passed. Static/editable builds and installs ran. Version check and check-pr report 1.1.0, matching main.
Remote/local tags and GitHub releases are absent; REPOSITORY_VERSIONING_ENABLED is false.
This supersedes the operational Spec Kit prerequisites below, which are historical evidence only.
The old 9224bf8 hosted run failed Windows and full integration; this port corrects the diagnosed paths and deleted
setup calls, but hosted qualification of the new branch is still required. No new PR, tag or release is created.

Tool-neutral agent guide, handover contract, `--no-speckit`, `--adopt`, automatic Spec Kit provisioning and the
R-B1/R-B2 fixes (branch `dev/neutral-guide`, 2026-09-29) on Linux/Python 3.12.12: unit profile
**188 tests (15 optional-tool skips) + 32 bootstrap tests pass**; `scripts/check.py` **GO**; ruff check/format clean;
opt-in packaging tests (`CBSETUP_PACKAGE_TESTS=1 tests.test_distribution`) 3/3 pass and the built wheel contains the
new payload files. Provisioning was exercised with mocked commands only; the strict full profile with real
`SPECIFY_BIN` and hosted CI have not run for this branch.

The CI dependency/evidence fixes passed the strict full gate on Linux/Python 3.13.14:
**165 tests, no skips, GO** (133 distribution tests and 32 consumer bootstrap tests).
Default and alternate Spec Kit integrations and actual static/editable package tests
were enabled. Log: `/tmp/rp-ci-evidence-full.log`.

**Historical, superseded 2026-09-30.** A fresh `pip install --dry-run --ignore-installed -e '.[dev,all]'` resolved
successfully: MCP 1.30.0, CodeGraphContext 0.6.13 and Kuzu 0.11.3. Resolver evidence is in
`/tmp/rp-compatible-dependencies.json`; this verified resolution, not installation of that entire fresh environment.
This record is kept because it happened, not because it still applies: the `cgc`, `sourcegraph` and `all` extras were
removed with those adapters, so `[dev,all]` no longer exists and `[dev]` is the only extra. There are no runtime
dependencies left to resolve.

Regression coverage checks uploadable NO-GO/test-not-run reports before dependency
setup, replacement after gate execution, and consistent optional dependency profiles.
Workflow linting, pin checks, shared conformance in all three repositories and patch
whitespace checks passed. The shared Dependabot policy excludes MCP >=2 until the
backend is compatible; its managed hashes were synchronized across all three repos.

## Hosted diagnosis and remaining scope

Run 34655522395 failed because its MCP 2.2.0 update conflicted with CodeGraphContext's
MCP <2 requirement. Installation stopped before the old workflow generated reports;
the artifact-upload failure was downstream. Unit tests separately failed an obsolete
literal MCP-version assertion. Expected negative-test GO=false output was not the cause.

These fixes require a fresh hosted run. Existing failed runs are not qualified by local
checks. No new hosted Windows/macOS run, actual artifact upload, public release, App
publication, Docker/Conda execution, production backend or live-agent validation is
claimed. No commits, pushes or releases were performed by this fix task.
