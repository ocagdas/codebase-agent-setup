# Current validation

[CI.md](CI.md) owns check commands and [STATUS.md](STATUS.md) owns capabilities.
Use Git history for superseded evidence.

## Verified locally

2026-10-01, dev/mvp_1.1.1 (renamed from dev/local-only-install), Linux/Python 3.12.12: strict
`CBSETUP_PACKAGE_TESTS=1 .venv/bin/python scripts/check.py --full` passed **248 distribution/unit + 31 payload
tests, no failures or skips**, including static/editable builds and installs. Ruff, contracts and shared conformance
passed; version and check-pr remain 1.1.0. New privacy regressions cover actual Git ignore behavior, preview-only
writes, preserved rules, idempotent upgrades, explicit CLI sharing and fleet override, and unchanged tracking.
Editable template coverage includes real CLI export/edit/single/fleet preview/apply, static-wheel and editable
installation flows, source mutation detection, supported inventory/secret-shape validation, no script execution,
author-owned guide preservation and explicit replacement with backup/rollback. Installed settings guide is 26 lines;
administration lives in CAS user docs. Seven local installations were refreshed with filled guides unchanged,
zero drift/missing files. Branch policy and whitespace checks passed. Clean tracked-files-only full gate also
passed without root AGENTS.md/AI_CONTEXT.md/ai_workflow/.cbsetup, with identical counts and no skips.
Latest logs: /tmp/cas-clean-checkout-full.log and /tmp/cas-clean-ci-fix-full.log.
Install, template creation and fleet now apply by default, with --dry-run previews. --behaviour defaults to upgrade;
preserve adds missing files, override backs up and replaces supported files including the guide. Tests cover all
modes, unknown unowned-file preservation, unrelated/local-settings preservation, rollback, invalid/conflicting CLI
flags and built-in override. Actual static/editable launchers exercise default writes; capsule/config controls are unchanged.
Owner published feature commit 3f69f66 and PR #13. Hosted push 36874131822 and PR 36874228527 failed because
distribution validation required the deliberately untracked root AGENTS.md. Clean testing additionally exposed
the same requirement in shared conformance and setup-document bundle drift. Both validators now check the tracked
project/AGENTS.md; the conformance adapter's optional agent_guide keeps existing root-guide behavior by default.
Shared setup text is restored to its checksum-pinned baseline; changed conformance/schema/readme hashes are updated.
Three regressions cover tracked-only validation, rejecting missing payload despite local guidance, and legacy
adapter defaults. The first two reproduced the pre-fix failure. This CI correction is local/uncommitted/unpushed;
fresh hosted qualification is still required. Installed root files remain ignored and untracked.

Prior MVP revision 4e3d4ea passed hosted run 36847221902: Linux Python 3.11/3.12/3.13, macOS 14/Python 3.13,
Windows/Python 3.13, analysis, distribution artifacts and strict Linux integration. MVP PR #12 is merged on main.

Historical MVP local evidence follows:

2026-10-01, dev/mvp_0.30, Linux/Python 3.12.12, Ruff 0.16.8:
`CBSETUP_PACKAGE_TESTS=1 .venv/bin/python scripts/check.py --full` passed with **217 unit/distribution tests
and 31 payload/bootstrap tests, zero failures and zero skips**. Formatting, lint, contracts and shared-standard
conformance passed. Static/editable builds and installs ran. Version check and check-pr report 1.1.0, matching main.
Remote/local tags and GitHub releases are absent; REPOSITORY_VERSIONING_ENABLED is false.
This supersedes the operational Spec Kit prerequisites below, which are historical evidence only.
The old 9224bf8 hosted run failed Windows and full integration; this port corrects the diagnosed paths and deleted
setup calls. Hosted run 36789363776 passed Linux/macOS, analysis, artifacts and full integration, but failed
Windows with six capsule errors: folder writes translated the bytes after hashing. Capsule files now use binary
UTF-8 writes, with a folder digest regression assertion. Hosted qualification subsequently passed as recorded above.
The redundant consolidation and two guide branches were backed up and removed; MVP PR #12 was merged by the owner.
No tag or release was created by this work.

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
