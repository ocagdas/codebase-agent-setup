# Installation on Windows, Linux and macOS

For a guided first setup followed by configuration and usage, start with [QUICKSTART.md](QUICKSTART.md).

Use this repository as the tooling distribution. Keep it outside the software repository you want to configure. Machine setup installs the codebase-agent-setup launcher and official Spec Kit; install.py then installs the project files. The same tooling environment can serve multiple project clones.

The default is a Python virtual environment. Native Python, Conda and Docker are alternatives. Minimal setup does not install graph dependencies. Add `--extras cgc`, `sourcegraph` or `all` for optional clients; use `--static` (default) or `--editable` to select source update behavior. See [docs/user/installation-modes.md](docs/user/installation-modes.md). Coding assistants, compilers, board SDKs and model subscriptions remain separate.

## Prerequisites and validation scope

| Method | Windows | Linux | macOS | Prerequisites |
| --- | --- | --- | --- | --- |
| Native Python | PowerShell commands below | Shell commands below | Shell commands below | Python 3.11 or newer with pip; Git on PATH |
| venv | Scripts directory | bin directory | bin directory | Python with venv and pip; Git on PATH |
| Conda | Anaconda Prompt or initialised shell | Initialised shell | Initialised shell | Conda or Miniforge; environment includes Python, pip and Git |
| Docker | Docker Desktop using Linux containers | Docker Engine | Docker Desktop using Linux containers | Docker running; target directory exists and is shared with Docker |

Linux utility/integration execution, alternate-version Conda setup and activation, and default/alternate Docker image builds with non-root installation have been tested. Host native installation and Windows/macOS execution remain unverified. No GitHub Actions workflow is currently included. Regression CI remains follow-up work; no remote platform results are available.

If Python, Git, Conda or Docker is missing, install it using your organisation's approved method first. Some Linux distributions package venv separately. Do not override an operating system managed Python restriction; use venv or Conda if native pip refuses installation.

## Recommended: venv

Linux and macOS, from this tooling repository:

```bash
python3 setup_tooling.py --mode venv --apply
python3 install.py /absolute/path/to/project --integration copilot
python3 install.py /absolute/path/to/project --integration copilot --apply
```

Windows PowerShell:

```powershell
py -3 setup_tooling.py --mode venv --apply
py -3 install.py C:\work\project --integration copilot
py -3 install.py C:\work\project --integration copilot --apply
```

Use a Python 3.11 or newer interpreter. The setup creates .venv beside install.py and installs the pinned official CLI. install.py detects .venv/bin/specify on Linux and macOS or .venv/Scripts/specify.exe on Windows. Activation is unnecessary. Omit --apply from setup_tooling.py to inspect the dependency installation commands without executing them.

To use a custom environment path:

```bash
python3 setup_tooling.py --mode venv --env-dir /path/to/toolenv --apply
python3 install.py /path/to/project --specify /path/to/toolenv/bin/specify --integration copilot --apply
```

On Windows, the equivalent executable is C:\path\to\toolenv\Scripts\specify.exe. Quote paths containing spaces. Virtual environments are recreated per machine and are never pushed to Git or copied between operating systems.

## Native Python

Native setup verifies the executable in the same scripts directory used for installation: the user scripts directory for `pip --user`, or the current environment's scripts directory otherwise. An unrelated `specify` on PATH is not used for setup verification.

Linux and macOS:

```bash
python3 setup_tooling.py --mode native --apply
python3 install.py /path/to/project --specify /path/to/user/scripts/specify --integration copilot --apply
```

Windows:

```powershell
py -3 setup_tooling.py --mode native --apply
py -3 install.py C:\work\project --specify C:\path\to\Scripts\specify.exe --integration copilot --apply
```

Outside an active venv or Conda environment, this uses pip's user installation. Add that Python user scripts directory to PATH, or provide its full specify path as shown. Inside an active environment it installs into that environment. Replace the example paths with the location pip reports. A managed Python installation may reject native installation even with user scope.

## Conda or Miniforge

From this tooling repository in a Conda-enabled shell, choose an environment name and activate it:

```text
conda env create --name codebase-agent-setup --file environment.yml
conda activate codebase-agent-setup
specify version
python install.py /path/to/project --specify specify --integration copilot
python install.py /path/to/project --specify specify --integration copilot --apply
```

Use a Windows path such as `C:\work\project` on Windows. `codebase-agent-setup` is only the default: replace it with your chosen name in creation and activation commands. `--name` overrides the name in environment.yml. Once active, use `python` and `specify` normally. Explicit `--specify specify` chooses the CLI on the environment's PATH rather than an existing tooling `.venv`.

When Python and Conda are already available, the helper offers the same override:

```text
python setup_tooling.py --mode conda --conda-name my_spec_tools --apply
conda activate my_spec_tools
```

Omit `--apply` to preview creation. After successful installation the helper prints the activation command for the chosen name. For unattended commands or an unactivated shell, use:

```text
conda run -n my_spec_tools python install.py /path/to/project --specify specify --integration copilot --apply
```

Creation stops if the named environment already exists. To deliberately update your selected environment, use `conda env update --name my_spec_tools --file environment.yml`. Review dependency changes before updating a shared environment.

### Conda activation troubleshooting

Activation changes the current shell. A Python child process cannot activate its parent shell, so setup prints the next command instead of claiming it activated the environment. In an initialised Bash/Zsh shell, installation and activation can be chained:

```bash
python setup_tooling.py --mode conda --conda-name my_spec_tools --apply && conda activate my_spec_tools
```

The activation runs only if setup succeeds. In PowerShell, run activation after checking success:

```powershell
python setup_tooling.py --mode conda --conda-name my_spec_tools --apply
if ($LASTEXITCODE -eq 0) { conda activate my_spec_tools }
```

If `conda activate` reports missing shell initialisation, run the command matching your shell once, then close and reopen that terminal:

| Shell | Initialisation command |
| --- | --- |
| Bash | `conda init bash` |
| Zsh | `conda init zsh` |
| PowerShell | `conda init powershell` |
| Windows Command Prompt | `conda init cmd.exe` |

These commands modify shell startup configuration; the setup helper does not run them automatically. If `conda` itself is unavailable, use an Anaconda/Miniforge Prompt or the installed Conda executable to initialise the desired shell. Then run `conda activate my_spec_tools`.

Verify the selected interpreter and CLI:

```text
python -c "import sys; print(sys.executable)"
specify version
```

The interpreter should belong to the selected environment and the CLI should report 1.0.4. IDE terminals may need reopening after initialisation; IDE run/debug interpreter selection is separate from terminal activation. `conda run -n my_spec_tools ...` remains an option when activation is inconvenient.

See the official [Conda shell initialisation documentation](https://docs.conda.io/projects/conda/en/latest/commands/init.html) for shell-specific details. Conda creation and activation were exercised on Linux in a child Bash session for the version-override pilot; other shells/platforms remain unverified. See VALIDATION.md.

## Docker

Build the tooling image from this repository:

```text
docker build -t codebase-agent-setup:1.1 .
```

Linux example, preserving host file ownership:

```bash
docker run --rm --user "$(id -u):$(id -g)" --env XDG_CACHE_HOME=/tmp/cache --mount "type=bind,source=/absolute/path/to/project,target=/repo" codebase-agent-setup:1.1 /repo --integration copilot --apply
```

macOS example:

```bash
docker run --rm --mount "type=bind,source=/absolute/path/to/project,target=/repo" codebase-agent-setup:1.1 /repo --integration copilot --apply
```

Windows PowerShell example:

```powershell
docker run --rm --mount "type=bind,source=C:\work\project,target=/repo" codebase-agent-setup:1.1 /repo --integration copilot --apply
```

The target directory must already exist. Omit --apply to preview. Only the mounted target is installed into; source files and existing authored instructions are protected by installer conflict checks. This is a Linux tooling container on all three hosts, not a Windows container. It creates repository instructions; it does not run your IDE or agents. Local agent bootstrap later still needs Python and Git in the agent's execution environment.

The image downloads dependencies while building. Runtime project staging uses the official CLI's bundled assets. The Python image tag and transitive dependencies are not fully locked by digest; upstream.lock.json pins Spec Kit itself, not the entire operating system or dependency graph.

## Choose a Spec Kit version

The default stays pinned to 1.0.4. Use `speckit.ref` in project/personal settings or `--speckit-ref` to select another official release or full commit. See [docs/user/toolchain-versions.md](docs/user/toolchain-versions.md) for environment isolation, Conda names, Docker build arguments, record export/import and upgrade previews.

## Choose agents

Any installation method can select codex, cursor-agent or copilot. Repeat the integration option to prepare one project for all three:

```text
python install.py /path/to/project --integration codex --integration cursor-agent --integration copilot --apply
```

Replace python with python3 or py -3 where appropriate. The installer uses only the documented explicit upstream multiple integration option in disposable staging, renders customisations for each integration, then restores the first as default.

## Existing Spec Kit projects

The full installer is intentionally conservative and stops on differing existing files. It is not a general merge tool. The new --upgrade option updates only unchanged files recorded by an earlier installation ledger; older installations without a ledger still require manual merging. You can use the official CLI directly inside an existing project:

```text
specify extension add --dev /path/to/this/tooling/extension
specify preset add --dev /path/to/this/tooling/preset
```

Use Specify CLI 1.0.4. Compare and merge the relevant files from project/ into your project, especially AI_CONTEXT.md, domain configuration, utilities and the constitution. Preserve authored values. The extension and preset alone expect those companion files and are not a complete standalone installation. Installing them does not overwrite the live constitution with our seed.

For the recognised unchanged v6 baseline, use the --migrate-v6 option described in docs/user/migration.md. For a new clone whose configuration is already committed, install machine tooling only; do not regenerate its repository files.

## Official references

[Spec Kit](https://github.com/github/spec-kit)

[Python virtual environments](https://docs.python.org/3/library/venv.html)

[Conda environment management](https://docs.conda.io/projects/conda/en/stable/user-guide/tasks/manage-environments.html)

[Docker bind mounts](https://docs.docker.com/engine/storage/bind-mounts/)

## Recovery and command deadlines

Project installation stages content before writing it. Each destination is replaced atomically; a journal at `.specify/engineering-transaction/` saves originals until the file updates and installation ledger are complete. An ordinary write failure attempts rollback. After a process interruption, rerun the same install command with `--apply` to recover before planning the installation again. Preview reports a pending recovery without changing files.

Recovery checks the saved hashes before restoring files. If someone edited a destination after interruption, or a backup is damaged, it stops and identifies the journal and conflicting file for manual reconciliation. Keep the journal until that reconciliation is complete. An operating-system file lock blocks another installer while the current process is running and is released when that process exits. The persistent `.specify/engineering-install.lock` file must not be removed while installers are running. Journals from the earlier PID-based implementation require manual reconciliation after stopping old installers; the new implementation never probes or signals their PIDs. Run one installer per checkout. This mechanism handles process interruptions and ordinary I/O failures; it is not a guarantee against power loss, filesystem corruption or concurrent external edits. The optional exported toolchain record is written after the project transaction; if export fails, the completed project installation remains in place and the command can be retried.

Toolchain probes default to **15 seconds** and other toolchain/setup commands to **600 seconds per command**. Set `CBSETUP_PROBE_TIMEOUT` or `CBSETUP_COMMAND_TIMEOUT` to a finite positive number of seconds to override these limits, for example when downloading dependencies over a slow connection. Discovery continues to other candidates after a probe times out. POSIX timeout handling terminates the command's process group; Windows handling terminates the immediate process. These controls do not change the knowledge adapter's separate indexing/query limits.

Recovery journals now record explicit prepared, committed and rolled-back phases. Completed journals are atomically renamed to `.specify/engineering-retired-*` before deletion. A deletion failure reports deferred cleanup; a later installation retries it without treating the remnants as an active transaction. The installer adds ignore rules for the lock, active journal and retired directories. Locking uses `flock` on POSIX and byte-range locking on Windows; Windows execution still requires platform validation.

Cancellation uses the same subprocess cleanup as timeouts. On POSIX, Ctrl-C stops the owned command's process group and reaps the direct child before propagating cancellation, so setup releases its environment lock after that cleanup. Windows cleanup terminates the direct child; descendant-tree cancellation has not been validated on Windows.
