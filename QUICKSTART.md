# Quickstart: install, configure, and use Spec Kit

Choose a **static** snapshot or **editable** source-linked installation, with `minimal`, `cgc`, `sourcegraph` or `all` dependencies. See [installation modes](docs/user/installation-modes.md). Setup now installs the `codebase-agent-setup` command as well as Spec Kit.

This tutorial installs codebase-agent-setup around official GitHub Spec Kit, configures a software project, and walks through a first feature. It describes the current package, which defaults to Specify CLI 1.0.4. Personal settings hierarchies are available; see [the settings guide](project/ai_workflow/settings.md). Local Spec Kit version overrides are available in [docs/user/toolchain-versions.md](docs/user/toolchain-versions.md). Shared graph downloads and automatic trunk detection remain planned in [ROADMAP.md](ROADMAP.md).

## 1. Prepare two separate directories

Keep this tooling repository outside the software project you want agents to work on:

```text
work/
  codebase-agent-setup/       # This tooling distribution
  my_project/      # Your software repository
```

Use an existing Git repository for `my_project`, or create one and make an initial commit before using knowledge bootstrap. Choose a tooling method below: native/venv needs Python 3.11 or newer and Git; Conda supplies them in its environment; Docker supplies them inside its image. Install your chosen coding assistant separately. Later agent bootstrap needs Python and Git in the environment where the agent runs. Project compilers, SDKs and test dependencies remain part of your project's normal setup.

The examples use Copilot. Replace `copilot` with `codex` or `cursor-agent` as needed. Installation output has been tested locally on Linux; Windows/macOS execution and live agent behaviour are not established by those tests. See [VALIDATION.md](VALIDATION.md).

## 2. Install machine tooling

Choose **one** method. Run from the `codebase-agent-setup` directory and replace example paths with your own.

| Method | Use when | Prerequisites |
| --- | --- | --- |
| venv | You want a dedicated Python tooling environment | Python 3.11+, pip/venv, Git |
| Native Python | You want the CLI in your existing Python installation/environment | Python 3.11+, pip, Git |
| Conda / Miniforge | You already manage tools with Conda | Conda in an initialised shell |
| Docker | You want installation tooling in a container | Docker with Linux containers; target directory accessible to Docker |

All four default to the same pinned source and install the same package; explicit version overrides are also available. Linux venv, alternate-version Conda and default/alternate Docker paths have been exercised. Host native installation and Windows/macOS remain unverified; see [VALIDATION.md](VALIDATION.md).

### Option A: venv

Linux/macOS:

```bash
cd /absolute/path/to/codebase-agent-setup
python3 --version
git --version
python3 setup_tooling.py --mode venv
python3 setup_tooling.py --mode venv --apply
./.venv/bin/specify version
```

Windows PowerShell:

```powershell
Set-Location C:\work\codebase-agent-setup
py -3 --version
git --version
py -3 setup_tooling.py --mode venv
py -3 setup_tooling.py --mode venv --apply
.\.venv\Scripts\specify.exe version
```

The first setup command previews dependency installation; `--apply` executes it and needs access to the dependency sources. Expect Specify CLI 1.0.4. The helper creates `.venv` in this tooling checkout; activation is unnecessary. This is separate from your software project's Python environment.

### Option B: native Python

Linux/macOS, from `codebase-agent-setup`:

```bash
python3 setup_tooling.py --mode native
python3 setup_tooling.py --mode native --apply
specify version
```

Windows PowerShell:

```powershell
py -3 setup_tooling.py --mode native
py -3 setup_tooling.py --mode native --apply
specify version
```

Outside an active venv or Conda environment, the helper installs with pip's user scope. Inside an active environment, it installs there. Add the scripts directory reported by pip to PATH so `specify` is found, or use its full executable path in step 3. If your operating system rejects installation into managed Python, choose venv or Conda.

### Option C: Conda / Miniforge

From `codebase-agent-setup`, in an initialised Conda shell on Linux/macOS or an Anaconda/Miniforge Prompt on Windows:

```text
conda env create --name codebase-agent-setup --file environment.yml
conda activate codebase-agent-setup
specify version
```

The environment file supplies Python 3.12, pip, Git and pinned Spec Kit. No separate native Python installation is needed. After activation, use `python` and `specify` normally.

The name is a default, not a requirement. For example, choose `my_spec_tools`:

```text
conda env create --name my_spec_tools --file environment.yml
conda activate my_spec_tools
```

If Python is already available, the setup helper exposes the same override and prints the activation command after successful installation:

```text
python setup_tooling.py --mode conda --conda-name my_spec_tools --apply
conda activate my_spec_tools
```

Activation must run in your current shell. The Python helper cannot change its parent shell's environment. In an already initialised Bash/Zsh shell, you can create and activate on success in one command:

```bash
python setup_tooling.py --mode conda --conda-name my_spec_tools --apply && conda activate my_spec_tools
```

If activation reports that the shell is not initialised, follow [Conda activation troubleshooting](INSTALLATION.md#conda-activation-troubleshooting). For scripts or an unactivated shell, `conda run -n my_spec_tools specify version` remains available. If `codebase-agent-setup` already exists, verify its CLI version instead of rerunning creation. See [INSTALLATION.md](INSTALLATION.md) for deliberate updates or a different environment name.

### Option D: Docker

From `codebase-agent-setup`, with Docker running:

```text
docker build -t codebase-agent-setup:1.1 .
docker run --rm --entrypoint specify codebase-agent-setup:1.1 version
```

The image installs Python, Git and pinned Spec Kit internally. It runs the project installer; it does not launch your IDE or coding agent. Step 3 mounts your project into the container. Later local agent bootstrap still requires Python and Git in that agent's environment.

For custom environment paths and further options, see [INSTALLATION.md](INSTALLATION.md).

## 3. Install the project files

Still in `codebase-agent-setup`, use the commands matching your choice in step 2. Preview uses disposable staging but does not write to the target project.

### With venv

Preview and then apply:

Linux/macOS:

```bash
python3 install.py /absolute/path/to/my_project --integration copilot
python3 install.py /absolute/path/to/my_project --integration copilot --apply
```

Windows PowerShell:

```powershell
py -3 install.py C:\work\my_project --integration copilot
py -3 install.py C:\work\my_project --integration copilot --apply
```

Quote paths containing spaces. The installer discovers the tooling `.venv` automatically.

### With native Python

Linux/macOS:

```bash
python3 install.py /absolute/path/to/my_project --specify specify --integration copilot
python3 install.py /absolute/path/to/my_project --specify specify --integration copilot --apply
```

Windows PowerShell:

```powershell
py -3 install.py C:\work\my_project --specify specify --integration copilot
py -3 install.py C:\work\my_project --specify specify --integration copilot --apply
```

`--specify specify` explicitly selects the CLI on PATH instead of a leftover tooling `.venv`. If needed, replace the second `specify` with the full executable path, quoted if it contains spaces.

### With Conda / Miniforge

Linux/macOS:

```bash
python install.py /absolute/path/to/my_project --specify specify --integration copilot
python install.py /absolute/path/to/my_project --specify specify --integration copilot --apply
```

Windows, in a Conda-enabled shell:

```text
python install.py C:\work\my_project --specify specify --integration copilot
python install.py C:\work\my_project --specify specify --integration copilot --apply
```

Run these commands after activating the environment selected in step 2. For scripts or an unactivated shell, prefix each command with `conda run -n YOUR_ENV_NAME`, using your chosen name. `--specify specify` prevents the installer from preferring an unrelated tooling `.venv`.

### With Docker

Ensure the target directory exists. First run your platform's command below **without `--apply`** to preview; then run it as shown to install.

Linux, preserving host file ownership:

```bash
docker run --rm --user "$(id -u):$(id -g)" --env XDG_CACHE_HOME=/tmp/cache --mount "type=bind,source=/absolute/path/to/my_project,target=/repo" codebase-agent-setup:1.1 /repo --integration copilot --apply
```

macOS:

```bash
docker run --rm --mount "type=bind,source=/absolute/path/to/my_project,target=/repo" codebase-agent-setup:1.1 /repo --integration copilot --apply
```

Windows PowerShell:

```powershell
docker run --rm --mount "type=bind,source=C:\work\my_project,target=/repo" codebase-agent-setup:1.1 /repo --integration copilot --apply
```

Docker Desktop must have access to the host directory. The installer writes into the mounted project, so the generated files remain after the container exits.

### Choose integrations and continue

For any method, repeat `--integration` on its preview and apply commands to prepare multiple agents. For example, with venv:

```bash
python3 install.py /absolute/path/to/my_project --integration codex --integration cursor-agent --integration copilot --apply
```

The first integration is restored as the default. Generated skills go under `.agents/skills` for Codex, `.cursor/skills` for Cursor, and `.github/skills` for Copilot. Copilot also receives `.github/copilot-instructions.md`.

If installation reports collisions, it stops before target writes. Preserve your authored files and follow the existing-project instructions in [INSTALLATION.md](INSTALLATION.md). Do not delete customised instructions just to make installation pass. For an unchanged legacy v6 installation, use the specific process in [docs/user/migration.md](docs/user/migration.md).

## 4. Configure your software project

Now open `my_project`. Make these edits there, not in this distribution's `project/` payload.

| File | What to configure |
| --- | --- |
| `ai_workflow/project.yaml` | Project name, active domains, language/tool versions, targets and authoritative source documents |
| `.specify/memory/constitution.md` | Agreed engineering principles and constraints |
| `ai_workflow/commands.yaml` | Actual configure, build, format, test, analysis and documentation commands; applicable completion profiles |
| `ai_workflow/coding_style.md` | References to existing style rules |
| `ai_workflow/build_test_deploy.md` | Build variants, test procedures and deployment requirements |
| `ai_workflow/documentation.md` | Authoritative documentation and update expectations |
| `ai_workflow/quality_gates.yaml` | Applicable project/domain checks |
| `ai_workflow/bootstrap.json` | Knowledge mode, source selection and base references |

For example, edit the corresponding fields in `project.yaml` while retaining its other fields:

```yaml
project:
  name: telemetry_service
active_domains:
  - python
language:
  c_standard: not_applicable
  cpp_standard: not_applicable
  python_version: '3.11'
  compiler_and_environment_versions:
    - 'Record the actual interpreter and dependency environment here'
source_documents:
  - README.md
```

Use `embedded` for relevant firmware work and add `data_science` where applicable. For C/C++, record actual language standards, compiler, target/board and build configuration. See `ai_workflow/domain_profiles.md` for the domain guidance.

In `commands.yaml`, replace `CUSTOMISE` with commands your project actually supports. For a Python project already using pytest, one existing entry might become:

```yaml
  test_all_required:
    command: python -m pytest
    working_directory: .
    mutates_source: false
    requires_human_approval: false
```

Run this using your project's intended Python environment. This is a fragment to edit inside `commands`, not a replacement for the whole file. For CMake projects, use your actual configure/build/test presets instead of inventing universal commands.

Configure every command required by your selected completion profile, including formatting, builds or environment checks, static analysis and documentation. Record why genuinely inapplicable checks do not apply. `CUSTOMISE` never counts as a successful check. Optional hardware, deployment and semantic backend entries may remain unconfigured until used; do not invoke those profiles as if they were operational.

You can ask your agent to help with configuration:

```text
Read AI_CONTEXT.md and the existing README, build files and CI configuration.
Configure the installed project guidance and command registry from that evidence.
Preserve existing project rules. Identify missing project-specific decisions;
do not invent commands or report unconfigured checks as passing.
```

## 5. Choose the current knowledge behaviour

For a first pilot, edit `ai_workflow/bootstrap.json` and set the existing `semantic_index.mode` field to `disabled`. This uses direct source analysis without a semantic backend. Alternatively, leave the default `auto`: when no compatible backend is configured, it falls back to source.

Do not use `required` until a real backend and necessary current layers exist. The package does not bundle one. A compilation database alone is not a graph.

Local file inventories and branch deltas remain available even with semantic mode disabled. The default selected-branch pattern is `^develop/.+$`; other branches still receive local state. Set `branch_selection.base_ref_candidates` to refs that actually exist in your repository. Current selection takes the first existing candidate; for multiple trunks, use an explicit base when needed rather than assuming automatic inference.

Review the configuration changes with `git diff` and `git status`, then commit the agreed workflow files through your normal process. Generated `.ai_cache/` knowledge and migration backups are ignored by the installer.

## 6. Start a session and discuss a change

Open your chosen assistant at `my_project` and say:

```text
Read AI_CONTEXT.md. Explain the telemetry component and discuss adding
validation for malformed input. Identify the relevant code and tests.
Do not implement yet.
```

This gives the agent the shared baseline and a bounded request. Conceptual discussion does not require bootstrap or file creation. Client settings still determine whether instructions and skills load; explicitly naming `AI_CONTEXT.md` makes the entry point clear.

## 7. Specify, plan, and implement

After agreeing the scope, use these prompts in sequence, reviewing each result before moving on:

1. `Read AI_CONTEXT.md. Use speckit.specify to specify the agreed malformed-input validation, with acceptance criteria. Do not implement yet.`
2. `Use speckit.plan to design the agreed feature using this project's existing architecture and tests. Do not implement yet.`
3. `Use speckit.tasks to break the plan into implementation and verification tasks.`
4. `Read AI_CONTEXT.md. Use speckit.implement to implement the agreed tasks. Run focused checks, complete the final review and correction cycle, and report remaining work.`

These are logical workflow names. Use ordinary language or your client's skill picker; do not assume every client exposes the same slash-command syntax.

Spec Kit owns `spec.md`, `plan.md`, and `tasks.md` in the feature directory it creates. If using an existing `develop/*` branch, identify the actual feature directory before upstream prerequisite scripts run. For example, only if this directory is your feature:

```bash
export SPECIFY_FEATURE_DIRECTORY=specs/001-telemetry
```

PowerShell equivalent:

```powershell
$env:SPECIFY_FEATURE_DIRECTORY = 'specs/001-telemetry'
```

Set this in the environment used by the agent's commands, or tell the agent to set it for those commands. Do not create a second task ledger or share mutable feature state between concurrent worktrees.

## 8. Refresh local knowledge and check completion

The installed instructions ask the agent to run bootstrap when beginning code work that allows cache writes. You can also run it yourself from `my_project`:

```bash
python3 ai_workflow/tools/repo_bootstrap.py prepare --pretty
```

For an explicit trunk, for example an existing `origin/release/1.x`:

```bash
python3 ai_workflow/tools/repo_bootstrap.py prepare --base-ref origin/release/1.x --pretty
```

On Windows use `py -3` in place of `python3`. With your Conda environment active, use `python` for these bootstrap and validation commands (including on Windows). Without activation, use `conda run -n YOUR_ENV_NAME python` with your chosen name. The Docker installer image is not a session runner; use Python and Git in your host or agent development environment for these commands. Read the returned action and semantic status. `prepare` creates inventories and an analysis request; it does not itself write the agent's understanding of the code. Have the agent follow `ai_workflow/bootstrap_analysis.md`, write the requested analysis outputs, and only then run:

```bash
python3 ai_workflow/tools/repo_bootstrap.py complete
```

If the source changed after preparation, prepare again. The analysis lives under `.ai_cache/code_knowledge/`; current semantic mode settings do not provide the roadmap's shared graph service.

At feature completion, ask:

```text
Use speckit.engineering.report to create the completion report for the active
feature. Include actual check evidence, incomplete items and unavailable checks.
Clearly distinguish self review from independent review.
```

Validate the resulting report using the actual feature directory:

```bash
python3 ai_workflow/tools/validate_completion.py specs/001-telemetry
```

This validates report structure, coverage and evidence references; it does not execute tests or certify the truth of the evidence. Review the code diff and actual test results through your normal review process.

## 9. Reuse the setup in another clone or on another PC

Commit and share the agreed project guidance and workflow files. In another clone, reuse those files; do not rerun the project installer merely to regenerate them. On another machine, obtain this tooling distribution and perform step 2 to create machine-local tooling, plus the project's usual development environment setup. Then open the configured clone and start at step 6.

Current caches are local. Portable graph bundles and shared trunk publication are described in [ROADMAP.md](ROADMAP.md) and [knowledge design](docs/development/knowledge-design.md). For local Spec Kit version selection and conservative upgrades, see [docs/user/toolchain-versions.md](docs/user/toolchain-versions.md).

## Optional graph retrieval

CGC and Sourcegraph default to off. Follow [knowledge_backends.md](project/ai_workflow/knowledge_backends.md) for optional dependencies, project/local selection, querying and CGC snapshot transfer. Existing installations can preview `install.py --upgrade` to obtain the new companion files.
