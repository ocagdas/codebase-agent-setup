# Current validation

## Correctness audit — 2026-10-17

Capsule regressions cover filled project-guide restoration, parent symlink refusal, duplicate repo names, ambiguous multi-repo mapping and preservation of existing destination guides. `CBSETUP_PACKAGE_TESTS=1 python scripts/check.py --full` passed: **206 distribution tests + 31 payload tests, zero skips**, Ruff formatting/lint, contracts, conformance and real static/editable package installation. Log: `/tmp/toolbox-cas-gate-20261017.log`. No live-client or machine-to-machine environment recovery is established.

[CI.md](CI.md) owns check commands and [STATUS.md](STATUS.md) owns capabilities.
Use Git history for superseded evidence.

## Ignore-file control — 2026-10-16

`cbsetup install` and `cbsetup fleet apply` now accept `--no-gitignore` to install
guidance and keep the ledger while leaving `.gitignore` untouched. The default
ignore behavior and `--track-guidance` retain their previous meanings. New tests
cover an absent ignore file, byte-preserved existing rules, CLI use and fleet use.
Focused install/fleet suites passed (25 + 19 tests). The distribution suite passed
(201 tests, one optional packaging skip), as did the payload suite (31 tests).
`git diff --check` passed. Ruff and the strict package gate were not run in this
environment; no hosted or live-client qualification is claimed.

## Pointer simplification — 2026-10-16

The five entry templates now refer only to `AI_CONTEXT.md`; that guide selects the
active tool's manual from `ai_workflow/tool_registry.json`. The catalog test verifies
the mapping, shipped manuals and shared-guide pointers without requiring duplicate
manual paths in each pointer. Focused manual tests passed (5 tests), payload tests
passed (31), and distribution tests passed (198, one optional packaging skip).
CAS upgrade applied the pointers at the workspace root and
all five checkouts, preserving local guides and manuals; a repeat CAS preview showed
no replacements. A fresh CAS install in a disposable directory produced byte-identical
copies of all five tracked entry templates and included the Codex registry mapping.
No live-client behavior or hosted platform is claimed.

## Current extraction/manual delta — 2026-10-05

Local dev/mvp_1.1.2 at 1e52bca, version unchanged at 1.1.1, with an uncommitted
Codebase Index Kit extraction and tool-manual delta. Strict Linux/Python 3.12 gate passed
197 distribution/unit + 31 payload tests, zero failures/errors/skips, including actual
static/editable installations, Ruff, contracts and shared repository conformance.
Log: /tmp/cas-extraction-full-check.log. These new counts exclude the moved engine tests.

New checks cover exact catalog/entry/manual mappings, byte-preserved user manuals in
preserve/upgrade/override, missing-manual reseeding, ignore rules, fleet override and
setup capsule capture/restore. Optional bridges refuse missing/incompatible contracts,
preserve literal arguments/exit codes, and hand legacy resolved settings through stdin.
CAS wheels include all manuals/catalog and no longer contain the Aider worker.

The separate Codebase Index Kit suite passed 75 tests with no skips, including actual
static/editable installations, independent execution after source relocation, direct
and standalone-payload CAS bridges, and real Aider 0.86.2 synthetic map generation,
current show/status and warm reuse. That companion evidence does not qualify new CAS
semantic indexing. No existing target source/build/install/cache changed, no cloud-agent
trial or hosted platform CI, and no commit/PR/push/tag/remote creation. Bootstrap helper
ownership remains a deliberate pending audit. Prior hosted evidence below is historical.

## Current hosted qualification (2026-10-01)

Owner-published 76aa042 passed push/PR runs 36878525386 and 36878524906, including Windows/Python 3.13,
macOS/Python 3.13, Linux/Python 3.11/3.12/3.13, formatting/analysis, strict integration, artifacts and Quality gate.
PR #13 merged at f8f2d4d; main run 36879174228 passed the same checks. Its version job initially lacked App
configuration, then succeeded on rerun after owner setup. The atomic publisher created main commit 1cf8650
and tag v1.1.1, matching pyproject.toml version 1.1.1. Version-commit CI 36903055110 and Release readiness
36903055469 both passed. This proves hosted Windows corrections and App publication,
not live-agent behavior, a real semantic backend, failing-PR protection enforcement or public publication.
Local editable metadata was rebuilt using isolated build dependencies and cbsetup --version reports 1.1.1.

Initial private C++ repository pilot: dry run and default upgrade installation succeeded. Repeat preview showed
no replacements or ignore additions and preserved the filled guide. Read-only fleet status reports 22 managed
files, zero drift/missing and a filled guide. All 26 installed/local pilot paths are ignored and untracked.
Fingerprints of 2,272 existing files and the Git index are unchanged, except the intended .gitignore additions;
existing dirty/untracked product work is preserved. Both configured handovers validate without warnings.
No product build, real semantic index, live cloud agent or remote publication ran. The initial no-build-isolation
metadata refresh lacked setuptools; the normal isolated editable rebuild succeeded. Private paths/details remain
outside this public repository.

## Verified locally

### External Aider maps (2026-10-02)

A later private full-src pilot selected 1,874 UTF-8 files (one binary/non-UTF-8 exclusion).
Fresh generation took 116.71 s; unchanged reuse 1.14 s. Map text was 3,164,605 bytes,
87,642 lines; two-snapshot folder 7,008,476 apparent bytes; peak process RSS 723.94 MiB.
Eight map-first investigations were then checked against current source. Useful candidate
locations were found, but callback timing, config semantics, actual test coverage and
build dependencies required source. Filename coverage is not semantic completeness.
This session read excerpts at owner request; it was not a separate hosted-client pilot.
Target Git diff/status/index hashes remained unchanged. No product build/tests, Clang
invocation, binary/object inspection or execution ran. One local compilation database
referenced existing source paths; another did not, and semantic build context remains
unvalidated. No controlled source-only/token-saving measurement or two-PC transfer result.
Detailed private reports/logs are preserved outside this public repository in workspace
handover docs; /tmp paths below are transient. This parking pass changes documentation
only and does not rerun or extend the recorded full-gate qualification.

Local branch dev/aider-repo-maps adds an optional external Aider adapter; package version remains 1.1.1.
Ten new map regressions pass: privacy/unchanged reuse/stale deletion, scopes/ignored files, dry runs, tracked-cache
refusal, redacted export, matching-clone restore, tampering/source mismatch, budget changes and missing dependency.
Real Aider 0.86.2 in a separate temporary Python 3.12 environment generated C++/Python fixture maps with Python
socket connections disabled. Warm reuse, export/restore and transfer to another checkout passed. Actual static
and editable package-install checks verify the new command/help and worker files without installing Aider into CAS.
A bounded private consumer pilot produced a current 290-file structural map, preserved product Git diff/status/index
hashes, and verified warm reuse plus ignored/untracked output and guidance. No private artifact export, cloud model,
product build, remote CI, commit or push ran. Both pilot and workspace handovers validate without warnings.
The first strict attempt exposed new untracked product docs absent from the tracked-only snapshot fixture; new
product files are now intent-to-add (no staged content/commit). Scope-wide regeneration is not delta caching;
compiler accuracy, live agent compliance and token savings remain unqualified. See docs/user/repo-map.md.
Final strict gate passes 258 distribution/unit plus 31 payload tests with zero failures, errors or skips,
including static/editable installs, formatting, lint, contracts and shared conformance. Log:
/tmp/cas-aider-full-check-final.log. Local Linux evidence does not establish external Aider on Windows/macOS.

### Earlier local qualification

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
Clean-validator logs: /tmp/cas-clean-checkout-full.log and /tmp/cas-clean-ci-fix-full.log.
Latest strict Linux gate, including the Windows-sensitive privacy test correction, passed the same 248 + 31
tests with no skips; log /tmp/cas-windows-privacy-full.log. Git ignore tests use binary NUL-delimited paths;
authored-rule checks read newline-normalized text while idempotence still compares bytes, and CRLF input is tested
on every platform. These corrected tests passed hosted Windows at 76aa042; no local Windows execution is claimed.
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
adapter defaults. The first two reproduced the pre-fix failure. Owner published that correction as 3105dac;
hosted run 36875946056 passed Linux 3.11/3.12/3.13, macOS, formatting, full integration and artifacts, but failed
the two Windows privacy assertions above. Their correction was published as 76aa042 and subsequently passed.
Current source was applied with override to all four primary checkouts using per-repo editable templates retaining
their filled guides. Each has 22 managed files plus guide/ledger, all 24 ignored and none tracked; source hashes,
guides, local settings and existing Git changes were verified unchanged. The pre-existing source-only utility test
remains current and retained (editable exports exclude tests). Old migration worktrees and product suites were untouched.

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

The historical failures above are superseded by the current hosted qualification section, not by local checks.
Docker/Conda execution, production backend and live-agent validation remain unproven. Public publication remains
disabled. The owner published/merged fixes and configured the App; this documentation/pilot task did not commit,
push or change hosted settings.
