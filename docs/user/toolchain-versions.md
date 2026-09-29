# Local Spec Kit version selection

The distribution-tested default remains official Spec Kit 1.0.4 at the commit in upstream.lock.json and requirements.txt. Personal or project overrides do not edit those files. This feature selects official releases or full commits; arbitrary repositories and moving branch names are rejected.

## Choose a release per project

Add the following field to your existing `ai_workflow/settings.local.json`, or use shared settings.json if the team agrees on the selection:

```json
{
  "schema_version": "1.0",
  "settings": {
    "speckit": {"ref": "v1.0.3"}
  }
}
```

1.0.3 is an exercised example, not a recommendation to downgrade. The setting follows the existing user → shared project → personal project → checkout → invocation hierarchy. `null` resets to the distribution pin. Inspect it with:

```bash
python configure.py inspect --repo /path/to/project
```

From this tooling distribution, preview then install the selected CLI:

```bash
python setup_tooling.py --repo /path/to/project
python setup_tooling.py --repo /path/to/project --apply
```

Or select a version for one invocation:

```bash
python setup_tooling.py --speckit-ref v1.0.3 --apply
python install.py /path/to/project --speckit-ref v1.0.3
python install.py /path/to/project --speckit-ref v1.0.3 --apply
```

Use `python3` or an activated environment's `python` on Linux/macOS and your chosen interpreter on Windows. The current interpreter must be Python 3.11+. Both setup and installation must receive the same project scope, settings, explicit ref or imported record. A one-off setup flag does not change project configuration.

## Resolution and isolation

A release is resolved through the official Git repository to a full commit; annotated tags are peeled. The CLI version is read from that commit's pyproject.toml. Preview may use the network and disposable temporary directories to resolve an alternate release, but does not modify target project files or install environments. The validated default resolves offline. Settings inspection itself never resolves remote tags.

| Setup mode | Behaviour for a different commit |
| --- | --- |
| venv | Uses a sibling of the configured/default venv named `<base>-speckit-<full-commit>` |
| native | Uses the same isolated companion venv mechanism, preserving the active/native CLI |
| Conda | Creates `<configured-name>-speckit-<full-commit>` using conda-forge, then installs the exact source there |
| Docker | Optional build argument selects a version inside the image; runtime selects the built image's source record and CLI, independent of host tooling preferences |

This prevents switching one project's version from replacing another's environment. Existing unowned override environments are refused; environments with another source identity are not reused. Venv setup uses an exclusive setup lock; after an interrupted process, inspect the printed lock path before removing a stale lock. Failed installation can leave an owned partial venv that the same selection can retry. Conda creation refuses an existing environment; inspect/recover that environment explicitly before retrying creation.

Conda setup prints the exact activation command with the suffixed name. Once active, ordinary Python commands work. For automated project installation, the installer can locate the selected Conda environment; activation remains a shell operation. Native override users can let install.py discover the companion venv without activating it. Explicit `--specify` must identify the selected CLI, not an unrelated default on PATH. Automatic discovery also checks the running interpreter's scripts directory and PATH. Candidate CLIs must match the selected version; alternate versions must pass source-commit verification. This lets an installed static launcher find a matching alternate CLI without depending on its original checkout. An explicit `--specify` is never silently replaced by another candidate.

Docker example:

```bash
docker build --build-arg SPEC_KIT_REF=v1.0.3 -t codebase-agent-setup:local-1.0.3 .
docker run --rm --mount "type=bind,source=/absolute/path/to/project,target=/repo" codebase-agent-setup:local-1.0.3 /repo --integration copilot
```

Add `--apply` after reviewing the container installer preview. Existing ownership/platform mount guidance in INSTALLATION.md still applies. Both default and alternate Docker images were built and exercised with non-root mounted-project preview/apply on Linux; see VALIDATION.md for exact evidence and limits.

## Compatibility checks

Setup and install stage real upstream `init`, extension/preset installation, integration activation and generated command/template checks in a temporary project. Overrides also require the installed package's VCS metadata to match the selected official commit; merely printing the same version is insufficient.

Our committed extension/preset manifests remain pinned to 1.0.4. For an explicit alternate commit, temporary copies declare the selected version so the compatibility probe can run. This is an experimental local adaptation, not a claim of upstream certification or broad version compatibility. If required public commands, rendered implementation/report skills or templates are missing, the operation fails before target installation.

Results distinguish `distribution_default` from `local_override_checked`. Checks cover rendered package structure and composition, not live agents, project build correctness or every possible semantic behaviour change. When upgrading and preserving authored differences, the compatibility result describes clean staging, not a certification of the resulting customised project.

## Resolved records and sharing

After successful setup, `.codebase-agent-setup-toolchain.json` is written inside the selected venv/Conda environment. Native default setup records live under this distribution's ignored `.toolchains/records/` directory. Export a portable copy deliberately:

```bash
python setup_tooling.py --repo /path/to/project --export-record /tmp/my-toolchain.json --apply
```

The record includes official repository, exact source commit, requested ref, CLI and codebase-agent-setup package versions, checked integrations, source verification and the package fingerprint. It contains no executable commands or machine-specific environment path. This pins Spec Kit source, not all transitive Python/OS dependencies. Do not claim it reproduces the entire machine environment.

On another machine, import that exact selection:

```bash
python setup_tooling.py --toolchain-record /path/to/my-toolchain.json --apply
python install.py /path/to/project --toolchain-record /path/to/my-toolchain.json
python install.py /path/to/project --toolchain-record /path/to/my-toolchain.json --apply
```

Import avoids resolving a tag again, but a fresh installation still needs source/dependency access. Conflicting explicit/configured refs or a different codebase-agent-setup package version are rejected. Imported compatibility claims are not trusted: local staging runs again. A ref in a record is informational; its exact commit is the selection. Export refuses to replace arbitrary authored files.

Keep personal exports outside project source or under ignored `.ai_cache/`. Commit a reviewed record only if intentionally adopting it as a team lock. Never commit the virtual environments themselves.

## Preview and apply an upgrade

New installs write `.specify/engineering-install.json`, which records source identity and hashes of installed generated files. Keep this ledger with the shared project configuration so a new clone can identify unchanged managed files.

For a project installed by this version of the installer:

```bash
python install.py /path/to/project --upgrade --speckit-ref v1.0.3
python install.py /path/to/project --upgrade --speckit-ref v1.0.3 --apply
```

Set up that CLI first. Preview lists unchanged generated files eligible for replacement, authored differences that will be preserved, and obsolete paths that will be retained. Apply updates only unchanged managed files and adds missing files. Custom instructions, constitution, project values and other authored differences survive; review retained differences for compatibility yourself. Obsolete files are not automatically deleted.

Changing a setting or installing tooling never upgrades project files automatically. Without --upgrade, existing differing files still cause the original conservative collision error. Older installations without this ledger require manual comparison/merge; no ownership hashes are guessed. The recognised --migrate-v6 workflow remains separate.
