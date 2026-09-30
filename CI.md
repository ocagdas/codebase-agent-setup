# Quality gates and release readiness

The same Python commands run locally and in GitHub Actions. No Make installation is required; the Makefile provides convenience aliases. Use Python 3.11 or newer and Git with `--show-object-format` support.

## Local checks

```bash
python -m pip install -e '.[dev]'
python scripts/check.py
```

The gate checks Ruff formatting, Ruff static analysis, distribution contracts and both unittest suites. It exits nonzero on failure and writes `.quality/gate.json` with `go: true` only if every stage passed. `.quality/tests.json` lists test counts, failures and explicit skips. `make check` is equivalent. Fix formatting with `python -m ruff format .`; do not bypass a failing check to obtain a green result.

The default unit profile permits the existing optional integration skips and reports them. It is not the release gate. For all integration tests, install optional dependencies and prepare both pinned toolchains:

```bash
python -m pip install -e '.[dev,all]'
python scripts/prepare_integration.py
```

The helper writes `.quality/toolchains/environment.json`. Set its four values in your shell: `SPECIFY_BIN`, `SPECIFY_ALTERNATE_BIN`, `SPECIFY_ALTERNATE_RECORD`, and `CBSETUP_PACKAGE_TESTS=1`. Then run:

```bash
python scripts/check.py --full
```

Full mode fails if prerequisites are absent or any test is skipped. It covers default and alternate Spec Kit installation, static/editable distributions and backend protocol fixtures. Run the strict profile on Linux; POSIX-only tests are explicitly skipped on Windows. Test results do not certify production Sourcegraph, real agent behavior or token savings.

## Hosted checks and go/no-go integration

`.github/workflows/ci.yml` runs for pull requests, branch pushes, merge queues and manual dispatch. It is also reusable through `workflow_call`. Jobs cover:

- formatting, static analysis, contract validation and checksum-pinned actionlint workflow validation;
- unit tests on Linux/Python 3.11–3.13 and macOS/Windows/Python 3.13;
- complete Linux integration tests with no skips;
- wheel/sdist build, metadata validation, checksums and clean-environment wheel smoke tests.

The final **Quality gate** job requires all four job groups to succeed. Failed, cancelled, skipped or missing prerequisites produce NO-GO; any additional non-success dependency also blocks. It publishes `go=true|false` as a job output, a reusable-workflow output and `.quality/ci-gate.json`. Evidence is uploaded as Actions artifacts. Quality jobs use read-only repository permissions and immutable action commits; the separately gated reusable version workflow receives the configured App secret only for eligible trunk pushes; it does not execute untrusted PR code with a privileged `pull_request_target` event.

Repository administrators must enable Actions and configure the default branch/release trunks to require **Quality gate**, require up-to-date checks or a merge queue, prevent force pushes, and require review appropriate to the team. A workflow file alone cannot enforce branch protection. Add the check after its first real run so GitHub can discover its name. Do not exempt documentation-only changes: they can affect package metadata, workflows or installed guidance.

A downstream deployment workflow can call `ci.yml`, depend on that job, and require `needs.checks.result == 'success'` and `needs.checks.outputs.go == 'true'` for the same commit. Also use a protected deployment environment for publication credentials and approvals. Never consume a previous run's green flag as evidence for a different commit.

The `quality-gate` artifact contains `ci-gate.json` with the shared schema:

```json
{"schema_version": 1, "go": true, "commit": "tested-sha", "run_id": "run-id", "checks": {"quality": "success", "unit": "success", "integration": "success", "artifacts": "success"}}
```

`python scripts/ci_gate.py --results jobs.json --report .quality/ci-gate.json` reads an explicit results file; otherwise it reads NEEDS_JSON. Invalid/missing input fails closed. Local runs without GitHub environment identity report null commit/run_id, so they cannot stand in for hosted evidence. The local stage/test reports remain separate from this shared hosted schema.

`version.yml` is reusable only and is called by eligible top-level CI trunk pushes after Quality gate success. Release checks reuse `ci.yml` without invoking mutation. See VERSIONING.md for selected-trunk defaults, App settings and serialized atomic publication. No remote rules are changed by these workflow files.

## Release candidates

```bash
python scripts/build_release.py --candidate
# On a clean checkout of an existing annotated release tag:
python scripts/build_release.py --tag v1.1.0
python scripts/build_release.py --verify-only
```

The build command requires empty output, verifies tag/version consistency when a tag is supplied, builds one wheel and one source distribution, validates metadata with Twine, checks wheel licenses/payload, installs the wheel in a disposable environment, and writes checksummed `provenance.json` and `SHA256SUMS`. Build defaults to `.quality/release`; choose another directory with `--output`. A manifest detects changed bytes; it does not authenticate an arbitrary publisher.

The **Release readiness** workflow runs on version tags or manual dispatch, reuses the entire CI gate and uploads a validated release candidate only after GO. It prepares distribution artifacts; it does not create public releases, upload to PyPI, change versions, move tags or deploy automatically. Publication can consume these artifacts behind the team's protected environment. Tag names must match both `pyproject.toml` and `upstream.lock.json`.

## Maintainer setup

Enable GitHub private vulnerability reporting so the route in SECURITY.md works. Confirm a private maintainer contact for conduct reports, and configure notification/review ownership. Dependabot proposes weekly action and Python updates; each update must pass the same gate. Optional backend pins must stay consistent with `requirements-knowledge.txt`; default Spec Kit pins must stay consistent with `requirements.txt` and manifest compatibility constraints.

See VALIDATION.md for what actually ran. A workflow committed locally is readiness evidence, not a successful remote CI run or verified Windows/macOS support.

## Contract and workflow maintenance

The gate runs the shared conformance suite described in
[REPOSITORY_STRUCTURE.md](REPOSITORY_STRUCTURE.md). [VERSIONING.md](VERSIONING.md)
owns mutation and release policy; [GitHub setup](docs/development/github-policy-setup.md)
owns hosted rules and activation. Refer to these owners when changing those policies.

Workflow actions use full commit pins and exact version comments. All uses of the
same action must agree across workflows; `scripts/validate_project.py` checks this.
Update all occurrences together, review upstream changes, and rerun actionlint and CI.
Integration uploads name `.quality/gate.json` and `.quality/tests.json` explicitly with
hidden-file inclusion, so toolchain directories are not uploaded.

## Workflow dependency checks

`python scripts/check_workflow_pins.py` requires full commit pins, exact version
comments and identical revisions for repeated external actions. The managed repository
conformance check runs it in the required gate. Update pins and their version comments
together, review upstream compatibility, then run conformance and actionlint. Hosted
execution still qualifies runner/action behavior; local syntax checks do not.

The pin validator uses PyYAML from the developer dependencies to inspect action and
reusable-workflow references structurally, including flow mappings and aliases. Put
the exact `# vX.Y.Z` comment immediately after the pinned value (or its closing flow
delimiters). Duplicate keys and YAML merge keys are rejected; shell-script contents
are not treated as workflow actions.

Integration initializes `gate.json` and `tests.json` before Python dependency and
Spec Kit setup. Until checks execute, these record NO-GO and tests not run. Setup
failures therefore retain uploadable diagnostics; successful gate/test execution
replaces the placeholders. Artifact upload and the required Quality gate still fail
on missing evidence or unsuccessful dependencies.

The shared Dependabot policy excludes MCP 2.x and later while CodeGraphContext
0.6.x requires MCP below 2. Keep the exact MCP pin synchronized between package
extras and `requirements-knowledge.txt`; qualify a compatible backend before lifting
that restriction. Dependency upgrades must resolve the complete `[dev,all]` extra.
