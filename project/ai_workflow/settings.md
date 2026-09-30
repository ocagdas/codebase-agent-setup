# Personal and project settings

Settings schema 1.0 is implemented for tooling preferences and knowledge navigation. Official Spec Kit release/commit overrides are available through `speckit.ref`. Optional CGC/Sourcegraph retrieval and manual CGC full-snapshot sharing are implemented. Query budgets are knowledge CLI options (--limit and --max-chars), not persisted settings. Shared semantic composition and fetch/update policies remain planned. Unknown settings are rejected rather than accepted without effect.

## Files and precedence

From lowest to highest priority:

1. Distribution defaults.
2. User file `settings`.
3. Existing `bootstrap.json` navigation fields, followed by shared `ai_workflow/settings.json` settings.
4. User file `projects[repository_id]`.
5. Ignored `ai_workflow/settings.local.json` for this checkout.
6. Explicit invocation options.

The user file defaults to `$XDG_CONFIG_HOME/codebase-agent-setup/config.json` (or `~/.config/codebase-agent-setup/config.json`) on Linux, `~/Library/Application Support/codebase-agent-setup/config.json` on macOS, and `%APPDATA%/codebase-agent-setup/config.json` on Windows. `--user-config PATH` selects another user file on all entry points. Missing files are allowed; malformed existing files are errors. These are JSON files to keep installed tooling independent of YAML libraries.

Mappings merge by key, lists replace rather than append, and `null` resets a field to its distribution default. A missing key inherits. `tooling.env_dir` and `cgc.data_dir` are relative to their declaring file, or the current directory for CLI overrides; `~` expands but environment variable interpolation is not performed. Other strings are not resolved as file-relative settings. In particular, cgc.executable is passed as a command name or executable path.

## Available settings

| Key | Default | Meaning |
| --- | --- | --- |
| `tooling.mode` | `venv` | `venv`, `native`, or `conda` machine setup |
| `tooling.env_dir` | `null` | Optional venv directory; null uses the tooling distribution's `.venv` |
| `tooling.conda_name` | `codebase-agent-setup` | Conda environment name |
| `speckit.ref` | `null` | Official release/tag or full commit; null uses the distribution pin |
| `agent.integrations` | `["codex"]` | Installer integrations; codex, cursor-agent, copilot |
| `knowledge.mode` | `auto` | auto, source, or index; maps to legacy auto, disabled, or required |
| `knowledge.base_refs` | `null` | Ordered base candidates; null uses legacy bootstrap candidates; an empty list disables candidate selection |
| `knowledge.backend` | `off` | Optional adapter: off, cgc or sourcegraph |
| `cgc.executable` | `cgc` | CGC command or executable path |
| `cgc.data_dir` | `null` | Per-checkout CGC storage; relative overrides resolve against their declaring file |
| `sourcegraph.url` | `null` | HTTPS deployment base URL |
| `sourcegraph.repository` | `null` | Repository name on the deployment |
| `sourcegraph.token_env` | `SOURCEGRAPH_TOKEN` | Environment variable containing the access token |

The distribution default for knowledge.mode is superseded by an existing bootstrap.json at shared-project precedence. Use a personal project or checkout override to supersede that project setting. Source mode disables semantic graph queries, not local inventory generation. Index mode requires compatible semantic layers; it does not install a backend. Settings do not themselves run builds, fetch graphs, or enforce model behaviour.

Quality gates, task state, approvals, commands and project policy are deliberately outside this override schema. Their existing project files remain authoritative. No supported setting waives project checks or runtime permissions.

## Example user file

```json
{
  "schema_version": "1.0",
  "settings": {
    "tooling": {"mode": "conda", "conda_name": "my_spec_tools"},
    "agent": {"integrations": ["codex", "copilot"]}
  },
  "projects": {
    "uuid:REPLACE_WITH_PROJECT_ID": {
      "knowledge": {"mode": "source"}
    }
  }
}
```

Project-specific settings follow repository identity, not a clone path. Shared settings.json may declare a committed repository_id. Without it, the resolver hashes the canonical origin host/repository path, normalising common SSH/HTTPS spelling and removing credentials. Repositories without either have no portable identity; personal project matching is unavailable until identity is configured. Non-default server ports remain distinct; host aliases, repository moves and forks may require explicit identities. Never assign the same explicit identity to unrelated repositories.

Example checkout-local file:

```json
{
  "schema_version": "1.0",
  "settings": {
    "knowledge": {"mode": "source", "base_refs": ["origin/release/1.x"]}
  }
}
```

## Inspect and configure

From the tooling distribution:

```text
python configure.py inspect --repo /path/to/project
python configure.py configure --repo /path/to/project
python configure.py configure --repo /path/to/project --apply
```

Configuration previews by default. Apply creates an empty shared settings file with the existing canonical origin identity (or a new UUID when there is no origin) and appends the checkout-local ignore rule. Commit that identity so other clones share it. Existing bootstrap.json, project.yaml, commands and policies remain untouched and continue to load at their documented precedence. No legacy values are copied into a second active configuration. Re-running configuration refuses an existing settings.json rather than replacing it. Preview identities are illustrative; use the identity written by apply. Configuration does not update installed scripts. Use the installer upgrade preview for a managed installation, or manually reconcile an older installation without a ledger, before using new settings there.

`migrate` remains a deprecated CLI alias for `configure`; it performs the same operation and prints a warning.

In an installed project the equivalent entry point is:

```text
python ai_workflow/tools/settings.py inspect --repo .
python ai_workflow/tools/settings.py configure --repo .
```

Inspection is read-only and includes effective settings, per-field origins, repository identity and a SHA256 fingerprint of effective preferences (not file locations/provenance). Null env_dir is a symbolic distribution default, not proof two machines have the same runtime. Bootstrap fingerprints the effective bootstrap configuration separately; unrelated tooling preferences do not invalidate knowledge. This is a preference fingerprint, not the future semantic artifact identity.

The schema accepts no credential fields. Origin remote credentials are never included in output. Supported strings and paths are shown as entered/resolved, so do not put secrets in names, paths or reference names; use external credential mechanisms.

CLI inspection overrides use JSON values, for example in Bash:

```bash
python configure.py inspect --repo /path/to/project --set 'knowledge.mode="source"'
```

## Use the resolved settings

```text
python setup_tooling.py --repo /path/to/project
python setup_tooling.py --repo /path/to/project --apply
python install.py /path/to/project
python install.py /path/to/project --apply
python ai_workflow/tools/repo_bootstrap.py prepare --repo . --knowledge-mode source --pretty
```

Machine setup only reads project settings when --repo is supplied. Installation always uses the target project as its scope. Explicit --mode, --env-dir, --conda-name and --integration override their respective preferences. An explicit installer --specify selects that executable; for the default pin, venv mode considers the configured venv directory before PATH, while native/Conda modes use PATH. An alternate selection uses its isolated environment, including named-environment discovery for Conda. Setup does not activate the calling shell; activate Conda there or use conda run for subsequent commands. Use `speckit.ref` or --speckit-ref for an official release/commit override; set up that selection before installation. See TOOLCHAIN_VERSIONS.md in the tooling distribution for isolation, records and upgrade instructions.

Bootstrap retains --config for an explicit legacy bootstrap file; its contents enter at shared-project precedence, with personal and invocation overrides above them. --base-ref selects one explicit ref over the configured candidate list. A settings change between prepare and complete invalidates pending analysis when it changes effective bootstrap configuration.

## Optional retrieval backend

`knowledge.backend` defaults to `off`; select `cgc` or `sourcegraph` at any settings layer. `cgc.executable` defaults to `cgc`; `cgc.data_dir` defaults to the checkout cache and supports file-relative overrides. Sourcegraph uses `sourcegraph.url`, `sourcegraph.repository` and `sourcegraph.token_env` (default `SOURCEGRAPH_TOKEN`). See [knowledge_backends.md](knowledge_backends.md) for commands, storage and sharing.

## Bootstrap validation and incremental inventory

`bootstrap.json` is a complete shared configuration, while `settings.local.json` and user settings are partial overrides. Bootstrap validates the shared configuration against the bundled `bootstrap.schema.json` before writing cache state. Errors identify the file and setting, including missing/unknown fields, incorrect types, invalid branch regular expressions, unsafe output paths and invalid namespace placeholders. Preserve the bundled schema when customising the configuration; it defines the tooling contract.

Incremental file inventories reuse unchanged records. Each inventory also records the dirty paths it analysed, so subsequent runs can detect restored files, renamed/deleted files and removed untracked files. Older inventories without this provenance receive a full hashing pass when they next need updating. Git inventory enumeration still runs; the optimisation avoids rereading unchanged source content, and does not provide semantic graph composition or a measured token-saving guarantee. Use `bootstrap prepare --force-full` to explicitly rebuild an invalid file index.

Bootstrap validates output paths as a complete layout: reserved state/candidate filenames, duplicate or nested output destinations, overlapping layer roots and inventory/semantic-manifest collisions are rejected before cache writes. Case-only aliases are rejected for portability. The same layout builder supplies the paths used by prepare, complete and status.

Prepared requests record a digest of their candidate index. Completion checks that digest, the source revision and worktree fingerprint, and verifies the request's paths against the configured layout before promotion. Completed state retains the index digest, so status cannot report a replaced index as fresh. These checks detect altered or mixed cache records; they do not authenticate data from another publisher. Older pending requests must be prepared again, and completed caches without integrity metadata receive a full refresh. A damaged index can be rebuilt with `bootstrap prepare --force-full`; malformed state records report the cache file requiring removal.

Bootstrap supports repositories using Git's SHA-1 and SHA-256 object formats, detected through `git rev-parse --show-object-format`. Persisted repository revisions are validated against that format. Cache content digests remain SHA-256 in both cases; the separate official Spec Kit commit-pin rules are unchanged.

Analysis planning handles configuration changes and other full-rebuild conditions before checking an index for reuse. Changing the configured index filename therefore schedules a full analysis using the new layout. Integrity checks still reject altered indices when the existing cache is otherwise reusable.
