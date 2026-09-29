# Maintaining the tooling package

Install the development tools with `python -m pip install -e '.[dev]'`. Set up official Spec Kit using INSTALLATION.md, then run the bootstrap and package tests. SPECIFY_BIN should identify the CLI in the chosen environment.

Linux or macOS with the default venv:

```bash
SPECIFY_BIN="$PWD/.venv/bin/specify" python3 -m unittest discover -s tests -v
python3 -m unittest discover -s project/ai_workflow/tools -p 'test_*.py'
```

Windows PowerShell:

```powershell
$env:SPECIFY_BIN = "$PWD\.venv\Scripts\specify.exe"
$env:PYTHONUTF8 = "1"
py -3 -m unittest discover -s tests -v
py -3 -m unittest discover -s project/ai_workflow/tools -p "test_*.py"
```

Without SPECIFY_BIN the installation tests skip deliberately; report that omission. Test modified environment modes with actual tools before marking them verified. Keep CI and local evidence distinct.

Runtime code lives in `src/codebase_agent_setup/`; see [architecture](docs/architecture.md) for
source/editable resource handling and wheel assembly. Root install/configure/knowledge
commands are launchers. Edit `project/`, `preset/` and `extension/` at their authored
paths; do not copy them into src.

The preset composes with upstream templates and commands. The extension supplies additional procedures. Companion project files supply policy, configuration and local utilities. Avoid maintaining a second specification or task ledger alongside Spec Kit.

Runtime modules intentionally remain at repository root and are packaged through pyproject mappings. Do not migrate to a `src/` layout unless a coordinated packaging/runtime migration is explicitly planned and validated.

Before a release, update STATUS.md and VALIDATION.md. Follow [VERSIONING.md](VERSIONING.md): ordinary PRs leave the package version unchanged; CI synchronizes pyproject.toml and upstream.lock.json after eligible merges. Maintainers use scripts/version.py for explicit version increases. A change to the official CLI pin must also update requirements.txt and manifest compatibility constraints. No upstream fork is maintained.

## Version override regression tests

The optional live version tests need both the pinned CLI and an alternate CLI plus its exported source record. They skip explicitly when these are absent. Use the paths produced by setup_tooling.py:

```bash
SPECIFY_BIN=/path/to/default/bin/specify \
SPECIFY_ALTERNATE_BIN=/path/to/alternate/bin/specify \
SPECIFY_ALTERNATE_RECORD=/path/to/alternate-record.json \
python3 -m unittest discover -s tests -v
```

In PowerShell set the same three environment variables before using the selected Python interpreter to run unittest. Do not infer cross-platform support from a Linux run. Alternate manifests are adapted only in disposable staging; the committed pin and manifest constraints remain the distribution baseline.

## Optional backend checks

Install requirements-knowledge.txt in a disposable environment and run tests/test_knowledge.py through unittest discovery. Without MCP, the Sourcegraph protocol test skips explicitly; it uses a fixture, not a production Sourcegraph instance. For real CGC validation, follow the index/export/import/query sequence in project/ai_workflow/knowledge_backends.md on two disposable clean clones and verify returned paths exist in the receiving clone. Do not infer cross-machine or large-codebase results from that check.

## Installed distribution checks

Set `CBSETUP_PACKAGE_TESTS=1` to include actual static/editable pip installations in the unittest suite. These build in disposable environments and may need network access for the build backend. With SPECIFY_BIN set, the packaging test also exercises a static installed launcher after its source checkout is moved, then verifies consumer installation and preservation on upgrade. Keep pyproject.toml's version consistent with upstream.lock.json and its optional dependency profiles consistent with requirements-knowledge.txt. Hidden integration payload files must remain present in wheels.

## Baseline and CI status

Repository regression CI and release-readiness workflows are included; see CI.md for local commands, strict integration prerequisites and branch-protection setup. Knowledge-artifact publication remains separate future work. A pushed commit is not evidence that remote tests ran.

Before recording a baseline, reconcile ROADMAP.md and TODO.md with the code, label partial deliveries, and distinguish historical validation from the current run. Include the optional packaging and alternate-version checks when validating those parts of a pending change, and report every skip. Keep claims about generated integration files separate from live agent results.

## Contributor quickstart and quality gate

Read [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) and [SUPPORT.md](SUPPORT.md). Discuss significant behavior or architecture changes in an issue before starting; focused bug fixes and documentation improvements can go directly to a pull request. Include a minimal reproducer, explain the resulting behavior, and keep unrelated changes separate.

```bash
python -m venv .venv-dev
# Activate .venv-dev using your shell, then:
python -m pip install -e '.[dev]'
python -m ruff format .
python scripts/check.py
```

Use the current interpreter for child Python commands and UTF-8 for text files. Unit checks disclose optional integration skips; the strict full gate rejects skips. Follow [CI.md](CI.md) to prepare full integration checks, build release candidates, read JSON gate results and configure protected branches. Fix the cause of a failed gate rather than changing the gate to ignore it.

By submitting a contribution, you confirm that you have the right to contribute it under this repository's MIT license. Preserve applicable third-party notices. No separate CLA is currently required. Do not include proprietary code, private graph data or credentials in fixtures. Report vulnerabilities through [SECURITY.md](SECURITY.md), not public issues.

Describe user-visible changes in the PR and update the owning STATUS/VALIDATION documents. There is no parallel manual changelog; future release notes should derive from tested release evidence. The default review owner is listed in `.github/CODEOWNERS`; GitHub only enforces owner review when an administrator enables that branch rule. Version changes are intentional release work, not automatic side effects of a contribution.

Follow [BRANCHING.md](BRANCHING.md) for the shared trunk/dev branch convention,
version/tag rules and REPOSITORY_VERSIONING_ENABLED activation setting.
