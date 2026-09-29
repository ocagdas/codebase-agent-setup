# Install profiles and source update behavior

codebase-agent-setup uses the same terms as the neighboring Aiplane project: **static** (a snapshot) and **editable** (linked to a source checkout). These choices are separate from where Python runs: native, venv, Conda or Docker.

## Initial setup

From the codebase-agent-setup checkout:

```bash
# Default: pinned Spec Kit plus a static codebase-agent-setup launcher, no graph dependencies.
python setup_tooling.py --mode venv --static --extras minimal --apply

# Source-linked development installation with both optional backend clients.
python setup_tooling.py --mode venv --editable --extras all --apply
```

Choose one, not both. Omit `--apply` to preview the exact commands without installing. `--install-mode static|editable` is equivalent to the shorthand flags. `--env-dir /path/to/env` controls a venv location. Existing Spec Kit version options continue to work; the selected Spec Kit and codebase-agent-setup are installed in the same target environment.

| `--extras` | What setup installs |
| --- | --- |
| `minimal` (default) | codebase-agent-setup and the selected pinned Spec Kit |
| `sourcegraph` | Minimums plus the MCP client |
| `cgc` | Minimums plus CodeGraphContext, Kuzu and MCP |
| `all` | Minimums plus all currently supported optional clients |

Optional packages remain subject to their own platform/Python support. Installing them does **not** enable a backend, start a server or parse a repository. `knowledge.backend` remains off until selected through project/user settings or a query's `--backend` argument. Sourcegraph still needs a separately managed deployment; no Sourcegraph server is installed. See [backend configuration](../../project/ai_workflow/knowledge_backends.md).

## Run the installed command

Activate the environment and run ordinary commands:

```bash
source .venv/bin/activate
codebase-agent-setup --version
codebase-agent-setup configure inspect --repo /path/to/project
codebase-agent-setup install /path/to/project --integration copilot --apply
codebase-agent-setup knowledge status --repo /path/to/project
codebase-agent-setup knowledge query --repo /path/to/project --backend cgc --query MyFunction
```

Activation is optional if you use `.venv/bin/codebase-agent-setup` directly. Windows uses `.venv\Scripts\codebase-agent-setup.exe`; activate with `.\.venv\Scripts\Activate.ps1` in PowerShell if desired. `--version` reports the installed package version, static/editable mode and code location. Each subcommand accepts `--help`. The existing `python install.py`, `configure.py` and `knowledge.py` entry points remain available, but those direct scripts always use their checkout regardless of the installed launcher's mode.

## What updates automatically?

| Change | Static install | Editable install |
| --- | --- | --- |
| codebase-agent-setup Python source edited or pulled | Reinstall to update | Next launcher run uses updated code |
| Templates/payload edited or pulled | Reinstall to update | Next installation/upgrade reads updated payload |
| Dependency declarations or command entry points changed | Reinstall | Reinstall |
| Files already installed into a consumer repository | Explicit project upgrade | Explicit project upgrade |

Static installs package the Python code and all required payload resources into the environment. They continue to work if the source checkout is moved or removed. Editable installs require that checkout to stay at its installed location. Neither mode pulls Git updates automatically or hot-reloads an already running process.

Consumer repository files remain independent, reviewable copies. To apply a newer payload, use `codebase-agent-setup install /path/to/project --upgrade` for preview, then repeat with `--apply`. Custom files are preserved according to the existing installer rules.

## Native and Conda

```bash
# Install into the currently active Python environment, or user site for bare Python.
python setup_tooling.py --mode native --editable --extras sourcegraph --apply

# Create a named Conda environment containing the tooling and selected optional clients.
python setup_tooling.py --mode conda --conda-name my_cbsetup_tools --static --extras cgc --apply
conda activate my_cbsetup_tools
codebase-agent-setup --version
```

Setup cannot activate its parent shell. An already activated Conda environment supports ordinary `python` and `codebase-agent-setup` commands. To update an existing Conda environment, activate it and use `--mode native`, or use the pip commands below; the Conda creation path is for a new named environment.

## Reinstall or switch modes in an existing environment

From the source checkout, with the desired environment activated:

```bash
python -m pip install .                 # static minimal launcher
python -m pip install --editable .      # editable minimal launcher
python -m pip install --editable '.[cgc]'
python -m pip install '.[sourcegraph]'
python -m pip install '.[all]'
```

Direct pip installs manage codebase-agent-setup and its selected extras; they do not provision or change Spec Kit. Use setup_tooling.py for complete initial setup and Spec Kit version selection. Selecting `minimal` does not uninstall optional packages already present; create a fresh environment when you want only the minimum dependencies. No public package-index release is assumed by these local installation commands.

## Docker

The default image remains a static/minimal installation. Select optional dependencies or editable mode at build time:

```bash
docker build --build-arg CBSETUP_EXTRAS=sourcegraph -t codebase-agent-setup:static .
docker build --build-arg CBSETUP_INSTALL_MODE=editable \
  --build-arg CBSETUP_EXTRAS=all -t codebase-agent-setup:editable .
```

A static image uses its built-in snapshot; rebuild to update. For the editable image, mount this checkout at its installed path and run the installed launcher:

```bash
docker run --rm --entrypoint codebase-agent-setup \
  -v "$PWD:/opt/engineering:ro" -v /path/to/project:/workspace \
  codebase-agent-setup:editable install /workspace --specify specify --apply
```

This editable example uses the default pinned Spec Kit in the image. It bypasses the legacy Docker wrapper's image-local source record, which a checkout mount would hide. Rebuild for dependency changes. For alternate Spec Kit image versions, use the existing static image flow in [docs/user/toolchain-versions.md](toolchain-versions.md). Mount caches separately if backend data must persist, and follow your normal container UID/GID configuration to preserve host ownership.

Installation rechecks files against the contents observed during planning. If another
process edits a destination before the transaction starts, installation stops and
preserves the edit; review it and rerun the command. No overwrite flag is needed.
