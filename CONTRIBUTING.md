# Maintaining the tooling package

Install the development tools with `python -m pip install -e '.[dev]'`, then run the quality gate and the bootstrap tests. The core has no runtime dependencies and needs no external CLI.

Linux or macOS with the default venv:

```bash
python3 -m unittest discover -s tests -v
python3 -m unittest discover -s project/ai_workflow/tools -p 'test_*.py'
```

Windows PowerShell:

```powershell
$env:PYTHONUTF8 = "1"
py -3 -m unittest discover -s tests -v
py -3 -m unittest discover -s project/ai_workflow/tools -p "test_*.py"
```

Report every skip rather than reading a skip count as intentional: a skip gated on a removed code path looks exactly like a deliberate environment gate. Test modified environment modes with actual tools before marking them verified. Keep CI and local evidence distinct.

Runtime code lives in `src/codebase_agent_setup/`; see [architecture](docs/architecture.md) for
source/editable resource handling and wheel assembly. `install`, `configure`, `knowledge` and the rest are
subcommands of the single `codebase-agent-setup` entry point; there are no root launchers. Edit the
installed payload at its authored path under `project/`; do not copy it into `src/`.

Companion project files supply policy, configuration and local utilities.

Before a release, update STATUS.md and VALIDATION.md. Follow [VERSIONING.md](VERSIONING.md): ordinary PRs leave the package version unchanged; CI bumps pyproject.toml and tags after eligible successful trunk merges. It is the sole package-version source. Spec Kit provisioning and backend adapters are retired.

## Historical toolchain checks (retired)

Spec Kit toolchains and their alternate-version tests were retired. Use
`CBSETUP_PACKAGE_TESTS=1 python scripts/check.py --full`; `[dev]` is the only extra.

## Repository knowledge checks

`tests/test_knowledge.py` needs no extra dependencies: every test declares a real command and asserts the wrapper runs it, keys its output by each file's content, and refuses the unsafe cases. The property to protect is that editing one file re-indexes exactly one file. When changing the layer model, verify by mutation — revert to whole-layer keying and confirm the two tests written for that property fail.

## Installed distribution checks

Set `CBSETUP_PACKAGE_TESTS=1` to include actual static/editable pip installations in the unittest suite. These build in disposable environments and may need network access for the build backend. The packaging test exercises a static installed launcher after its source checkout is moved and verifies consumer installation and preservation on upgrade. Hidden integration payload files must remain present in wheels.

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
